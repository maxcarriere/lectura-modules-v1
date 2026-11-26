# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Cœur du correcteur : la chaîne G2P → P2G en contexte écrit.

1. Lecture (Transducer) : chaque mot reçoit sa prononciation (lexique, sinon modèle de mot) ; option : nettoyage
   amont des fautes qui changent la prononciation (enveloppe du Module).
2. Pour chaque mot qui a des homophones (clé phonétique connue de la tête de graphie), analyse de la phrase avec ce
   seul mot donné par sa prononciation, le reste écrit (canal par mot) : la tête de graphie donne la probabilité de
   chaque graphie candidate dans ce contexte.
3. Correction quand une autre graphie l'emporte sur la graphie reçue d'un écart de probabilité au moins ``seuil``
   (mode « suggestions » : seuil bas ; « automatique » : seuil haut).
4. Option (``generateur`` + ``juge``, voir `candidats.py`) : mots inconnus du lexique → voisins orthographiques et
   phonétiques ; flexions audibles → formes du même lemme à un trait près ; choix par le modèle de langue écrit.
"""

from __future__ import annotations

import re
import unicodedata
import warnings

from ..resultats import Correction, Resultat
from .analyseur import AnalyseurCanaux
from .candidats import TRAITS_FLEXION
from .filtres import homophone_permis, mot
from .accords import GENRE, NOMBRE, Accordeur
from .explications import ASTUCES, CATEGORIES, expliquer


def _couple_genre(masc: str, fem: str) -> bool:
    """« ami / amie », « boulanger / boulangère », « acteur / actrice », « veuf / veuve », « chat / chatte » : un vrai
    couple de genre, pas deux noms qui se ressemblent (« dit / dix »)."""
    if not masc or not fem or masc == fem:
        return False
    for a, b in (("", "e"), ("er", "ère"), ("eur", "euse"), ("eur", "rice"), ("teur", "trice"), ("f", "ve"), ("eux", "euse"),
                 ("n", "nne"), ("t", "tte"), ("l", "lle"), ("s", "sse"), ("c", "que"), ("eau", "elle"), ("e", "esse")):
        if (not a or masc.endswith(a)) and fem == masc[:len(masc) - len(a)] + b:
            return True
    return False


def _article(categorie: str) -> str:
    return ("un " if categorie in ("nom", "nom propre", "verbe", "auxiliaire", "adjectif", "adverbe", "déterminant",
                                   "pronom", "numéral") else "une ") + categorie

# homophones : écart p(meilleure) − p(reçue) exigé, et p(reçue) maximale (la graphie reçue est un indice : on ne la
# change que si elle devient improbable). Réglés le 14/10 sur la collecte masque_v1 (banc/balayer.py).
SEUILS = {"suggestions": 0.8, "automatique": 0.9, "collecte": 0.0}
P_RECUE_MAX = {"suggestions": 0.01, "automatique": 0.002, "collecte": 1.0}
# « collecte » : toutes les décisions possibles, avec leurs mesures (``Correction.mesures``), pour régler les seuils
# hors ligne (banc/collecter.py, banc/balayer.py) ; les homophones n'y modifient pas le contexte des suivants.
# écarts de log10 P(phrase) exigés : candidat hors lexique (sur le deuxième), flexion (sur la forme reçue)
MARGES_HORS_LEXIQUE = {"suggestions": 2.0, "automatique": 2.0, "collecte": 0.0}
MARGES_SCISSION = {"suggestions": 1.0, "automatique": 1.5, "collecte": 0.0}   # 16/10 soir : mots collés (« Cest » 1,7 face à « ceste »)
# mot inconnu dont la forme accentuée existe (« chateau », « grace ») : la faute la plus courante, marge réduite
MARGES_ACCENT = {"suggestions": 0.5, "automatique": 0.5, "collecte": 0.0}
# mot inconnu dont un mot du lexique se prononce exactement comme lui, au timbre près (« fote » → faute) : le scripteur
# a écrit ce qu'il entendait ; les candidats d'un autre son (« fête ») sont pénalisés, la marge est réduite
PENALITE_SON = 3.0                                   # « une grosse fête » plaît au LM de 1,35 log10 de plus que « faute »
MARGES_SON = {"suggestions": 1.5, "automatique": 1.5, "collecte": 0.0}   # 16/10 : 0,5 laissait passer « ème » → M, « masks » ; automatique 2 → 1,5 (13 h 40 : « il a fait une grosse fote » valait 1,55 face à « fête » ; 0 fausse de plus sur UD / prose)
COUT_LETTRE_SON = 0.3                                # entre candidats de même son, le plus proche par les lettres (reflètent, pas reflète)
LONGUEUR_SON = 4                                     # pas de « son exact » sur les mots de 3 lettres (« alt », « ème », « way »)
# forme acceptée mais rare dont la forme accentuée est bien plus fréquente (« trés ») : gain LM minimal, seuils zipf
MARGES_ACCENT_LEXIQUE = {"suggestions": 0.0, "automatique": 1.0, "collecte": -1e9}
ZIPF_ACCENT, ECART_ZIPF_ACCENT = 3.5, 1.2                 # 16/10 soir : 1,5 → 1,2 (« ages », « interim », « rebellion »), le LM doit alors gagner 1,0
ECART_ZIPF_ACCENT_SUR = 1.5
MARGES_FLEXION = {"suggestions": 3.0, "automatique": 3.0, "collecte": 0.0}
# e/ɛ, o/ɔ, ø/œ : à peine audible ; jugés par le seul modèle de langue, ils ne font que des fausses corrections en
# prose (15/10) : gardés en collecte seulement ; le cas utile (« a était » → été) est traité par les accords
MARGES_QUASI = {"suggestions": 1e9, "automatique": 1e9, "collecte": 0.0}
# accord justifié par l'analyse : le modèle de langue ne peut que s'y opposer franchement (perte log10 au-delà de…)
MARGES_ACCORD = {"suggestions": -2.0, "automatique": -1.0, "collecte": -1e9}
# homophones jugés par la tête de graphie ou les traits : le modèle de langue écrit est le second juge, il ne doit
# pas s'opposer (gain log10 de la phrase avec la graphie proposée ; 15/10 : −1 garde 81/81 justes, ôte 60 % des
# fausses corrections d'UD et de prose)
MARGES_LM = {"suggestions": -0.3, "automatique": 0.0, "collecte": -1e9}   # −1 → −0,3 le 15/10 soir : UD 1,21 → 1,00 ‰, WiCoPaCo égal
# seconde voie : graphie reçue pas assez improbable pour la tête (P_RECUE_MAX), mais modèle de langue très net
LM_FORT = {"suggestions": 2.5, "automatique": 3.0, "collecte": 1e9}
# troisième juge des homophones (``juge_homophones``, juge du transducer, 18/10), en plus du modèle de langue : quand
# il connaît le couple, il doit préférer la graphie proposée d'au moins MARGES_JUGE (écart de logits ; veto sinon), et
# très net (JUGE_FORT) il ouvre une troisième voie comme LM_FORT. Balayage du 18/10 (collecte juge_1018a) : en le
# substituant au modèle de langue, les fausses corrections montaient (UD 0,84 → 1,0 ‰) ; en veto, WiCoPaCo 61,3 → 62,0
# et 61,7 → 62,2, UD 0,84 → 0,79 / 0,68 =, roman 0,75 → 0,65 / 0,47 =.
MARGES_JUGE = {"suggestions": 3.0, "automatique": 4.0, "collecte": -1e9}
JUGE_FORT = {"suggestions": 6.0, "automatique": 6.0, "collecte": 1e9}
# le juge sur les accords (veto s'il s'oppose à l'accord justifié par l'analyse : « A noter » → noté, « gardé par un
# forgeron » → gardée) et sur les flexions homophones que l'analyse ne justifie pas (verdict « muet », ouvertes s'il
# est très net : « ses propre yeux » → propres, « on appel » → appelle). Balayage du 18/10 (collecte juge_1018b) :
# veto à −1 : WiCoPaCo 62,0 → 62,8 / 62,2 → 62,7, UD 0,79 → 0,68 / 0,68 → 0,58 ‰, FLE intact (à 0, FLE perd 0,4) ;
# muets à 8 : +0,2 / +0,1 sans fausse en plus (à 6, UD +0,05). Ensemble : 62,9 / 62,9.
MARGES_JUGE_ACCORD = {"suggestions": -1.0, "automatique": -1.0, "collecte": -1e9}
JUGE_MUET = {"suggestions": 8.0, "automatique": 8.0, "collecte": 1e9}
# … ou les deux juges nettement favorables ensemble (juge ≥ 6 et modèle de langue ≥ 1 ; balayage du 18/10 après-midi
# sur juge_1018b : 62,9 → 63,1 dans les deux modes, UD +0,06 ‰, FLE, oral et roman égaux)
JUGE_MUET_LM = {"suggestions": 6.0, "automatique": 6.0, "collecte": 1e9}
LM_MUET = {"suggestions": 1.0, "automatique": 1.0, "collecte": 1e9}
# règles de style ou plus fragiles : le modèle de langue doit être d'accord (suggestions), jamais en automatique
MARGES_REGLE = {"des_de": {"suggestions": 0.0, "automatique": 1e9, "collecte": -1e9},
                "quantite": {"suggestions": 1.0, "automatique": 2.0, "collecte": -1e9},      # noms massifs écartés par le LM
                "infinitif_apres_verbe": {"suggestions": -0.5, "automatique": 0.0, "collecte": -1e9},
                "participe_relatif": {"suggestions": -3.0, "automatique": -1.5, "collecte": -1e9}}   # structure sûre, formes rares pour le LM
# catégorie prédite (phrase écrite) assez sûre pour contredire la graphie reçue ; le lissage des étiquettes à
# l'entraînement plafonne les probabilités vers 0,9
P_UPOS_MIN = 0.8
LIGATURES = "ﬁﬂﬀﬃﬄﬅﬆ"
ALPHABET = set("abcdefghijklmnopqrstuvwxyzàâäéèêëîïôöùûüÿçœæ-'’")
CONTRACTIONS = {"ma": "m'a", "ta": "t'a", "la": "l'a", "mon": "m'ont", "ton": "t'ont", "ni": "n'y"}
CLITIQUES = {"le", "la", "les", "l'", "l’", "me", "m'", "m’", "te", "t'", "t’", "se", "s'", "s’", "nous", "vous",
             "lui", "leur", "y", "en"}
TYPES_ACCORD = {"conjugaison": "conjugaison", "personne": "conjugaison", "passe_simple": "conjugaison",
                "participe_apres_avoir": "forme_verbale",
                "participe_apres_etre": "forme_verbale",
                "infinitif_apres_verbe": "forme_verbale", "infinitif_apres_preposition": "forme_verbale"}
# élision devant une voyelle ou un h muet (le lexique dit si le h est aspiré et si le mot commence bien par une
# voyelle : pas « oui », « huit », « yaourt ») ; les lettres seules sont l'élision sans apostrophe (« l ouverture »)
_DETERMINANTS_APRES_DE = {"la", "l'", "ses", "ces", "mes", "tes", "nos", "vos", "leur", "leurs", "cette", "ce", "cet",
                          "mon", "ton", "son", "ma", "ta", "sa", "notre", "votre"}   # « des » devant eux : « de » ou « dès »
MARGE_DE_DES = 1.0            # log10 : écart minimal du modèle de langue entre « de » et « dès » pour trancher
ELISIONS_NOMINALES = {"de": "d'", "le": "l'", "la": "l'", "l": "l'", "d": "d'"}       # devant un nom, un adjectif…
ELISIONS_VERBALES = {"ne": "n'", "je": "j'", "n": "n'", "j": "j'"}                   # devant un verbe, « en », « y »
ELISIONS_QUE = {"que": "qu'", "qu": "qu'", "jusque": "jusqu'"}                        # devant tout mot à voyelle
ELISIONS_CONDITIONNELLES = {                                                          # devant certains mots seulement
    "si": ("s'", {"il", "ils"}), "ce": ("c'", {"est", "était", "étaient", "en"}), "c": ("c'", {"est", "était", "étaient"}),
    "se": ("s'", None), "me": ("m'", None), "te": ("t'", None),                      # None : verbe, « en », « y »
    "s": ("s'", {"il", "ils", "est", "était", "en", "y"}), "m": ("m'", {"a", "ai", "en", "y", "est", "ont", "avait"}),
    "t": ("t'", {"a", "ai", "en", "y", "est", "ont", "avait"}),
    "lorsque": ("lorsqu'", {"il", "ils", "elle", "elles", "on", "un", "une", "en", "ainsi"}),
    "puisque": ("puisqu'", {"il", "ils", "elle", "elles", "on", "un", "une", "en", "ainsi"}),
    "quoique": ("quoiqu'", {"il", "ils", "elle", "elles", "on", "un", "une", "en", "ainsi"})}
# mots à voyelle devant lesquels « le », « la », « de » ne s'élident pas (« la une », « le un », « de un à dix »)
SANS_ELISION = {"un", "une", "uns", "unes", "onze", "onzième", "onzièmes", "oui", "ou", "et", "or", "en", "y", "ouf"}
VOYELLES_PHONES = set("aeiouyɑɛɔøœə")                        # premier phone d'un mot élidable (pas j, w, ɥ)
_DET_MASCULINS = {"un", "le", "ce", "cet", "mon", "ton", "son", "notre", "votre", "leur", "quel", "du", "au"}   # pas « l' » (de l'héro)
# participe présent (invariable, verbe) écrit pour l'adjectif verbal homophone, après un adverbe de degré ou une
# copule (« très contant », « il est différant ») ; l'inverse après « en » (« en différent de ») — règle d'école
PAIRES_ANT = {"adhérant": "adhérent", "affluant": "affluent", "communiquant": "communicant", "convainquant": "convaincant",
              "convergeant": "convergent", "différant": "différent", "divergeant": "divergent", "équivalant": "équivalent",
              "excellant": "excellent", "expédiant": "expédient", "extravaguant": "extravagant", "fatiguant": "fatigant",
              "influant": "influent", "intriguant": "intrigant", "naviguant": "navigant", "négligeant": "négligent",
              "précédant": "précédent", "provoquant": "provocant", "somnolant": "somnolent", "suffoquant": "suffocant",
              "vaquant": "vacant", "violant": "violent", "zigzaguant": "zigzagant", "émergeant": "émergent",
              "détergeant": "détergent", "déférant": "déférent", "contant": "content"}
PAIRES_ENT = {a: p for p, a in PAIRES_ANT.items() if a != "content"}       # « en content » : contenter
_ADVERBES_DEGRE = {"très", "trop", "assez", "si", "aussi", "plus", "moins", "fort", "tellement", "vraiment",
                   "extrêmement", "particulièrement", "peu", "bien", "tout", "toute", "toutes", "tous"}
_COPULES_SING = {"est", "était", "sera", "serait", "fut", "semble", "semblait", "paraît", "paraissait", "reste",
                 "restait", "devient", "devenait", "demeure", "demeurait"}
_COPULES_PLUR = {"sont", "étaient", "seront", "seraient", "furent", "semblent", "semblaient", "paraissent",
                 "paraissaient", "restent", "restaient", "deviennent", "devenaient", "demeurent", "demeuraient"}
# « il y ai », « il y as », « il y à » : toujours « il y a » (« il y ait » au subjonctif est correct)
_IL_Y_A_FAUTIFS = {"ai", "as", "à"}
# après « en » + gérondif : mots qui ne peuvent pas commencer un groupe nominal (« en différant peu », « en précédant
# la file ») — l'analyse lit parfois « peu » comme un nom
_APRES_GERONDIF = {"de", "du", "des", "d'", "d’", "le", "la", "les", "l'", "l’", "un", "une", "à", "au", "aux", "par",
                   "pour", "en", "sur", "dans", "avec", "peu", "beaucoup", "ainsi", "alors", "encore", "toujours",
                   "souvent", "parfois", "déjà", "aussi", "tout", "très", "trop", "assez", "bien", "mal", "plus", "moins"}
# pronoms qui se rattachent au verbe à l'impératif par un trait d'union (« sortez-moi », « allez-y », « prends-en »)
_CLITIQUES_IMPERATIF = {"moi", "toi", "nous", "vous", "le", "la", "les", "lui", "leur", "y", "en"}
# « touts les » : « touts » n'existe que comme nom (« des touts ») ; devant un déterminant ou un nombre, « tous »
_APRES_TOUTS = {"les", "ces", "mes", "tes", "ses", "nos", "vos", "leurs", "des", "ceux"}
_SUJETS_DE_A = {"il", "elle", "on", "qui", "ça", "cela", "ceci", "c'", "c’", "ce", "n'", "n’", "y", "en", "l'", "l’",
                "lui", "leur", "m'", "m’", "t'", "t’", "s'", "s’", "nous", "vous", "me", "te", "se", "la", "le", "les"}
_DETS_TOUT = {"les": "Plur", "ces": "Plur", "mes": "Plur", "tes": "Plur", "ses": "Plur", "nos": "Plur", "vos": "Plur",
              "leurs": "Plur", "le": "Sing", "la": "Sing", "ce": "Sing", "cette": "Sing", "mon": "Sing", "ma": "Sing",
              "ton": "Sing", "ta": "Sing", "son": "Sing", "sa": "Sing", "un": "Sing", "une": "Sing", "notre": "Sing",
              "votre": "Sing", "leur": "Sing"}
_SUBJONCTIFS_ETRE = {"soit": "Sing", "soient": "Plur", "fût": "Sing", "fussent": "Plur", "puisse": "Sing", "puissent": "Plur"}
_QUOI_QUE = ("il arrive", "il advienne", "il en soit", "il en coûte", "on en dise", "il fasse", "il dise", "on fasse",
             "on dise", "il en pense", "on en pense", "il se passe", "elle fasse", "elle dise", "ils fassent", "ils disent")
_AU_AUX = {"au": "aux", "aux": "au", "leur": "leurs", "leurs": "leur", "quelque": "quelques", "quelques": "quelque"}
# déterminants homophones au singulier et au pluriel : l'autre côté de l'accord (« au réformes », « leur affaires »)
# numéraux écrits avec un s (« les huits bungalows », « dix milles ans ») ; pas « vingts », « cents » (multipliés),
# ni « neufs » (adjectif), ni « uns »
_NUMERAUX_FAUTIFS = {f + "s": f for f in ("deux", "trois", "quatre", "cinq", "six", "sept", "huit", "dix", "onze", "douze",
                                          "treize", "quatorze", "quinze", "seize", "trente", "quarante", "cinquante",
                                          "soixante", "mille")}
_MILLES_MESURE = {"marins", "marin", "nautiques", "nautique", "terrestres", "anglais", "romains", "à", "par", "de", "carrés"}
# après « dès » : « dès que », « dès lors », « dès maintenant », « dès 1959 », « dès le début »
_APRES_DES = {"que", "qu'", "qu’", "lors", "maintenant", "aujourd'hui", "demain", "hier", "à", "l'", "l’", "son", "sa",
              "ses", "leur", "leurs", "ce", "cet", "cette", "ces", "mon", "ma", "mes", "ton", "ta", "tes", "notre", "nos",
              "votre", "vos", "le", "la", "les", "un", "une"}
# mots de quantité devant lesquels « d'avantage » est bien le nom (« pas d'avantage à », « beaucoup d'avantages »)
_QUANTITES = {"pas", "plus", "point", "peu", "beaucoup", "trop", "assez", "tant", "autant", "moins", "guère", "que",
              "qu'", "qu’", "aucun", "nul", "sans", "combien", "énormément", "suffisamment", "davantage", "bien"}
_CATEGORIES_VIDES = {"PRON", "DET", "X", "INTJ", "CCONJ", "SCONJ", "ADP", "PART", "SYM"}
# coût a priori (log10) d'un candidat hors lexique selon son origine et sa distance
# validités LeXiK d'un mot qu'on ne laisse pas « nettoyer » par le Module
VALIDES = ("proposable", "acceptee")
COUT = {("ortho", 1): 1.0, ("ortho", 2): 2.5, ("phone", 0): 0.5, ("phone", 1): 2.0, ("accent", 1): 0.3, ("accent", 2): 1.0,
        ("scission", 1): 1.0, ("elision", 1): 1.0, ("elision", 2): 2.0}   # elision : clitique + voisin du reste (« lortograf »)
# locutions figées écrites avec des traits d'union (famille « segmentation » de WiCoPaCo)
LOCUTIONS = {"c'est à dire": "c'est-à-dire", "c’est à dire": "c’est-à-dire", "vis à vis": "vis-à-vis",
             "au dessus": "au-dessus", "au dessous": "au-dessous", "là bas": "là-bas", "par dessus": "par-dessus",
             "par dessous": "par-dessous", "au delà": "au-delà", "ci dessous": "ci-dessous", "ci dessus": "ci-dessus",
             "ci joint": "ci-joint", "ci jointe": "ci-jointe", "rez de chaussée": "rez-de-chaussée",
             "après midi": "après-midi", "grand mère": "grand-mère", "grand père": "grand-père",
             "grands parents": "grands-parents", "week end": "week-end", "là haut": "là-haut",
             "au dedans": "au-dedans", "peut être que": "peut-être que",                  # (« en dessous » s'écrit sans trait)
             "toute fois": "toutefois", "quelque fois": "quelquefois", "long temps": "longtemps", "plu tôt": "plutôt",
             "au jourd'hui": "aujourd'hui", "au jourd’hui": "aujourd’hui", "par fois": "parfois", "sur tout": "surtout",
             "d'ors et déjà": "d'ores et déjà", "d’ors et déjà": "d’ores et déjà",   # soudures et locutions mal écrites
             "vice versa": "vice-versa", "chef d'œuvre": "chef-d'œuvre", "chef d'oeuvre": "chef-d'œuvre",
             "hors d'œuvre": "hors-d'œuvre", "sous marin": "sous-marin", "sous marins": "sous-marins",
             # 16/10 : pronoms + même, indéfinis, adverbes, noms composés sans lecture libre plausible (pas « belle
             # mère », « petite fille », « long métrage », « peut être »)
             "moi même": "moi-même", "toi même": "toi-même", "lui même": "lui-même", "elle même": "elle-même",
             "soi même": "soi-même", "nous mêmes": "nous-mêmes", "nous même": "nous-mêmes", "vous mêmes": "vous-mêmes",
             "vous même": "vous-même", "eux mêmes": "eux-mêmes", "eux même": "eux-mêmes", "elles mêmes": "elles-mêmes",
             "elles même": "elles-mêmes", "quelques uns": "quelques-uns", "quelques unes": "quelques-unes",
             "jusque là": "jusque-là", "ci après": "ci-après", "ci contre": "ci-contre", "ci inclus": "ci-inclus",
             "ci joints": "ci-joints", "ci jointes": "ci-jointes", "là dessus": "là-dessus", "là dessous": "là-dessous",
             "là dedans": "là-dedans", "par delà": "par-delà", "avant hier": "avant-hier", "après demain": "après-demain",
             "grand chose": "grand-chose", "état major": "état-major", "états majors": "états-majors",
             "porte parole": "porte-parole", "porte avions": "porte-avions", "arc en ciel": "arc-en-ciel",
             "arcs en ciel": "arcs-en-ciel", "contre attaque": "contre-attaque", "contre attaques": "contre-attaques",
             "contre offensive": "contre-offensive", "contre offensives": "contre-offensives",
             "quasi totalité": "quasi-totalité", "box office": "box-office", "demi heure": "demi-heure",
             "demi heures": "demi-heures", "mi temps": "mi-temps", "chefs d'œuvre": "chefs-d'œuvre",
             "chefs d'oeuvre": "chefs-d'œuvre", "grands mères": "grands-mères", "grands pères": "grands-pères",
             "rez de chaussées": "rez-de-chaussées", "week ends": "week-ends",
             # démonstratifs composés, toponymes dont le trait d'union est obligatoire (pas « sud est » : « le sud
             # est », ni « croix rouge » : « une croix rouge »)
             # « de part le monde » → « de par » (pas « de part et d'autre », « mis à part les »)
             "de part le": "de par le", "de part la": "de par la", "de part les": "de par les", "de part leur": "de par leur",
             "de part leurs": "de par leurs", "de part sa": "de par sa", "de part son": "de par son", "de part ses": "de par ses",
             "de part ce": "de par ce", "de part cette": "de par cette", "de part ces": "de par ces",
             "celui ci": "celui-ci", "celle ci": "celle-ci", "ceux ci": "ceux-ci", "celles ci": "celles-ci",
             "celui là": "celui-là", "celle là": "celle-là", "ceux là": "ceux-là", "celles là": "celles-là",
             "états unis": "États-Unis", "etats unis": "États-Unis", "royaume uni": "Royaume-Uni",
             "grande bretagne": "Grande-Bretagne", "pays bas": "Pays-Bas", "nouvelle zélande": "Nouvelle-Zélande",
             "nouvelle calédonie": "Nouvelle-Calédonie", "moyen orient": "Moyen-Orient", "proche orient": "Proche-Orient",
             "extrême orient": "Extrême-Orient", "monte carlo": "Monte-Carlo", "saint pétersbourg": "Saint-Pétersbourg",
             "sud ouest": "sud-ouest", "nord ouest": "nord-ouest", "île de france": "Île-de-France",
             "ile de france": "Île-de-France", "meurthe et moselle": "Meurthe-et-Moselle",
             "seine saint denis": "Seine-Saint-Denis", "pas de calais": "Pas-de-Calais", "hauts de seine": "Hauts-de-Seine",
             "val de marne": "Val-de-Marne", "val d'oise": "Val-d'Oise", "loir et cher": "Loir-et-Cher",
             "saône et loire": "Saône-et-Loire", "ille et vilaine": "Ille-et-Vilaine", "tarn et garonne": "Tarn-et-Garonne",
             "lot et garonne": "Lot-et-Garonne", "maine et loire": "Maine-et-Loire", "eure et loir": "Eure-et-Loir",
             "indre et loire": "Indre-et-Loire", "alpes maritimes": "Alpes-Maritimes", "hautes alpes": "Hautes-Alpes",
             "hautes pyrénées": "Hautes-Pyrénées", "pyrénées orientales": "Pyrénées-Orientales",
             "pyrénées atlantiques": "Pyrénées-Atlantiques", "haute garonne": "Haute-Garonne", "haute savoie": "Haute-Savoie",
             "haute loire": "Haute-Loire", "haute marne": "Haute-Marne", "haute saône": "Haute-Saône",
             "haute vienne": "Haute-Vienne", "haute corse": "Haute-Corse", "corse du sud": "Corse-du-Sud",
             "seine maritime": "Seine-Maritime", "seine et marne": "Seine-et-Marne", "bouches du rhône": "Bouches-du-Rhône",
             "rhône alpes": "Rhône-Alpes"}
# adresses web et courriels : on n'y corrige rien (« humanuscrit.com » n'est pas « comme »)
_ADRESSE_RE = re.compile(r"(?:https?://|www\.)\S+|[\w.+-]+@[\w-]+\.[\w.]+|\b[\w-]+\.(?:com|fr|org|net|io|eu|edu|gov|info)\b")
_LOCUTIONS_RE = re.compile(r"(?<![\w'’-])(" + "|".join(sorted(map(re.escape, LOCUTIONS), key=len, reverse=True))
                           + r")(?![\w-])", re.IGNORECASE)


# ``Correction`` et ``Resultat`` vivent dans ``lectura_nlp_fr.resultats`` (communs au mode local et au mode API).


def _levenshtein(a: str, b: str) -> int:
    prec = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cour = [i]
        for j, cb in enumerate(b, 1):
            cour.append(min(prec[j] + 1, cour[j - 1] + 1, prec[j - 1] + (ca != cb)))
        prec = cour
    return prec[-1]


def _sans_accents(forme: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", forme) if not unicodedata.combining(ch))


def _premier_mot(lus, j: int) -> bool:
    """Premier mot de la phrase : rien avant lui que de la ponctuation ou des puces (« * Lappareil de Golgi »,
    « — Etat des lieux ») ; une majuscule y est de position, pas de nom propre."""
    if lus is None:
        return j == 0
    return all(not lus[i].mot.forme[:1].isalnum() for i in range(j))


def _recoller(coupe: str, forme: str) -> str:
    """Coupe d'un mot collé avec les lettres reçues (« lAdonis » + « l'adonis » → « l'Adonis », « Lappareil » →
    « L'appareil ») : seuls l'espace ou l'apostrophe sont ajoutés."""
    prop, p = "", 0
    for ch in coupe:
        if ch in " '":
            prop += ch
        else:
            prop += forme[p]
            p += 1
    return prop


def _casse(graphie: str, modele: str) -> str:
    if modele[:1].isupper() and not graphie[:1].isupper():
        return graphie[:1].upper() + graphie[1:]
    return graphie


def _son(phone: str) -> str:
    return "".join(c for c in phone if c not in " .‿")


def appliquer(texte: str, corrections: list[Correction]) -> str:
    for c in sorted(corrections, key=lambda c: c.debut, reverse=True):
        texte = texte[:c.debut] + c.proposition + texte[c.fin:]
    return texte


def _elision_casse(original: str, remplacement: str, motif: str) -> str:
    """Élision recollée par le nettoyage du Module (« lHôpital » → « L'hôpital ») : la majuscule du nom reste au nom
    (« l'Hôpital »), l'élision prend la casse de la lettre reçue."""
    if motif == "elision" and len(original) > 2 and original[1:2].isupper() and original[:1].isalpha() \
            and remplacement[1:2] in ("'", "’") and remplacement[2:].lower() == original[1:].lower():
        return original[:1] + remplacement[1] + original[1:]
    return remplacement


def _uniques(corrections) -> list[Correction]:
    """Les corrections dans l'ordre, sans doublon d'objet (une correction à deux mots est rangée sous deux indices)."""
    vus, res = set(), []
    for c in corrections:
        if id(c) not in vus:
            vus.add(id(c))
            res.append(c)
    return res


class Correcteur:
    def __init__(self, chaine=None, analyseur: AnalyseurCanaux | None = None, nettoyer: bool = True,
                 contexte: str = "dual", generateur=None, juge=None, hors_lexique: bool = True, flexion: bool = True,
                 accords: bool = True, models_dir=None, transducer_dir=None, lexique=None, fils: int | None = None,
                 abreviations: bool = False, juge_homophones=None):
        """Sans ``chaine`` ni ``analyseur`` : tout est chargé depuis les dossiers de modèles (``charger``) ; ``fils`` :
        fils ONNX de l'analyseur (défaut : variable LECTURA_CORRECTEUR_FILS, sinon 1) ; ``abreviations`` : couche
        optionnelle qui réécrit le langage SMS (« bjr », « cava », « pk » : ``sms.py``)."""
        if chaine is None or analyseur is None:
            from . import charger

            c = charger(models_dir, transducer_dir, lexique, fils=fils, chaine=chaine, nettoyer=nettoyer,
                        contexte=contexte, hors_lexique=hors_lexique, flexion=flexion, accords=accords,
                        abreviations=abreviations, juge_homophones=juge_homophones)
            self.__dict__.update(c.__dict__)
            return
        self.abreviations = abreviations
        self.chaine = chaine                      # lectura_nlp_fr.analyseur.chaine.Chaine
        self.analyseur = analyseur
        self.nettoyer = nettoyer
        self.contexte = contexte                  # canal des mots du contexte : « dual » ou « ortho »
        self.generateur = generateur              # candidats.Generateur (lexique), facultatif
        self.juge = juge                          # candidats.Juge (modèle de langue), facultatif
        self.juge_homophones = juge_homophones    # juge_homophones.JugeHomophones (juge du transducer), facultatif
        self.hors_lexique = hors_lexique and generateur is not None and juge is not None
        self.flexion = flexion and generateur is not None and juge is not None
        self.accordeur = Accordeur(generateur.lex) if accords and generateur is not None else None

    def corriger(self, texte: str, mode: str = "suggestions", seuil: float | None = None) -> Resultat:
        """Trois étapes, du plus sûr au plus coûteux : la prononciation reçue est le meilleur indice de ce que le
        scripteur voulait dire, on la garde autant que possible.
        1. mots inconnus du lexique → voisins (orthographe, prononciation), modèle de langue ;
        2. homophones (même prononciation) : tête de graphie, ou traits prédits par le tagger quand la tête ne
           connaît pas la prononciation (roulait / roulaient) ;
        3. flexions audibles (un / une, est / sont) en dernier recours, marge haute, sur la phrase déjà corrigée."""
        seuil = SEUILS[mode] if seuil is None else seuil
        corrections: list[Correction] = []
        try:
            phrases = self.chaine.lire(texte, corriger=self.nettoyer)
        except ImportError:
            # analyseur sans son enveloppe de nettoyage (elle migre dans ce paquet) : sans nettoyage
            warnings.warn("Analyseur sans nettoyage des entrées : correction sans l'étape lexicale du Module",
                          RuntimeWarning, stacklevel=2)
            self.nettoyer = False
            phrases = self.chaine.lire(texte, corriger=False)
        brutes = phrases
        if self.nettoyer and any(self._validite(c.original) in VALIDES or self._accent_voisin(c.original, c.remplacement)
                                 for p in phrases for c in p.corrections):
            # le Module a « nettoyé » un mot que LeXiK connaît (« sauterai » → sauverai) : les étapes suivantes
            # doivent voir le mot écrit (16/10) ; relecture sans nettoyage, les corrections du Module gardées à part
            brutes = self.chaine.lire(texte, corriger=False)
            if len(brutes) != len(phrases):
                brutes = phrases
        for phrase, brute in zip(phrases, brutes):
            lexicales = [self._scission_du_nettoyage(c) or
                         Correction(c.debut, c.fin, c.original, _elision_casse(c.original, c.remplacement, c.motif),
                                    "lexical", c.score, c.motif, {"validite": self._validite(c.original)})
                         for c in phrase.corrections if not self._accent_voisin(c.original, c.remplacement)]
            # le nettoyage du Module ne voit que son lexique embarqué : un mot que LeXiK propose est gardé
            lus = brute._lus()
            if lus:
                corrections += self._locutions(texte, lus[0].mot.debut, lus[-1].mot.fin)
            etrangers = {j for j in range(len(lus)) if self._etranger(lus, j)}
            ajoutees = [c for c in lexicales
                        if (mode == "collecte" or c.mesures["validite"] not in VALIDES)
                        and all(ch in ALPHABET for ch in c.original.lower())
                        and not any(lus[j].mot.debut <= c.debut < lus[j].mot.fin for j in etrangers)]
            # mots que le nettoyage du Module remplace vraiment (pas ceux que LeXiK connaît : « sauterai » reste
            # examinable par les accords, même en collecte)
            deja = {c.debut for c in lexicales if c.mesures["validite"] not in VALIDES}
            if self.abreviations:
                sms = self._sms(texte, lus, mode)
                ajoutees = [c for c in ajoutees if not any(c.debut == a.debut for a in sms)] + sms
                deja |= {c.debut for c in sms}
            corrections += ajoutees
            if not lus:
                continue
            faites: dict[int, Correction] = {}
            # les corrections lexicales gardées entrent dans le rendu vu par le modèle de langue et par l'analyse
            # (« Cest lécole » : « c'est » se juge devant « l'école », pas devant « lécole »), sans être recomptées
            prealables: set[int] = set()
            for c in ajoutees:
                if c.mesures.get("validite") in VALIDES:
                    continue                                  # collecte : « cardiopathies → cardiopathie » n'est pas appliquée
                for i, m in enumerate(lus):
                    if m.mot.debut == c.debut and i not in faites:
                        faites[i] = c
                        prealables.add(i)
                        break
            examinables = self._examinables(lus, deja)
            if self.hors_lexique:
                self._ligatures(texte, lus, faites)
                self._je_ai(texte, lus, faites, mode)
                self._hors_lexique(texte, lus, examinables, faites, mode)
            attentes, analyses, refusees = self._accords(texte, lus, examinables, faites, mode)
            self._homophones(texte, lus, deja, faites, seuil, P_RECUE_MAX.get(mode, 1.0), attentes, analyses,
                             collecte=mode == "collecte", marge_lm=MARGES_LM[mode], lm_fort=LM_FORT[mode],
                             refusees=refusees, marge_juge=MARGES_JUGE[mode], juge_fort=JUGE_FORT[mode],
                             juge_muet=JUGE_MUET[mode], juge_muet_lm=JUGE_MUET_LM[mode], lm_muet=LM_MUET[mode])
            if self.flexion:
                self._flexions_audibles(texte, lus, examinables, faites, mode, attentes)
            corrections += _uniques(c for i, c in faites.items() if i not in prealables)   # une élision couvre deux mots : une seule correction
        lex = self.generateur.lex if self.generateur is not None else None
        adresses = [(a.start(), a.end()) for a in _ADRESSE_RE.finditer(texte)]
        corrections = [c for c in corrections if not any(c.debut < fin and c.fin > debut for debut, fin in adresses)]
        # deux corrections qui se chevauchent (« Etats Unis » → « États-Unis » et « Etats » → « États ») : la plus longue
        corrections.sort(key=lambda c: (c.debut, -(c.fin - c.debut)))
        gardees: list[Correction] = []
        for c in corrections:
            if gardees and c.debut < gardees[-1].fin:
                continue
            gardees.append(c)
        corrections = gardees
        for c in corrections:
            c.explication = expliquer(c, lex)
        return Resultat(appliquer(texte, corrections), corrections)

    # ── étapes ─────────────────────────────────────────────────────────────────

    def _accent_voisin(self, original: str, remplacement: str) -> bool:
        """« cone » nettoyé en « conne » alors que LeXiK a « cône » : un voisin qui ne diffère que par les accents
        l'emporte sur le nettoyage du Module ; le mot reste examinable par les candidats hors lexique (origine
        « accent »)."""
        if self.generateur is None or not original.isalpha() or len(original) < 3 or self._validite(original) in VALIDES:
            return False
        bas = original.lower()                                # même si le nettoyage accentue (« vertebrés » → vertèbres ?
        squelette = _sans_accents(bas)                        # vertébrés ?) : le modèle de langue départage les candidats
        return any(_sans_accents(v.ortho.lower()) == squelette and not v.propre and v.zipf >= 2.0
                   for v in self.generateur.lex.voisins_orthographiques(bas, distance_max=1, limite=20, validite_min="proposable"))

    def _scission_du_nettoyage(self, c) -> Correction | None:
        """Le nettoyage du Module ramène un mot collé à l'une de ses parties (« participentà » → participent) : si le
        lexique coupe le mot en deux mots connus dont l'une est cette partie, c'est la coupe qu'on propose."""
        if self.generateur is None or not c.original.isalpha() or self._validite(c.original) in VALIDES:
            return None
        cible = c.remplacement.lower()
        for sc in self.generateur.scissions(c.original):
            parties = [p.rstrip("'") for p in sc.replace("'", "' ").split()]
            if cible in parties or "'" in sc and c.original[len(parties[0])].isupper():
                # « participentà » → « participent à » ; « lArche » → « l'Arche » (nettoyé en « Marche »)
                prop = _recoller(sc, c.original)
                return Correction(c.debut, c.fin, c.original, prop, "lexical", c.score, "scission",
                                  {"validite": "inconnue", "regle": "scission"},
                                  explication=f"« {c.original} » : deux mots collés : « {prop} ».")
        return None

    def _examinables(self, lus, deja: set[int]) -> list[tuple[int, object, str]]:
        from lectura_nlp_fr.analyseur.structures import TypeMot

        if self.generateur is None:
            return []
        sortie = []
        for j, m in enumerate(lus):
            forme = m.mot.forme
            if (m.mot.type is TypeMot.MOT and m.mot.debut not in deja and forme.isalpha()
                    and not (forme[:1].isupper() and not _premier_mot(lus, j)) and not (forme.isupper() and len(forme) > 1)
                    and not self._etranger(lus, j)):
                lex = self.generateur.lex
                validite = lex.validite(forme)
                if validite != "inconnue" and forme[:1].isupper() and _premier_mot(lus, j) \
                        and lex.validite(forme.lower()) == "inconnue" \
                        and all(l.upos == "PROPN" for l in lex.lectures(forme)) \
                        and any("'" in c and lex.frequence(c.split("'", 1)[1]) >= 4.0 for c in self.generateur.scissions(forme)):
                    validite = "inconnue"                     # « Jai vu » : « Jai » n'est un nom propre que pour le lexique,
                                                              # en tête de phrase « j'ai » est en lice (le LM tranche) ;
                                                              # pas « Latour », « Nissa » (« atour », « issa » : mots rares)
                sortie.append((j, m, validite))
        return sortie

    @staticmethod
    def _locutions(texte: str, debut: int, fin: int) -> list[Correction]:
        """Locutions figées sans leurs traits d'union (« c'est à dire », « vis à vis », « au dessus »)."""
        res = []
        for m in _LOCUTIONS_RE.finditer(texte[debut:fin]):
            recu = m.group(1)
            cible = LOCUTIONS[recu.lower()]
            cible = cible[0].upper() + cible[1:] if recu[:1].isupper() else cible
            if "-" in cible:
                explication = f"« {recu} » est une locution figée qui s'écrit avec des traits d'union : « {cible} »."
            elif " " not in cible:
                explication = f"« {recu} » s'écrit en un seul mot : « {cible} »."
            elif cible.lower().startswith("d"):
                explication = f"La locution s'écrit « {cible} » (« ores » est un vieux mot pour « maintenant »)."
            else:
                explication = (f"« {recu} » : la locution est « de par » (= par l'effet de, à travers : « de par le "
                               f"monde ») ; « part » est le nom (« une part », « de part et d'autre »).")
            res.append(Correction(debut + m.start(1), debut + m.end(1), recu, cible, "typographie", 1.0, "locution",
                                  {"regle": "locution"}, explication=explication))
        return res

    def _etranger(self, lus, j: int) -> bool:
        """Mot pris dans un passage en langue étrangère (« the river birds are back ») : au moins
        deux de ses quatre voisins sont inconnus du lexique ou de catégorie X (mot étranger)."""
        if self.generateur is None:
            return False
        inconnus = 0
        for i in range(max(0, j - 2), min(len(lus), j + 3)):
            # la ponctuation occupe sa place dans la fenêtre : sauter jusqu'aux mots d'après une virgule prend les noms
            # propres pour un passage étranger (« disctict d'Anyue, Sichuan », « francais, Augustus Pugin » : essai du 18/10)
            f = lus[i].mot.forme
            if i == j or not f.isalpha() or (f[:1].isupper() and _premier_mot(lus, i)):
                continue
            lectures = self.generateur.lex.lectures(f.lower())
            if not lectures or all(l.upos == "X" for l in lectures):
                inconnus += 1                                 # inconnu, ou mot étranger (« to », « war »)
        if inconnus >= 2:
            return True
        if inconnus == 1:
            # un seul voisin inconnu, mais le groupe est isolé entre parenthèses ou guillemets (« (poncirus trifoliata) »,
            # « " vacuum extractor " ») : nom latin, titre, citation
            bords = []
            for pas in (-1, 1):
                i = j + pas
                while 0 <= i < len(lus) and abs(i - j) <= 3 and lus[i].mot.forme.isalpha():
                    i += pas
                bords.append(lus[i].mot.forme if 0 <= i < len(lus) else "")
            if bords[0] in ("(", "«", '"', "“", "[") and bords[1] in (")", "»", '"', "”", "]"):
                return True
        return False

    def _validite(self, forme: str) -> str:
        if self.generateur is None or not forme.isalpha():
            return ""
        return self.generateur.lex.validite(forme.lower())

    @staticmethod
    def _rendu(texte: str, lus, faites: dict[int, Correction], j: int | None = None, forme: str = "",
               debut: int | None = None) -> str:
        """Phrase avec les corrections faites, plus ``forme`` à la place du mot ``j`` (ou de ``debut`` à sa fin)."""
        d0 = lus[0].mot.debut
        t = texte[d0:lus[-1].mot.fin]
        plages = {(c.debut, c.fin, c.proposition) for i, c in faites.items() if i != j}  # une correction peut couvrir deux mots
        if j is not None:
            plages.add((lus[j].mot.debut if debut is None else debut, lus[j].mot.fin, forme))
        for a, b, p in sorted(plages, reverse=True):
            t = t[:a - d0] + p + t[b - d0:]
        return t

    def _accords(self, texte, lus, examinables, faites, mode) -> dict:
        """Accords, conjugaison et formes verbales justifiés par l'analyse (``accords.py``), puis majuscules
        accentuées. Rend les attentes de l'analyse, consultées par les étapes suivantes."""
        if self.accordeur is None:
            return {}, None, {}
        formes = [faites[i].proposition if i in faites else m.mot.forme for i, m in enumerate(lus)]
        cles = [self.chaine._cle_lue(m) or "" for m in lus]
        types = ["p" if m.origine == "ponctuation" else "m" for m in lus]
        analyses, _ = self.analyseur.analyser_mixte(formes, cles, [self.contexte] * len(lus), types, [""] * len(lus))
        attentes = self.accordeur.attentes(formes, analyses)
        ex = {j for j, _m, _v in examinables}
        # règles fermées d'abord (leur explication est la plus précise) : « il y ai », « touts les », « très contant »
        self._il_y_a(texte, lus, faites, mode)
        self._touts(texte, lus, analyses, faites, mode)
        self._participe_present(texte, lus, analyses, faites, mode)
        self._les_plus(texte, lus, analyses, faites, mode)
        self._seul(texte, lus, analyses, faites, mode)
        self._imperatif_pronom(texte, lus, analyses, faites)
        self._numeraux(texte, lus, analyses, faites, mode)
        self._entre_autres(texte, lus, analyses, faites, mode)
        self._autre_part(texte, lus, faites, mode)
        self._a_infinitif(texte, lus, analyses, faites, mode)
        self._leur_pronom(texte, lus, analyses, faites, mode)
        self._quel_que(texte, lus, analyses, faites, mode)
        self._quoi_que(texte, lus, faites)
        self._tout_les(texte, lus, analyses, faites, mode)
        self._voire(texte, lus, analyses, faites, mode)
        self._accent_inverse(texte, lus, faites)
        base = None
        refusees: dict[int, str] = {}
        for j, p in self.accordeur.proposer(formes, analyses, attentes).items():
            m = lus[j]
            if j not in ex or j in faites or (p.fusion and (j - 1 in faites or j - 1 not in ex)):
                continue
            src = p.attente.source
            if src is not None and src in faites and faites[src].proposition.lower() != formes[src].lower():
                continue                                      # « la liste a biffer » : « a » déjà corrigé en « à », l'attente est caduque
            debut = lus[j - 1].mot.debut if p.fusion else m.mot.debut
            original = texte[debut:m.mot.fin]
            gain = 0.0
            if self.juge is not None:
                if base is None:
                    base = self.juge.note(self._rendu(texte, lus, faites))
                gain = self.juge.note(self._rendu(texte, lus, faites, j, _casse(p.forme, original), debut)) - base
            marge = MARGES_REGLE.get(p.attente.regle, MARGES_ACCORD)[mode]
            jg = None
            if self.juge_homophones is not None and not p.fusion:
                jg = self.juge_homophones.note(formes, j, formes[j], p.forme)   # troisième juge, s'il connaît le couple
            if self._alternative(texte, lus, faites, formes, ex, p, j, gain, base, marge):
                refusees[j] = p.forme                         # « au réformes » → aux, « il renforcent » → ils (ou abstention) :
                continue                                      # les homophones ne reprennent pas l'autre côté
            if jg is not None and jg < MARGES_JUGE_ACCORD[mode] \
                    and not (p.attente.regle in ("sujet", "personne") and p.confiance >= 0.9):
                # veto du juge sur les accords de rattachement (participe, nom, attribut, déterminant : « un autel
                # surmonté d'une enclume gardé par » → gardée) ; pas sur un sujet que l'analyse a trouvé avec confiance
                # (« la plupart des religions précédant le christianisme intègre » → intègrent : le juge, comme le
                # modèle de langue, cède à l'accord de proximité)
                refusees[j] = p.forme
                continue
            if gain < marge:
                refusees[j] = p.forme                         # le modèle de langue s'y oppose : les homophones ne la reprennent pas
                continue
            faites[j] = Correction(debut, m.mot.fin, original, _casse(p.forme, original),
                                   TYPES_ACCORD.get(p.attente.regle, "accord"), p.confiance, p.attente.regle,
                                   {"regle": p.attente.regle, "confiance": p.confiance, "gain": gain,
                                    "juge": None if jg is None else round(jg, 3)},
                                   explication=p.explication)
        self._majuscules(texte, lus, analyses, faites)
        self._contractions(texte, lus, analyses, faites, ex)
        self._elisions(texte, lus, faites)
        self._davantage(texte, lus, analyses, faites, mode)
        self._des_accent(texte, lus, analyses, faites, mode)
        self._des_determinant(texte, lus, faites, mode)
        self._heros(texte, lus, analyses, faites)
        return attentes, analyses, refusees

    def _heros(self, texte, lus, analyses, faites) -> None:
        """« un héro » → « un héros » : « héros » garde son s au singulier ; « héro » (sans s, dans LeXiK) est
        l'abréviation familière d'héroïne, féminine, jamais derrière un déterminant masculin."""
        for j in range(1, len(lus)):
            m = lus[j]
            if m.mot.forme.lower() != "héro" or j in faites or lus[j - 1].mot.forme.lower() not in _DET_MASCULINS:
                continue
            orig = texte[m.mot.debut:m.mot.fin]
            faites[j] = Correction(m.mot.debut, m.mot.fin, orig, _casse("héros", orig), "typographie", 0.95, "heros",
                                   {"regle": "heros"},
                                   explication=(f"« héros » s'écrit avec un s, même au singulier (« {lus[j - 1].mot.forme} héros ») ; "
                                                f"« héro » sans s est l'abréviation familière d'héroïne (la drogue)."))

    def _gain(self, texte, lus, faites, j, prop, debut=None) -> float:
        if self.juge is None:
            return 0.0
        return self.juge.note(self._rendu(texte, lus, faites, j, prop, debut)) - self.juge.note(self._rendu(texte, lus, faites))

    def _alternative(self, texte, lus, faites, formes, ex, p, j, gain, base, marge) -> bool:
        """Quand les deux mots d'un accord se prononcent pareil, l'autre côté peut être la bonne correction : « jusqu'au
        réformes » → « aux » (le singulier « réforme » est refusé par le modèle de langue), « il renforcent leur
        position » → « ils » (le pluriel est nettement plus vraisemblable). Rend True si la correction a été portée
        sur la source de l'accord."""
        if self.juge is None or base is None:
            return False
        k = p.attente.source
        src = formes[k].lower()
        if k not in ex or k in faites or k == j:
            return False
        if p.attente.regle == "determinant" and src in _AU_AUX:
            # les deux côtés se prononcent pareil : le modèle de langue départage « au déplacé » / « aux déplacés »
            alt, seuil = _AU_AUX[src], max(marge, 0.0, gain + 0.5)
            if src in ("leur", "leurs", "quelque", "quelques"):
                seuil = max(marge, 0.0, gain - 0.5)           # « leur affaires » : l'oubli du s du déterminant est la faute courante
            explication = (f"« {src} » et le nom « {formes[j]} » ne sont pas au même nombre ; ici c'est le déterminant "
                           f"qu'on corrige : « {alt} {formes[j]} »" + (" (« leur » devant un nom au pluriel prend un s ; "
                           "c'est devant un verbe, pronom, qu'il est invariable : « il leur dit »)" if src == "leur" else "")
                           + ".")
        elif p.attente.regle == "sujet" and src in ("il", "elle") \
                and all("Number=Plur" in l.feats for l in self.accordeur._lectures(formes[j], {"VERB", "AUX"})):
            alt, seuil = ("ils" if src == "il" else "elles"), max(marge, gain + 1.0)
            explication = (f"« {formes[k]} » est au singulier, mais le verbe « {formes[j]} » est au pluriel ; dans cette "
                           f"phrase, « {alt} {formes[j]} » est plus vraisemblable que « {formes[k]} {p.forme} » : "
                           f"c'est le pronom qu'on corrige.")
        else:
            return False
        orig = texte[lus[k].mot.debut:lus[k].mot.fin]
        prop = _casse(alt, orig)
        gain2 = self.juge.note(self._rendu(texte, lus, faites, k, prop)) - base
        if gain2 < seuil:
            if src in _AU_AUX and gain2 >= marge and gain - gain2 < 0.5:
                return True                                   # « au déplacés de guerre » : rien ne départage, on s'abstient
            return False
        faites[k] = Correction(lus[k].mot.debut, lus[k].mot.fin, orig, prop, "accord", p.confiance, p.attente.regle,
                               {"regle": p.attente.regle + "_source", "confiance": p.confiance, "gain": gain2},
                               explication=explication)
        return True

    def _numeraux(self, texte, lus, analyses, faites, mode) -> None:
        """« dix milles ans », « les huits bungalows » → « mille », « huit » : les numéraux sont invariables (sauf
        « vingt » et « cent » multipliés, non traités) ; « milles » reste quand c'est la mesure (« milles marins »)."""
        for j in range(len(lus) - 1):
            forme = lus[j].mot.forme.lower()
            if forme not in _NUMERAUX_FAUTIFS or j in faites:
                continue
            suivant = lus[j + 1].mot.forme.lower()
            if forme == "milles" and suivant in _MILLES_MESURE:
                continue
            precedent = lus[j - 1].mot.forme.lower() if j else ""
            if not suivant.isalpha() or not any(l.upos == "NOUN" and "Number=Plur" in l.feats
                                                for l in self.generateur.lex.lectures(suivant)):
                continue                                      # un nom au pluriel suit (« huits bungalows », lu comme nom propre)
            if not (precedent in _APRES_TOUTS or analyses[j - 1].upos == "NUM" or precedent.isdigit() or forme != "milles"):
                continue
            orig = texte[lus[j].mot.debut:lus[j].mot.fin]
            prop = _casse(_NUMERAUX_FAUTIFS[forme], orig)
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < MARGES_ACCORD[mode]:
                continue
            if forme == "milles":
                explication = (f"Le nombre « mille » est invariable : « {prop} {lus[j + 1].mot.forme} » ; « milles » avec un s "
                               f"n'existe que pour la mesure (« des milles marins »).")
            else:
                explication = f"Les numéraux sont invariables : « {prop} {lus[j + 1].mot.forme} », pas « {orig} »."
            faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "accord", 0.95, "numeral_invariable",
                                   {"regle": "numeral_invariable", "gain": round(gain, 3)}, explication=explication)

    def _entre_autres(self, texte, lus, analyses, faites, mode) -> None:
        """« entre autre » → « entre autres » (= parmi d'autres) : toujours au pluriel ; pas « entre autre chose »
        (un nom suit, autre tournure)."""
        for j in range(1, len(lus)):
            if lus[j].mot.forme.lower() != "autre" or j in faites or lus[j - 1].mot.forme.lower() != "entre":
                continue
            if j + 1 < len(lus) and analyses[j + 1].upos in ("NOUN", "ADJ", "PROPN"):
                continue
            orig = texte[lus[j].mot.debut:lus[j].mot.fin]
            prop = _casse("autres", orig)
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < MARGES_ACCORD[mode]:
                continue
            faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "accord", 0.95, "entre_autres",
                                   {"regle": "entre_autres", "gain": round(gain, 3)},
                                   explication="« entre autres » (= parmi d'autres) s'écrit toujours au pluriel.")

    def _sms(self, texte, lus, mode) -> list[Correction]:
        """Couche optionnelle (``abreviations``) : langage SMS réécrit en français courant (``sms.py``), un mot à la
        fois ; les formes qui sont aussi des mots ou des sigles ne sont réécrites que si le modèle de langue préfère
        nettement la forme pleine ; les abréviations familières (« ordi ») ne sont signalées qu'en suggestions."""
        from .sms import ABREVIATIONS, AMBIGUES, FAMILIERES, expliquer

        res: list[Correction] = []
        for j, m in enumerate(lus):
            forme = m.mot.forme
            bas = forme.lower()
            if bas not in ABREVIATIONS or forme.isupper() and len(forme) > 1 or m.origine == "ponctuation":
                continue
            if mode == "automatique" and bas in FAMILIERES:
                continue
            cible = _casse(ABREVIATIONS[bas], forme)
            gain = self._gain(texte, lus, {}, j, cible)
            if gain < (LM_FORT[mode] if bas in AMBIGUES else MARGES_ACCORD[mode]):
                continue
            res.append(Correction(m.mot.debut, m.mot.fin, forme, cible, "abreviation", 0.9, "sms",
                                  {"regle": "sms", "gain": round(gain, 3), "validite": "inconnue"},
                                  explication=expliquer(forme, cible)))
        return res

    def _je_ai(self, texte, lus, faites, mode) -> None:
        """« jé mangé », « jé raison » → « j'ai » : « jé » se prononce comme « j'ai », pas comme « je » ; devant une forme
        conjuguée (« jé mange ») c'est « je » qui manque d'orthographe (règle des accents)."""
        lex = self.generateur.lex
        for j in range(len(lus) - 1):
            if lus[j].mot.forme.lower() not in ("jé", "jè", "jais") or j in faites:
                continue
            suivant = lus[j + 1].mot.forme.lower()
            ls = lex.lectures(suivant) if suivant.isalpha() else []
            if not ls or any(l.upos in ("VERB", "AUX") and "VerbForm=Fin" in l.feats for l in ls):
                continue
            orig = texte[lus[j].mot.debut:lus[j].mot.fin]
            prop = _casse("j'ai", orig)
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < MARGES_ACCORD[mode]:
                continue
            faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "homophone", 0.95, "je_ai",
                                   {"regle": "je_ai", "gain": round(gain, 3), "p_meilleure": 1.0, "p_recue": 0.0,
                                    "tete": True, "accord": "sans_objet", "lm": round(gain, 3)},
                                   explication=f"« {orig} » se prononce comme « j'ai » (= je + avoir) : devant « {lus[j + 1].mot.forme} », "
                                               f"c'est « j'ai » qu'il faut écrire, avec l'apostrophe.")

    def _autre_part(self, texte, lus, faites, mode) -> None:
        """« d'autre parts », « d'une parts » → « part » : locution figée au singulier."""
        for j in range(2, len(lus)):
            if lus[j].mot.forme.lower() != "parts" or j in faites or lus[j - 1].mot.forme.lower() not in ("autre", "une") \
                    or lus[j - 2].mot.forme.lower() not in ("d'", "d’"):
                continue
            orig = texte[lus[j].mot.debut:lus[j].mot.fin]
            prop = _casse("part", orig)
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < MARGES_ACCORD[mode]:
                continue
            loc = "d'autre part" if lus[j - 1].mot.forme.lower() == "autre" else "d'une part"
            faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "accord", 0.95, "autre_part",
                                   {"regle": "autre_part", "gain": round(gain, 3)},
                                   explication=f"« {loc} » est une locution figée : « part » reste au singulier.")

    def _leur_pronom(self, texte, lus, analyses, faites, mode) -> None:
        """« ils leurs ont dit » → « leur » : devant un verbe, « leur » est un pronom (= à eux), invariable ; « leurs »
        avec un s est le déterminant d'un nom au pluriel (« leurs amis »)."""
        lex = self.generateur.lex
        for j in range(len(lus) - 1):
            if lus[j].mot.forme.lower() != "leurs" or j in faites:
                continue
            k = j + 1
            if lus[k].mot.forme.lower() in ("en", "y") and k + 1 < len(lus):
                k += 1
            suivant = lus[k].mot.forme.lower()
            ls = lex.lectures(suivant)
            if not ls or not all(l.upos in ("VERB", "AUX") and "VerbForm=Fin" in l.feats for l in ls) \
                    or analyses[k].upos not in ("VERB", "AUX"):
                continue
            orig = texte[lus[j].mot.debut:lus[j].mot.fin]
            prop = _casse("leur", orig)
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < MARGES_ACCORD[mode]:
                continue
            faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "accord", 0.95, "leur_pronom",
                                   {"regle": "leur_pronom", "gain": round(gain, 3)},
                                   explication=(f"Devant le verbe « {lus[k].mot.forme} », « leur » est un pronom (= à eux, à elles) : "
                                                f"il est invariable, « {prop} {texte[lus[j + 1].mot.debut:lus[k].mot.fin]} ». "
                                                f"« leurs » avec un s est le déterminant d'un nom au pluriel (« leurs amis »)."))

    def _quel_que(self, texte, lus, analyses, faites, mode) -> None:
        """« quelque soit la raison » → « quelle que soit » : devant « être » (ou « pouvoir ») au subjonctif, « quel que »
        s'écrit en deux mots et « quel » s'accorde avec le sujet qui suit le verbe."""
        lex = self.generateur.lex
        for j in range(len(lus) - 2):
            if lus[j].mot.forme.lower() not in ("quelque", "quelques") or j in faites:
                continue
            verbe = lus[j + 1].mot.forme.lower()
            if verbe not in _SUBJONCTIFS_ETRE:
                continue
            nombre = _SUBJONCTIFS_ETRE[verbe]
            genre = "Masc"
            for k in range(j + 2, min(len(lus), j + 6)):
                if analyses[k].upos in ("NOUN", "PROPN", "PRON"):
                    g = {l.traits().get("Gender") for l in lex.lectures(lus[k].mot.forme.lower()) if l.upos == analyses[k].upos} - {None}
                    genre = g.pop() if len(g) == 1 else analyses[k].feats.get("Gender", "Masc")
                    break
            quel = {("Masc", "Sing"): "quel", ("Fem", "Sing"): "quelle", ("Masc", "Plur"): "quels", ("Fem", "Plur"): "quelles"}[(genre, nombre)]
            orig = texte[lus[j].mot.debut:lus[j].mot.fin]
            prop = _casse(quel, orig) + " que"
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < MARGES_ACCORD[mode]:
                continue
            faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "homophone", 0.95, "quel_que",
                                   {"regle": "quel_que", "gain": round(gain, 3), "p_meilleure": 1.0, "p_recue": 0.0,
                                    "tete": True, "accord": "sans_objet", "lm": round(gain, 3)},
                                   explication=(f"Devant « {lus[j + 1].mot.forme} » (le verbe être au subjonctif), on écrit « quel que » "
                                                f"en deux mots, et « quel » s'accorde avec le sujet qui suit : « {prop} {lus[j + 1].mot.forme} ». "
                                                f"« quelque » en un mot veut dire « environ » ou « un certain » (« quelque temps »)."))

    def _quoi_que(self, texte, lus, faites) -> None:
        """« quoiqu'il arrive », « quoiqu'il en soit » → « quoi qu' » : « quoi que » (= quelle que soit la chose) dans ces
        tours figés ; « quoique » en un mot veut dire « bien que »."""
        for j in range(len(lus) - 2):
            f = lus[j].mot.forme.lower()
            if f not in ("quoiqu'", "quoiqu’") or j in faites:
                continue
            suite = " ".join(m.mot.forme.lower() for m in lus[j + 1:j + 4])
            if not any(suite.startswith(x) for x in _QUOI_QUE):
                continue
            orig = texte[lus[j].mot.debut:lus[j].mot.fin]
            prop = _casse("quoi qu" + orig[-1], orig)
            faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "homophone", 0.95, "quoi_que",
                                   {"regle": "quoi_que", "gain": 0.0, "p_meilleure": 1.0, "p_recue": 0.0,
                                    "tete": True, "accord": "sans_objet", "lm": 0.0},
                                   explication=(f"« {prop}{lus[j + 1].mot.forme} {lus[j + 2].mot.forme} » : « quoi que » en deux mots "
                                                f"(= quelle que soit la chose qui…) ; « quoique » en un mot veut dire « bien que »."))

    def _tout_les(self, texte, lus, analyses, faites, mode) -> None:
        """« tout les jours » → « tous les jours », « toutes les nuits » ; « tous le monde » → « tout le monde » : devant
        un déterminant, « tout » s'accorde avec le nom."""
        lex = self.generateur.lex
        for j in range(len(lus) - 2):
            f = lus[j].mot.forme.lower()
            if f not in ("tout", "tous", "toute", "toutes") or j in faites:
                continue
            det = lus[j + 1].mot.forme.lower()
            if det not in _DETS_TOUT or analyses[j + 2].upos not in ("NOUN", "PROPN", "ADJ", "NUM"):
                continue
            nombre = _DETS_TOUT[det]
            nom = lus[j + 2].mot.forme.lower()
            k = j + 2
            while k + 1 < len(lus) and analyses[k].upos == "ADJ" and analyses[k + 1].upos == "NOUN":
                k += 1
            nom = lus[k].mot.forme.lower()
            if analyses[k].upos not in ("NOUN", "PROPN"):
                continue                                      # « toutes les trois » : le genre est celui des personnes
            g = {l.traits().get("Gender") for l in lex.lectures(nom) if l.upos == "NOUN"} - {None}
            if len(g) != 1:
                continue                                      # « tous tes camarades » (épicène), « vertebrés » (inconnu) : on ne sait pas
            genre = g.pop()
            cible = {("Masc", "Sing"): "tout", ("Fem", "Sing"): "toute", ("Masc", "Plur"): "tous", ("Fem", "Plur"): "toutes"}[(genre, nombre)]
            if cible == f:
                continue
            orig = texte[lus[j].mot.debut:lus[j].mot.fin]
            prop = _casse(cible, orig)
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < MARGES_ACCORD[mode]:
                continue
            faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "accord", 0.95, "tout",
                                   {"regle": "tout", "gain": round(gain, 3)},
                                   explication=(f"Devant « {lus[j + 1].mot.forme} {lus[k].mot.forme} », « tout » s'accorde avec le nom "
                                                f"« {lus[k].mot.forme} » ({GENRE[genre]} {NOMBRE[nombre]}) : « {prop} {lus[j + 1].mot.forme} {lus[k].mot.forme} »."))

    def _a_infinitif(self, texte, lus, analyses, faites, mode) -> None:
        """« rien a voir », « la liste a biffer », « 2 a 3 kWh » → « à » : le verbe « a » n'est jamais suivi d'un
        infinitif (ce serait un participe : « a vu ») ni placé entre deux nombres. Et l'inverse : « un convoi à
        circulé » → « a » (la préposition n'est jamais suivie d'un participe passé)."""
        lex = self.generateur.lex
        for j in range(1, len(lus) - 1):
            if lus[j].mot.forme.lower() == "à" and j not in faites and j + 1 not in faites:
                suivant = lus[j + 1].mot.forme
                bas = suivant.lower()
                ls = lex.lectures(bas) if bas.isalpha() else []
                if ls and all(l.upos == "VERB" and "VerbForm=Part" in l.feats and "Tense=Past" in l.feats for l in ls) \
                        and analyses[j + 1].upos in ("VERB", "AUX") and bas not in ("été", "fait", "dû", "pu"):
                    orig = texte[lus[j].mot.debut:lus[j].mot.fin]
                    prop = _casse("a", orig)
                    gain = self._gain(texte, lus, faites, j, prop)
                    if gain >= MARGES_ACCORD[mode]:
                        explication = (f"« à » est une préposition : elle est suivie d'un nom ou d'un infinitif, jamais d'un "
                                       f"participe passé. Devant « {suivant} », c'est le verbe avoir : « a {suivant} » "
                                       f"(« il avait {suivant} »).")
                        faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "homophone", 0.95, "a_participe",
                                               {"regle": "a_participe", "gain": round(gain, 3), "p_meilleure": 1.0, "p_recue": 0.0,
                                                "tete": True, "accord": "sans_objet", "lm": round(gain, 3)}, explication=explication)
                continue
            if lus[j].mot.forme.lower() != "a" or j in faites or j + 1 in faites:
                continue
            if lus[j - 1].mot.forme.lower() in _SUJETS_DE_A:
                continue                                      # « il a finir son travail » : c'est le participe qui manque
            if analyses[j].upos == "AUX" and analyses[j].relation.startswith("aux") and analyses[j].confiance_tete >= 0.8:
                continue                                      # « le sondage a révéler que » : auxiliaire sûr, c'est le
                                                              # participe qui manque (règle participe_apres_avoir)
            suivant = lus[j + 1].mot.forme
            bas = suivant.lower()
            if not bas.isalpha() and not bas.isdigit():
                continue
            ls = lex.lectures(bas) if bas.isalpha() else []
            infinitif = ls and all(l.upos in ("VERB", "AUX") and "VerbForm=Inf" in l.feats for l in ls) \
                and analyses[j + 1].upos in ("VERB", "AUX") and bas not in ("être", "avoir")
            nombres = analyses[j + 1].upos == "NUM" and analyses[j - 1].upos == "NUM" \
                and texte[lus[j - 1].mot.debut:lus[j - 1].mot.fin].isdigit() and texte[lus[j + 1].mot.debut:lus[j + 1].mot.fin].isdigit()
            if not infinitif and not nombres:
                continue
            orig = texte[lus[j].mot.debut:lus[j].mot.fin]
            prop = _casse("à", orig)
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < MARGES_ACCORD[mode]:
                continue
            if infinitif:
                explication = (f"« a » est le verbe avoir (« il avait ») : il ne peut pas être suivi d'un infinitif. Devant "
                               f"« {suivant} », c'est la préposition « à » : « à {suivant} ».")
            else:
                avant, apres = texte[lus[j - 1].mot.debut:lus[j - 1].mot.fin], texte[lus[j + 1].mot.debut:lus[j + 1].mot.fin]
                explication = (f"Entre deux nombres, « {avant} à {apres} » marque l'intervalle : préposition "
                               f"« à », pas le verbe « a » (« il avait »).")
            faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "homophone", 0.95, "a_infinitif",
                                   {"regle": "a_infinitif", "gain": round(gain, 3), "p_meilleure": 1.0, "p_recue": 0.0,
                                    "tete": True, "accord": "sans_objet", "lm": round(gain, 3)}, explication=explication)

    def _voire(self, texte, lus, analyses, faites, mode) -> None:
        """« deux voir trois », « difficile voir impossible », « trésorier voir questeur » → « voire » (= et même) :
        l'infinitif « voir » ne suit pas directement un nom, un adjectif ou un nombre, et n'est pas suivi d'un autre
        adjectif, nom ou nombre sans déterminant."""
        for j in range(1, len(lus) - 1):
            if lus[j].mot.forme.lower() != "voir" or j in faites:
                continue
            k = j - 1
            if lus[k].mot.forme == "," and k > 0:
                k -= 1
            if analyses[k].upos not in ("NOUN", "ADJ", "NUM") or not lus[k].mot.forme[:1].isalnum():
                continue
            if analyses[j + 1].upos not in ("ADJ", "NUM", "NOUN", "ADV") or not lus[j + 1].mot.forme[:1].isalnum() \
                    or lus[j + 1].mot.forme[:1].isupper():
                continue
            if any(l.upos in ("VERB", "AUX") for l in self.generateur.lex.lectures(lus[j + 1].mot.forme.lower())) \
                    and analyses[j + 1].upos != "NUM":
                continue                                      # « voir venir », « voir grand » : forme verbale ou figée
            orig = texte[lus[j].mot.debut:lus[j].mot.fin]
            prop = _casse("voire", orig)
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < 0.0:
                continue
            faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "homophone", 0.9, "voire",
                                   {"regle": "voire", "gain": round(gain, 3), "p_meilleure": 1.0, "p_recue": 0.0,
                                    "tete": True, "accord": "sans_objet", "lm": round(gain, 3)},
                                   explication=(f"« {lus[k].mot.forme} {orig} {lus[j + 1].mot.forme} » : ici, c'est « voire » "
                                                f"(= et même), pas le verbe voir (« regarder »)."))

    def _accent_inverse(self, texte, lus, faites) -> None:
        """« á », « Á Genève », « lá » → « à », « À », « là » : l'accent aigu n'existe pas sur « a » en français."""
        from lectura_nlp_fr.analyseur.structures import TypeMot

        lex = self.generateur.lex
        for j, m in enumerate(lus):
            f = m.mot.forme
            if j in faites or m.mot.type is not TypeMot.MOT or "á" not in f.lower():
                continue
            prop = f.replace("á", "à").replace("Á", "À")
            if lex.validite(prop.lower()) == "inconnue":
                continue
            faites[j] = Correction(m.mot.debut, m.mot.fin, texte[m.mot.debut:m.mot.fin], prop, "accent", 1.0,
                                   "accent_inverse", {"regle": "accent_inverse"},
                                   explication=f"Sur « a », l'accent est toujours grave en français : « {prop} », pas « {f} ».")

    def _il_y_a(self, texte, lus, faites, mode) -> None:
        """« il y ai », « il y as », « il y à » → « il y a » : dans « il y a », c'est le verbe avoir à la 3e personne."""
        for j in range(2, len(lus)):
            m = lus[j]
            if m.mot.forme.lower() not in _IL_Y_A_FAUTIFS or j in faites or lus[j - 1].mot.forme.lower() != "y":
                continue
            k = j - 2
            if lus[k].mot.forme.lower() in ("n'", "n’") and k > 0:
                k -= 1
            if lus[k].mot.forme.lower() not in ("il", "qu'il", "s'il"):
                continue
            orig = texte[m.mot.debut:m.mot.fin]
            gain = self._gain(texte, lus, faites, j, "a")
            if gain < MARGES_ACCORD[mode]:
                continue
            faites[j] = Correction(m.mot.debut, m.mot.fin, orig, "a", "conjugaison", 0.95, "il_y_a",
                                   {"regle": "il_y_a", "gain": round(gain, 3)},
                                   explication=(f"Dans « il y a », « a » est le verbe avoir à la 3e personne (« il y avait ») : "
                                                f"« il y a », pas « il y {orig} »."))

    def _touts(self, texte, lus, analyses, faites, mode) -> None:
        """« touts les costumes » → « tous » : « touts » n'existe que comme nom (« des touts »)."""
        for j in range(len(lus) - 1):
            m, n = lus[j], lus[j + 1]
            if m.mot.forme.lower() != "touts" or j in faites:
                continue
            suivant = n.mot.forme.lower()
            if suivant not in _APRES_TOUTS and analyses[j + 1].upos != "NUM":
                continue
            orig = texte[m.mot.debut:m.mot.fin]
            prop = _casse("tous", orig)
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < MARGES_ACCORD[mode]:
                continue
            faites[j] = Correction(m.mot.debut, m.mot.fin, orig, prop, "accord", 0.95, "touts",
                                   {"regle": "touts", "gain": round(gain, 3)},
                                   explication=(f"Au masculin pluriel, « tout » s'écrit « tous » (« {prop} {n.mot.forme} ») ; "
                                                f"« touts » n'existe que comme nom (« des touts »)."))

    def _les_plus(self, texte, lus, analyses, faites, mode) -> None:
        """« parmi les plus dense d'Europe » → « denses » : après « les plus / moins / mieux », l'adjectif est au pluriel
        (le lexique dit que la forme reçue est un singulier) ; pas si un nom suit (« les plus grand nombre » : autre
        faute)."""
        for j in range(2, len(lus)):
            if j in faites or analyses[j].upos != "ADJ" or lus[j - 1].mot.forme.lower() not in ("plus", "moins", "mieux") \
                    or lus[j - 2].mot.forme.lower() != "les":
                continue
            forme = lus[j].mot.forme
            lectures = self.accordeur._lectures(forme, {"ADJ"})
            if not lectures or any("Number=Plur" in l.feats or "Number" not in l.feats for l in lectures):
                continue
            if j + 1 < len(lus) and analyses[j + 1].upos in ("NOUN", "PROPN"):
                continue
            cible = self.accordeur._flechir(forme, lectures, {"Number": "Plur"}, analyses[j])
            if not cible:
                continue
            orig = texte[lus[j].mot.debut:lus[j].mot.fin]
            prop = _casse(cible, orig)
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < MARGES_ACCORD[mode]:
                continue
            faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "accord", 0.9, "les_plus",
                                   {"regle": "les_plus", "gain": round(gain, 3)},
                                   explication=(f"Après « les {lus[j - 1].mot.forme} », l'adjectif « {forme} » est au pluriel : "
                                                f"« les {lus[j - 1].mot.forme} {prop} »."))

    def _seul(self, texte, lus, analyses, faites, mode) -> None:
        """« seul 4 coureurs parviennent », « seul les enfants » → « seuls » : « seul » placé devant un groupe pluriel
        s'accorde avec lui ; pas après un déterminant ou une copule (« le seul des survivants », « il reste seul »)."""
        for j in range(len(lus) - 2):
            f = lus[j].mot.forme.lower()
            if f not in ("seul", "seule") or j in faites:
                continue
            if j > 0 and (analyses[j - 1].upos in ("DET", "ADJ", "NUM", "AUX", "VERB")
                          or lus[j - 1].mot.forme.lower() in _COPULES_SING | _COPULES_PLUR):
                continue
            n1, a1, a2 = lus[j + 1].mot.forme.lower(), analyses[j + 1], analyses[j + 2]
            if not ((a1.upos == "NUM" and n1 not in ("1", "un", "une")) or n1 in _APRES_TOUTS):
                continue
            if a2.upos not in ("NOUN", "PROPN", "ADJ") or a2.feats.get("Number") != "Plur":
                continue
            cible = "seules" if f == "seule" or a2.feats.get("Gender") == "Fem" else "seuls"
            orig = texte[lus[j].mot.debut:lus[j].mot.fin]
            prop = _casse(cible, orig)
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < MARGES_ACCORD[mode]:
                continue
            faites[j] = Correction(lus[j].mot.debut, lus[j].mot.fin, orig, prop, "accord", 0.9, "seul",
                                   {"regle": "seul", "gain": round(gain, 3)},
                                   explication=(f"« {orig} » porte sur « {lus[j + 1].mot.forme} {lus[j + 2].mot.forme} » (pluriel) et "
                                                f"s'accorde avec lui : « {prop} »."))

    def _imperatif_pronom(self, texte, lus, analyses, faites) -> None:
        """« Sortez moi d'ici », « allez y » → « Sortez-moi », « allez-y » : à l'impératif (lu ainsi par l'analyse, et
        possible d'après le lexique), le pronom qui suit le verbe s'y rattache par un trait d'union ; pas si un
        infinitif suit le pronom (« venez nous voir » : le pronom est à l'infinitif)."""
        for j in range(len(lus) - 1):
            m, n = lus[j], lus[j + 1]
            if j in faites or j + 1 in faites or analyses[j].upos != "VERB" or analyses[j].feats.get("Mood") != "Imp":
                continue
            pronom = n.mot.forme.lower()
            if pronom not in _CLITIQUES_IMPERATIF or texte[m.mot.fin:n.mot.debut] != " ":
                continue
            if j > 0 and analyses[j - 1].upos in ("PRON", "NOUN", "PROPN", "DET", "AUX", "ADP"):
                continue                                      # « vous sortez », « que je sorte », « de sortir »
            if j + 2 < len(lus) and analyses[j + 2].upos == "VERB" and analyses[j + 2].feats.get("VerbForm") == "Inf":
                continue
            if pronom in ("le", "la", "les", "leur", "en") and j + 2 < len(lus) \
                    and analyses[j + 2].upos in ("NOUN", "PROPN", "ADJ", "NUM", "DET") or analyses[j + 1].upos == "DET":
                continue                                      # « Arrêtez la lecture », « envoyez le mot » : article, pas pronom
            if not any(l.upos == "VERB" and "Mood=Imp" in l.feats for l in self.generateur.lex.lectures(m.mot.forme.lower())):
                continue
            orig = texte[m.mot.debut:n.mot.fin]
            prop = f"{texte[m.mot.debut:m.mot.fin]}-{texte[n.mot.debut:n.mot.fin]}"
            faites[j] = faites[j + 1] = Correction(
                m.mot.debut, n.mot.fin, orig, prop, "typographie", 0.9, "imperatif_pronom", {"regle": "imperatif_pronom"},
                explication=(f"À l'impératif, le pronom qui suit le verbe s'y rattache par un trait d'union : « {prop} »."))

    def _participe_present(self, texte, lus, analyses, faites, mode) -> None:
        """Participe présent écrit pour l'adjectif verbal homophone (« très contant », « il est différant ») et l'inverse
        après « en » (« en différent de ») : règle d'école, paires fermées (PAIRES_ANT)."""
        lex = self.generateur.lex
        for j in range(1, len(lus)):
            m = lus[j]
            forme = m.mot.forme.lower()
            if j in faites or (forme not in PAIRES_ANT and forme not in PAIRES_ENT):
                continue
            prev = lus[j - 1].mot.forme.lower()
            suivant = analyses[j + 1].upos if j + 1 < len(lus) else "PUNCT"
            if forme in PAIRES_ANT and (prev in _ADVERBES_DEGRE or prev in _COPULES_SING or prev in _COPULES_PLUR):
                base = PAIRES_ANT[forme]
                feats = analyses[j].feats
                nombre = "Plur" if prev in _COPULES_PLUR else "Sing" if prev in _COPULES_SING else feats.get("Number", "Sing")
                prop = base + ("e" if feats.get("Gender") == "Fem" else "") + ("s" if nombre == "Plur" else "")
                if prop != base and not any(l.upos == "ADJ" for l in lex.lectures(prop)):
                    prop = base
                regle, expl = "adjectif_verbal", (
                    f"« {forme} » est le participe présent du verbe (invariable : « en {forme} ») ; après « {lus[j - 1].mot.forme} », "
                    f"c'est l'adjectif « {base} » qu'on écrit" + (f", accordé : « {prop} »" if prop != base else "") + ".")
            elif forme in PAIRES_ENT and prev == "en" and (
                    (lus[j + 1].mot.forme.lower() if j + 1 < len(lus) else "") in _APRES_GERONDIF
                    or suivant not in ("NOUN", "PROPN", "ADJ", "NUM")):          # pas « en excellent état »
                prop = PAIRES_ENT[forme]
                regle, expl = "participe_present", (
                    f"Après « en », c'est le participe présent, invariable : « en {prop} » ; « {forme} » est l'adjectif "
                    f"(« très {forme} »).")
            else:
                continue
            orig = texte[m.mot.debut:m.mot.fin]
            prop = _casse(prop, orig)
            gain = self._gain(texte, lus, faites, j, prop)
            if gain < MARGES_ACCORD[mode]:
                continue
            faites[j] = Correction(m.mot.debut, m.mot.fin, orig, prop, "forme_verbale", 0.9, regle,
                                   {"regle": regle, "gain": round(gain, 3)}, explication=expl)

    def _des_determinant(self, texte, lus, faites, mode) -> None:
        """« des » devant un déterminant (« des l'Association », « celle des ses parents », « des la seconde ») : jamais
        correct, « des » étant déjà « de les ». Deux lectures : la coquille pour « de », ou « dès » (= à partir de) sans
        son accent (« des sa naissance ») ; le modèle de langue écrit les départage, et doit nettement préférer l'une.
        Pas devant « le », « les » (« de le » n'existe pas : la bonne forme n'est pas prévisible) ni « un », « une »
        (« des uns et des autres »). (18/10 : 3 occurrences dans 45 000 mots de textes corrects, toutes des fautes.)"""
        for j in range(len(lus) - 1):
            m, n = lus[j], lus[j + 1]
            if m.mot.forme.lower() != "des" or m.origine != "lexique" or j in faites or j + 1 in faites:
                continue
            suivant = texte[n.mot.debut:n.mot.fin]
            if suivant.replace("’", "'") not in _DETERMINANTS_APRES_DE or not suivant[:1].islower():
                continue
            orig = texte[m.mot.debut:m.mot.fin]
            notes = {}
            for cible in ("de", "dès"):
                prop = _casse(cible, orig)
                notes[cible] = self.juge.note(self._rendu(texte, lus, faites, j, prop)) if self.juge is not None else 0.0
            base = self.juge.note(self._rendu(texte, lus, faites)) if self.juge is not None else 0.0
            cible, autre = sorted(notes, key=lambda c: -notes[c])
            gain, ecart = notes[cible] - base, notes[cible] - notes[autre]
            ambigu = ecart < MARGE_DE_DES                     # « des sa naissance » : « de » et « dès » se valent
            if self.juge is not None and (gain < max(MARGES_LM[mode], 0.0) or (ambigu and mode == "automatique")):
                continue                                      # suggestions : la meilleure lecture, l'autre dans l'explication
            prop = _casse(cible, orig)
            suite = f"{prop} {suivant}"
            if suivant.endswith(("'", "’")) and j + 2 < len(lus):
                suite += texte[lus[j + 2].mot.debut:lus[j + 2].mot.fin]      # « de l'Association »
            if cible == "de":
                explication = (f"« des » est déjà la contraction de « de les » : devant un déterminant (« {suivant} »), on écrit "
                               f"« de » : « {suite} »" + (", ou « dès » (= à partir de) si c'est le sens voulu." if ambigu else "."))
            else:
                explication = (f"« des » devant « {suivant} » n'est pas correct : « dès » (= à partir de) prend un accent grave : "
                               f"« {suite} »" + (", ou « de » si c'est le sens voulu." if ambigu else "."))
            faites[j] = Correction(m.mot.debut, m.mot.fin, orig, prop, "accord" if cible == "de" else "accent", 0.9,
                                   "des_determinant", {"regle": "des_determinant", "confiance": 0.9, "gain": round(gain, 3),
                                                       "ecart": round(ecart, 3), "juge": None},
                                   explication=explication)

    def _des_accent(self, texte, lus, analyses, faites, mode) -> None:
        """« dés » (les dés à jouer) écrit pour « dès » (= à partir de) : devant un déterminant, « que », « lors », une
        date ou un adverbe de temps, sans déterminant devant (« les dés ») ; le modèle de langue écrit confirme."""
        for j in range(len(lus) - 1):
            m, n = lus[j], lus[j + 1]
            if m.mot.forme.lower() != "dés" or m.origine != "lexique" or j in faites or j + 1 in faites:
                continue
            suivant = texte[n.mot.debut:n.mot.fin].lower()
            if not (suivant[:1].isdigit() or suivant in _APRES_DES or analyses[j + 1].upos == "DET"):
                continue
            if j > 0 and (analyses[j - 1].upos in ("DET", "NUM") or lus[j - 1].mot.forme.lower() in ("de", "d'", "d’")):
                continue                                      # « les dés », « deux dés », « jeu de dés »
            orig = texte[m.mot.debut:m.mot.fin]
            prop = _casse("dès", orig)
            gain = 0.0
            if self.juge is not None:
                gain = self.juge.note(self._rendu(texte, lus, faites, j, prop)) - self.juge.note(self._rendu(texte, lus, faites))
            if gain < max(MARGES_LM[mode], 0.0):
                continue
            faites[j] = Correction(m.mot.debut, m.mot.fin, orig, prop, "accent", 0.9, "des_accent",
                                   {"regle": "des_accent", "lm": round(gain, 3)},
                                   explication=(f"« dès » (= à partir de : « {prop} {texte[n.mot.debut:n.mot.fin]} ») prend un accent "
                                                f"grave ; « dés » avec un accent aigu, ce sont les dés à jouer."))

    def _davantage(self, texte, lus, analyses, faites, mode) -> None:
        """« d'avantage » (= d'un avantage) écrit pour « davantage » (= plus) : après un verbe, un adverbe ou un
        pronom, sans mot de quantité devant (« pas d'avantage à », « beaucoup d'avantages ») ni adjectif derrière
        (« d'avantage fiscal ») ; le modèle de langue écrit confirme (marge des homophones)."""
        for j in range(1, len(lus) - 1):
            m, n = lus[j], lus[j + 1]
            if m.mot.forme.lower() not in ("d'", "d’") or n.mot.forme.lower() != "avantage" or n.mot.debut != m.mot.fin \
                    or j in faites or j + 1 in faites:
                continue
            if lus[j - 1].mot.forme.lower() in _QUANTITES or analyses[j - 1].upos not in ("VERB", "AUX", "ADV", "PRON"):
                continue
            if j + 2 < len(lus) and analyses[j + 2].upos == "ADJ":
                continue
            orig = texte[m.mot.debut:n.mot.fin]
            prop = _casse("davantage", orig)
            gain = 0.0
            if self.juge is not None:
                base = self.juge.note(self._rendu(texte, lus, faites))
                gain = self.juge.note(self._rendu(texte, lus, faites, j + 1, prop, m.mot.debut)) - base
            if gain < MARGES_LM[mode]:
                continue
            faites[j] = faites[j + 1] = Correction(
                m.mot.debut, n.mot.fin, orig, prop, "homophone", 0.9, "davantage",
                {"regle": "contraction", "accord": "sans_objet", "p_meilleure": 1.0, "p_recue": 0.0, "tete": True, "lm": gain},
                explication=(f"« davantage » (= plus) s'écrit en un seul mot : « {prop} ». « d'avantage » veut dire "
                             f"« d'un avantage » (« il n'y a pas d'avantage à cela »)."))

    def _elisions(self, texte, lus, faites) -> None:
        """Élision oubliée devant une voyelle ou un h muet (« de Andrew », « la administration », « que il »,
        « l ouverture » sans apostrophe) ; élision abusive devant un h aspiré (« l'haricot »). Le lexique dit si le
        h est aspiré (prononciation enrichie « *h* ») et si le mot commence bien par une voyelle (pas « oui »,
        « huit », « yaourt »). Une correction couvre les deux mots : elle est rangée sous les deux indices."""
        lex = self.generateur.lex
        for j in range(len(lus) - 1):
            if j in faites or j + 1 in faites:
                continue
            m, n = lus[j], lus[j + 1]
            if m.origine == "ponctuation" or n.origine == "ponctuation":
                continue
            orig, suivant = texte[m.mot.debut:m.mot.fin], texte[n.mot.debut:n.mot.fin]
            if not suivant[:1].isalpha() or not all(ch.isalpha() or ch == "-" for ch in suivant):
                continue
            f = orig.lower()
            lectures = lex.lectures(suivant)
            if f in ("l'", "l’", "d'", "d’"):                  # élision abusive : « l'haricot » → « le haricot »
                if n.mot.debut != m.mot.fin or suivant[:1] != "h" or not lectures \
                        or not all("*h*" in l.phone_enrichi for l in lectures) \
                        or any(l.upos == "PROPN" for l in lectures) or max(l.zipf for l in lectures) < 2.5:
                    continue
                noms = [l for l in lectures if l.upos in ("NOUN", "ADJ")]
                genres = {l.traits().get("Gender") for l in noms}
                if not noms or (f[0] == "l" and (len(genres) != 1 or None in genres)):
                    continue
                plein = "de" if f[0] == "d" else "le" if genres == {"Masc"} else "la"
                prop = _casse(plein, orig) + " " + suivant
                faites[j] = faites[j + 1] = Correction(
                    m.mot.debut, n.mot.fin, orig + suivant, prop, "elision", 0.9, "h_aspire", {"regle": "h_aspire"},
                    explication=(f"« {suivant} » commence par un h aspiré : pas d'élision devant lui (ni de liaison), "
                                 f"on écrit « {prop} », comme « le hibou », « de haut »."))
                continue
            bas = suivant.lower()
            if texte[m.mot.fin:n.mot.debut] != " " or (len(suivant) == 1 and suivant not in ("à", "y")) \
                    or suivant[1:] != bas[1:] or not lectures or any(l.upos == "INTJ" for l in lectures) \
                    or (suivant[:1].isupper() and (bas[:1] == "h" or any(l.upos != "PROPN" for l in lectures)
                                                   or any(l.upos == "NOUN" for l in lex.lectures(bas)))):
                # lettre seule ; sigle (UMP, XIe, Uch-Kuduk) ; mot inconnu (Angiox : les marques ne s'élident pas
                # toujours) ; interjection (« le oh », « que euh ») ; nom propre en H (la Haye, Helmut : h aspiré
                # imprévisible) ou qui est aussi un nom commun (« de Union européenne » : c'est l'article qui manque)
                continue
            seule = len(f) <= 2 and "'" not in f               # « l », « d », « qu » : élision sans apostrophe
            if seule and not (orig.islower() or j == 0):
                continue
            if seule and j > 0 and any(ch.isdigit() for ch in texte[lus[j - 1].mot.debut:lus[j - 1].mot.fin]):
                continue                                      # « 5 l eau » : unité de mesure
            if f in ELISIONS_NOMINALES or f.endswith(" de"):
                groupe, elide = "nominale", (_casse(ELISIONS_NOMINALES[f], orig) if f in ELISIONS_NOMINALES else orig[:-2] + "d'")
            elif f in ELISIONS_VERBALES:
                groupe, elide = "verbale", _casse(ELISIONS_VERBALES[f], orig)
            elif f in ELISIONS_QUE or f.endswith(" que"):
                groupe, elide = "que", (_casse(ELISIONS_QUE[f], orig) if f in ELISIONS_QUE else orig[:-3] + "qu'")
            elif f in ELISIONS_CONDITIONNELLES:
                elide, permis = ELISIONS_CONDITIONNELLES[f]
                groupe, elide = ("verbale" if permis is None else permis), _casse(elide, orig)
            else:
                continue
            if isinstance(groupe, set):
                ok = bas in groupe
            else:
                muet = not any("*h*" in l.phone_enrichi for l in lectures) \
                    and all(l.phone[:1] in VOYELLES_PHONES for l in lectures)
                cats = {l.upos for l in lectures}
                if groupe == "nominale":
                    ok = muet and len(suivant) > 1 and bas not in SANS_ELISION and not cats <= _CATEGORIES_VIDES
                elif groupe == "verbale":
                    verbes = [l for l in lectures if l.upos in ("VERB", "AUX")]
                    if f in ("je", "j"):
                        verbes = [l for l in verbes if l.traits().get("Person") == "1"]
                    ok = muet and (bool(verbes) or bas in ("en", "y"))
                else:
                    ok = (muet or bas in ("à", "y")) and bas not in ("ou", "et", "or")
            if ok and suivant[:1].isupper() and j > 0 and texte[lus[j - 1].mot.debut:lus[j - 1].mot.fin][:1].isupper():
                ok = False                                    # « Miguel de Unamuno » : nom étranger, pas d'élision
            if not ok or self._etranger(lus, j + 1):
                continue
            prop = elide + suivant
            if seule:
                explication = f"« {orig} » devant « {suivant} » : il manque l'apostrophe de l'élision, « {prop} »."
            else:
                explication = (f"Devant « {suivant} », qui commence par {'un h muet' if bas[:1] == 'h' else 'une voyelle'}, "
                               f"« {orig} » s'élide : « {prop} ».")
            faites[j] = faites[j + 1] = Correction(m.mot.debut, n.mot.fin, orig + " " + suivant, prop, "elision", 0.9,
                                                   "elision", {"regle": "elision"}, explication=explication)

    def _contractions(self, texte, lus, analyses, faites, ex) -> None:
        """« ma » / « ta » / « la » devant un participe → « m'a » / « t'a » / « l'a » ; « ni » entre un pronom sujet et
        un verbe → « n'y » : contractions que le lexique ne donne pas comme homophones."""
        lex = self.generateur.lex
        for j, m in enumerate(lus):
            f = m.mot.forme.lower()
            if f not in CONTRACTIONS or j in faites or j not in ex or j + 1 >= len(lus):
                continue
            suivant = lus[j + 1].mot.forme.lower()
            toutes = lex.lectures(suivant)
            verbes = [l for l in toutes if l.upos in ("VERB", "AUX")]
            if not verbes or (f == "la" and analyses[j + 1].upos not in ("VERB", "AUX")):
                continue                                      # « la » est aussi un pronom objet : « en la touchant »
            if f == "ni":
                ok = (j > 0 and lus[j - 1].mot.forme.lower() in ("il", "elle", "on", "ils", "elles", "je", "tu",
                                                                 "nous", "vous", "qui", "y", "n")
                      and all(l.traits().get("VerbForm") == "Fin" for l in verbes))
                explication = (f"« ni » (= et pas non plus) ne va pas ici : c'est « n'y » (ne + y), comme dans "
                               f"« il n'y a pas » : « {CONTRACTIONS[f]} {suivant} ».")
            else:
                autres = [l for l in toutes if l.upos in ("NOUN", "ADJ")]
                ok = (all(l.traits().get("VerbForm") == "Part" and l.traits().get("Tense") == "Past" for l in verbes)
                      and all(l.zipf < max(v.zipf for v in verbes) - 1.0 for l in autres))   # « la pensée », « la mort »
                explication = (f"« {f} » (déterminant) ne peut pas précéder le participe « {suivant} » : c'est "
                               f"« {CONTRACTIONS[f]} » (pronom + verbe avoir ; on peut dire "
                               f"« {CONTRACTIONS[f][:-1]}avait »).")
            if ok:
                faites[j] = Correction(m.mot.debut, m.mot.fin, m.mot.forme, _casse(CONTRACTIONS[f], m.mot.forme),
                                       "homophone", float(analyses[j + 1].confiance), "contraction",
                                       {"regle": "contraction", "accord": "sans_objet", "p_meilleure": 1.0,
                                        "p_recue": 0.0, "tete": True}, explication=explication)

    def _majuscules(self, texte, lus, analyses, faites) -> None:
        """Majuscules qui ont perdu leur accent : « A » préposition → « À », « Etat » → « État »."""
        from lectura_nlp_fr.analyseur.structures import TypeMot

        lex = self.generateur.lex
        for j, m in enumerate(lus):
            f = m.mot.forme
            if j in faites or m.mot.type is not TypeMot.MOT or not f[:1].isupper():
                continue
            if f == "A" and (analyses[j].upos == "ADP" or self._a_initial(lus, analyses, j)):
                faites[j] = Correction(m.mot.debut, m.mot.fin, f, "À", "accent", float(analyses[j].confiance),
                                       "A_majuscule", {"regle": "A_majuscule"},
                                       explication="« À » (préposition) garde son accent en majuscule ; « A » sans "
                                                   "accent est le verbe avoir (« il a »).")
            elif f[:1] == "E" and len(f) > 2 and f[1:].islower() and lex.validite(f.lower()) == "inconnue":
                fo = lex.forme("é" + f[1:], avec_lectures=False)
                propres = {l.upos for l in lex.lectures(f)} & {"PROPN"}
                if propres and (not any(l.upos == "PROPN" for l in lex.lectures("É" + f[1:]))
                                or lex.frequence(f) >= lex.frequence("É" + f[1:]) - 0.5):
                    continue                                  # nom propre tel quel : Eden Park, Eclipse, Eric
                if propres and fo is None:
                    fo = lex.forme("É" + f[1:], avec_lectures=False)   # « Egypte », « Etienne » : nom propre accentué
                if fo and (not fo.propre or propres) and fo.validite in VALIDES:
                    faites[j] = Correction(m.mot.debut, m.mot.fin, f, "É" + f[1:], "accent", 1.0, "E_majuscule",
                                           {"regle": "E_majuscule"},
                                           explication=f"Les majuscules prennent les accents : « É{f[1:]} ».")

    def _a_initial(self, lus, analyses, j: int) -> bool:
        """« 23 mars : A Paris », « A la fin des tours », « A chacun son cinéma » : « A » en tête de proposition
        (début, ou après « : », « ; », « . », « ( », « » ») devant un nom propre, un déterminant, un pronom ou un
        nombre : la préposition « À », quoi qu'en dise l'analyse ; jamais devant une forme verbale (« A participé »)."""
        if j + 1 >= len(lus) or (j > 0 and lus[j - 1].mot.forme not in (":", ";", ".", "(", "»", "«", "!", "?", "–", "—", "*")):
            return False
        suivant = lus[j + 1]
        bas = suivant.mot.forme.lower()
        if not bas[:1].isalnum():
            return False
        if any(l.upos in ("VERB", "AUX") for l in self.generateur.lex.lectures(bas)):
            return False
        return analyses[j + 1].upos in ("PROPN", "DET", "PRON", "NUM") or bas in ("la", "le", "les", "l'", "l’", "chacun",
                                                                                   "chaque", "partir", "peine", "cette", "ce")

    def _categorie_contredite(self, recue: str, probas: dict, a) -> str | None:
        """Catégorie prédite (phrase écrite lue en entier) sûre et incompatible avec toute lecture de la graphie
        reçue : la seule graphie candidate de cette catégorie, s'il y en a une."""
        if a is None or a.confiance < P_UPOS_MIN or a.upos not in CATEGORIES:
            return None
        lex = self.generateur.lex
        if a.upos in {l.upos for l in lex.lectures(recue.lower())}:
            return None
        cands = [g for g in probas if g.lower() != recue.lower()
                 and a.upos in {l.upos for l in lex.lectures(g.lower())} and mot(g)]
        return cands[0] if len(cands) == 1 else None

    def _verdict_genre(self, j, lr, lp, formes, analyses, proposee: str = "") -> str:
        """Couple de genre d'un nom (ami / amie, deux lemmes dans LeXiK) : seul un déterminant non élidé en décide."""
        nr = [l for l in lr if l.upos == "NOUN"]
        np_ = [l for l in lp if l.upos == "NOUN"]
        if not nr or not np_ or analyses is None or formes is None:
            return "sans_objet"
        gr = {l.traits().get("Gender") for l in nr} - {None}
        gp = {l.traits().get("Gender") for l in np_} - {None}
        if len(gr) != 1 or len(gp) != 1 or gr == gp:
            return "sans_objet"
        dets = [d for d, a in enumerate(analyses) if a.tete == j and a.relation == "det" and d < j]
        if not dets and j > 0 and analyses[j - 1].upos == "DET":
            dets = [j - 1]
        if not dets:
            return "muet"
        d = formes[dets[-1]].lower()
        if d in ("mon", "ton", "son") and formes[j][:1].lower() in "aeiouyàâäéèêëîïôöùûüœæh":
            return "contre"
        gd = {l.traits().get("Gender") for l in self.generateur.lex.lectures(d) if l.upos == "DET"} - {None}
        if len(gd) != 1:
            return "muet"
        if gd != gp:
            return "contre"
        if analyses[j].upos != "NOUN" or not (_couple_genre(formes[j].lower(), proposee.lower())
                                                or _couple_genre(proposee.lower(), formes[j].lower())):
            return "muet"                                     # « sa dit » → dix ? pas un couple ami / amie : la tête ne
                                                              # décide pas seule (hauteur / auteur, boue / bout restent « muets »)
        return "pour"

    def _infinitif(self, forme: str) -> bool:
        lectures = self.generateur.lex.lectures(forme.lower()) if self.generateur is not None else []
        return any(l.upos in ("VERB", "AUX") and l.traits().get("VerbForm") == "Inf" for l in lectures)

    def _verdict_accord(self, attentes: dict, j: int, recue: str, proposee: str, formes=None, analyses=None) -> str:
        """Ce que l'analyse dit d'un homophone du même lemme (flexion) : « pour », « contre », « muet » ; les paires
        d'autres lemmes (est / et) ne la concernent pas (« sans_objet »)."""
        lex = self.generateur.lex if self.generateur is not None else None
        if lex is None:
            return "sans_objet"
        lr, lp = lex.lectures(recue.lower()), lex.lectures(proposee.lower())
        paires = [(a, b) for a in lr for b in lp if a.lemme == b.lemme and a.upos == b.upos]
        if not paires:
            return self._verdict_genre(j, lr, lp, formes, analyses, proposee)
        att = attentes.get(j)
        diffs = [{k for k in set(a.traits()) | set(b.traits()) if a.traits().get(k) != b.traits().get(k)}
                 for a, b in paires]
        if att is not None and att.forme_cible:
            return "pour" if proposee.lower() == att.forme_cible else "contre"
        if any(d and d <= set(TRAITS_FLEXION) for d in diffs):
            if att is None or not att.traits:
                return "muet"
            upos = paires[0][0].upos
            if self.accordeur.satisfait(recue, upos, att.traits):
                return "contre"
            return "pour" if self.accordeur.satisfait(proposee, upos, att.traits) else "contre"
        return "sans_objet"

    def _ligatures(self, texte, lus, faites) -> None:
        """« oe » / « ae » en deux lettres là où la norme soude la ligature (« Soeurs », « Oedipe », « l'Oeuvre »,
        « mains-d'oeuvre », « caecum ») : tous les mots, majuscules et composés compris, quand la forme ligaturée est
        dans le lexique et au moins deux fois plus fréquente que la forme reçue (« moelle », « Goethe », « Boeing »,
        « foehn », « vitae », « phoenix » restent)."""
        lex = self.generateur.lex
        for j, m in enumerate(lus):
            if j in faites or m.origine == "ponctuation":
                continue
            forme = texte[m.mot.debut:m.mot.fin]
            bas = forme.lower()
            if ("oe" not in bas and "ae" not in bas) or not all(ch.isalpha() or ch in "-'’" for ch in forme) \
                    or self._etranger(lus, j):
                continue
            lie = forme
            for deux, une in (("oe", "œ"), ("Oe", "Œ"), ("OE", "Œ"), ("ae", "æ"), ("Ae", "Æ"), ("AE", "Æ")):
                lie = lie.replace(deux, une)
            if lie == forme or (lex.validite(lie) not in VALIDES and lex.validite(lie.lower()) not in VALIDES):
                continue
            f_lie, f_forme = max(lex.frequence(lie), lex.frequence(lie.lower())), max(lex.frequence(forme), lex.frequence(bas))
            if f_lie < f_forme + 0.3 or (forme[:1].isupper() and not _premier_mot(lus, j) and f_forme == 0 and f_lie < 2.0):
                continue                                      # nom propre inconnu, ligaturé rare (« Oersted » → Œrsted)
            lig = "œ" if "œ" in lie.lower() else "æ"
            exemples = "« cœur », « œuf », « sœur »" if lig == "œ" else "« ex æquo », « cæcum »"
            faites[j] = Correction(m.mot.debut, m.mot.fin, forme, lie, "typographie", 1.0, "ligature_oe",
                                   {"regle": "ligature_oe"},
                                   explication=f"« {forme} » s'écrit avec la ligature « {lig} » (lettres soudées) : "
                                               f"« {lie} », comme {exemples}.")

    def _hors_lexique(self, texte, lus, examinables, faites, mode) -> None:
        for j, m, validite in examinables:
            forme = m.mot.forme
            if j in faites:
                continue                                      # ligature déjà corrigée
            if validite == "inconnue" and any(ch in LIGATURES for ch in forme):
                plat = unicodedata.normalize("NFKC", forme)   # diﬃcile → difficile
                if self.generateur.lex.validite(plat.lower()) in VALIDES:
                    faites[j] = Correction(m.mot.debut, m.mot.fin, forme, plat, "typographie", 1.0, "ligature",
                                           {"regle": "ligature"},
                                           explication=f"« {forme} » contient une ligature typographique (ﬁ, ﬂ, ﬀ…) "
                                                       f"à la place des lettres : « {plat} ».")
                    continue
            if validite == "variante":            # graphie ancienne ou concurrente : suggestion seulement
                usuelle = self.generateur.lex.usuelle(forme.lower())
                if usuelle and usuelle != forme.lower() and self._rectifiee(forme.lower(), usuelle):
                    continue                          # « gout », « paraitre » : orthographe rectifiée de 1990, admise
                if usuelle and usuelle != forme.lower() and _sans_accents(usuelle) == _sans_accents(forme.lower()):
                    # coquille d'accent connue du lexique (« trés », « déja », lectura-lexicon ≥ 0.3) : les deux modes
                    faites[j] = Correction(m.mot.debut, m.mot.fin, forme, _casse(usuelle, forme), "accent", 1.0,
                                           "accent : usuelle du lexique", {"regle": "accent_usuelle"},
                                           explication=f"« {forme} » s'écrit « {_casse(usuelle, forme)} » : attention à l'accent.")
                    continue
                if usuelle and usuelle != forme.lower() and ("œ" in usuelle or "œ" in forme.lower()):
                    faites[j] = Correction(m.mot.debut, m.mot.fin, forme, _casse(usuelle, forme), "typographie", 1.0,
                                           "ligature_oe", {"regle": "ligature_oe"},
                                           explication=f"« {forme} » s'écrit « {_casse(usuelle, forme)} » (ligature œ).")
                    continue
                if usuelle and usuelle != forme.lower():
                    # lectura-lexicon ≥ 0.3.3 : une variante avec usuelle est une faute d'orthographe connue
                    # (« parmis », « mourrir », « parceque », « enfans ») ; les graphies rectifiées sont admises
                    faites[j] = Correction(m.mot.debut, m.mot.fin, forme, _casse(usuelle, forme), "lexical", 1.0,
                                           "variante", {"regle": "variante"},
                                           explication=f"« {forme} » s'écrit « {_casse(usuelle, forme)} ».")
                    continue
            if validite != "inconnue":
                self._accent_lexique(texte, lus, faites, j, m, forme, mode)
                continue
            if any(ch not in ALPHABET for ch in forme.lower()):
                continue                                      # « địch », « Tiếng » : lettres d'une autre langue
            bas = forme.lower()
            if bas.endswith("s") and len(bas) > 3 and self.generateur.lex.validite(bas[:-1]) in VALIDES \
                    and any(l.upos in ("NOUN", "ADJ") for l in self.generateur.lex.lectures(bas[:-1])):
                continue                                      # « gariguettes » : pluriel régulier d'un mot connu
            cands = self.generateur.hors_lexique(forme, m.phone)
            if not cands:
                continue
            for c in cands:
                cout = COUT.get((c.origine, c.distance), 3.0)
                if c.origine == "scission" and "'" in c.forme and c.zipf >= 4.0:
                    cout = COUT[("accent", 1)]                # apostrophe oubliée devant un mot courant (« cest », « jai »,
                                                              # « quil ») : la faute la plus banale, au prix d'un accent
                c.score = self.juge.note(self._rendu(texte, lus, faites, j, _casse(c.forme, forme))) - cout
            exacts = [c for c in cands if c.origine == "phone" and c.distance == 0]
            if exacts and len(bas) >= LONGUEUR_SON:
                # un candidat se prononce comme ce qui a été écrit (« fote » → faute, au timbre près) : ceux qui se
                # prononcent autrement (« fête ») sont pénalisés, le scripteur a écrit ce qu'il entendait ; entre
                # candidats de même son, le plus proche par les lettres (« reflettent » → reflètent, pas reflète)
                for c in cands:
                    if c in exacts:
                        c.score -= COUT_LETTRE_SON * _levenshtein(bas, c.forme.lower())
                    elif c.origine != "accent" and not (c.origine in ("scission", "elision") and "'" in c.forme):
                        c.score -= PENALITE_SON               # une apostrophe ne change pas le son (« cest » → c'est, pas ceste)
            accents = [c for c in cands if c.origine == "accent"]
            if accents:
                # les lettres reçues sont le meilleur indice du nombre et de la personne : quand un candidat ne diffère
                # que par les accents (« intérmédiaires » → intermédiaires, « empèchent » → empêchent), les formes du
                # même lemme à d'autres lettres (intermédiaire, empêche) s'effacent ; et « août » plutôt que « aout ».
                # Pas si l'accent change la fin du mot (« appellé » → appelle ? non : appelé reste en lice)
                # (la cédille ne change pas la terminaison : « annonca » → annonça, pas annonce)
                lemmes_accent = {l.lemme for a in accents
                                 if a.forme.lower()[-2:].replace("ç", "c") == bas[-2:].replace("ç", "c")
                                 for l in self.generateur.lex.lectures(a.forme.lower())}
                cands = [c for c in cands if c.origine == "accent"
                         or not (lemmes_accent & {l.lemme for l in self.generateur.lex.lectures(c.forme.lower())})]
                cands = [c for c in cands if not (c.origine == "accent" and any(
                    a is not c and self._rectifiee(c.forme.lower(), a.forme.lower()) for a in accents))]
                cands = [c for c in cands if not (c.origine == "ortho" and c.distance >= 2)]
                # « reactivité » → activité ? deux lettres à ôter alors qu'un accent suffit : ces voisins s'effacent
            for sc in [c for c in cands if c.origine == "scission" and not accents]:
                # « identifieret » : la coupe « identifier et » passe devant « identifier » (ôter les lettres d'un mot-outil
                # est moins probable qu'oublier une espace) ; jamais devant un simple accent (« reactivité »)
                parties = [p.rstrip("'") for p in sc.forme.lower().replace("'", "' ").split()]
                for c in cands:
                    if c.origine == "ortho" and c.forme.lower() in parties and c.score > sc.score:
                        sc.score = c.score + 0.1
            cands.sort(key=lambda c: -c.score)
            accent = cands[0].origine == "accent"
            son_exact = cands[0].origine == "phone" and cands[0].distance == 0 and len(bas) >= LONGUEUR_SON
            # marge sur le premier concurrent d'une autre origine : « grâce » / « grâces » se départagent après
            scission = cands[0].origine == "scission"
            elision = cands[0].origine == "elision"
            if forme[:1].isupper() and j > 0 and not scission and not elision and not accent:
                continue                                      # « * Warthog », « * Encyclopaedia » : après une puce, un nom propre est possible
            lemmes = {l.lemme for l in self.generateur.lex.lectures(cands[0].forme.lower())}
            if scission or elision:
                # « occupationde » → « occupation de » : les concurrents qui ne sont qu'une des deux parties (« occupation »,
                # « occupations ») ne comptent pas, oublier une espace est plus probable qu'ajouter deux lettres ;
                # de même « lortograf » → « l'orthographe » face à « orthographe »
                parties = [p.rstrip("'") for p in cands[0].forme.lower().replace("'", "' ").split()]
                lemmes = {l.lemme for p in parties for l in self.generateur.lex.lectures(p)} | set(parties)
            autres = [c for c in cands[1:] if not (accent and c.origine == "accent")
                      and not (lemmes and lemmes & ({l.lemme for l in self.generateur.lex.lectures(c.forme.lower())} | {c.forme.lower()}))]
            marge = cands[0].score - (autres[0].score if autres else cands[0].score - 3.0)
            if not autres and cands[0].origine == "ortho" and len(cands[0].forme) <= len(bas) - 2 \
                    and not any(bas[i:i + 2] == bas[i + 2:i + 4] for i in range(len(bas) - 3)):
                continue                                      # seul candidat, plus court de deux lettres : un dérivé que le lexique
                                                              # ignore (« stégosauriens » → stégosaures, « authentifieurs » →
                                                              # authentifier, « réingestion » → ingestion) plutôt qu'une faute ;
                                                              # sauf syllabe doublée (« tardivemenent » → tardivement) (18/10)
            if marge >= (MARGES_ACCENT if accent else MARGES_SON if son_exact else MARGES_SCISSION if scission or elision
                         else MARGES_HORS_LEXIQUE)[mode]:
                explication = ""
                if accent:
                    explication = (f"« {forme} » n'existe pas sans ses accents : on écrit « {_casse(cands[0].forme, forme)} »"
                                   " (les accents font partie de l'orthographe du mot).")
                elif son_exact:
                    explication = (f"« {forme} » n'est pas dans le dictionnaire ; le mot qui se prononce ainsi et qui "
                                   f"convient dans la phrase s'écrit « {_casse(cands[0].forme, forme)} ».")
                elif cands[0].origine == "scission":
                    explication = (f"« {forme} » : deux mots collés" + (" (apostrophe oubliée)" if "'" in cands[0].forme else "")
                                   + f" : « {_casse(cands[0].forme, forme)} ».")
                elif cands[0].origine == "elision":
                    clitique, reste = cands[0].forme.split("'", 1)
                    explication = (f"« {forme} » : apostrophe oubliée après « {clitique} », et le mot qui suit s'écrit "
                                   f"« {reste} » : « {_casse(cands[0].forme, forme)} ».")
                prop = _recoller(cands[0].forme, forme) if scission else _casse(cands[0].forme, forme)
                faites[j] = Correction(m.mot.debut, m.mot.fin, forme, prop,
                                       "accent" if accent else "hors_lexique",
                                       marge, "; ".join(f"{c.forme} {c.score:.1f}" for c in cands[:3]),
                                       {"marge": marge, "origine": cands[0].origine,
                                        "regle": "accent_manquant" if accent else "son_exact" if son_exact else cands[0].origine},
                                       explication=explication)

    def _rectifiee(self, forme: str, classique: str) -> bool:
        """``forme`` est l'orthographe rectifiée (1990) de ``classique`` : drapeau du lexique (lectura-lexicon ≥ 0.3.2,
        ``rectifiee``), sinon le seul circonflexe sur i / u (gout / goût, paraitre / paraître)."""
        marque = getattr(self.generateur.lex, "rectifiee", None)
        if marque is not None:
            try:
                return bool(marque(forme))
            except Exception:
                pass
        return forme == classique.replace("î", "i").replace("û", "u")

    def _accent_lexique(self, texte, lus, faites, j, m, forme: str, mode: str) -> None:
        """Forme que LeXiK accepte mais rare (« trés », « déja », « carriere », « medias »), dont la forme accentuée de
        mêmes lettres est bien plus fréquente (zipf + 1,5) : accent manquant ou déplacé, confirmé par le modèle de
        langue. Pas si la forme reçue est un verbe d'un autre lemme (« posté », « retraité » ne sont pas « poste »)."""
        bas = forme.lower()
        lex = self.generateur.lex
        zipf = lex.frequence(bas)
        if zipf >= ZIPF_ACCENT or forme[:1].isupper() and not _premier_mot(lus, j):
            return
        if forme[:1].isupper() and j + 1 < len(lus) and lus[j + 1].mot.forme[:1].isupper():
            return                                            # « Gene Vincent », « Dela guerre » : nom propre probable
        if forme[:1].isupper() and any(l.upos == "PROPN" for l in lex.lectures(forme)):
            zipf = max(zipf, lex.frequence(forme))            # « Equipe » est aussi un nom propre : l'écart se mesure à lui
        squelette = _sans_accents(bas)
        lectures = lex.lectures(bas)
        if any(l.upos in ("VERB", "AUX") for l in lectures) \
                or (bas.endswith(("é", "és", "ée", "ées")) and any(l.upos == "ADJ" for l in lectures)):
            return                                # « chiffré », « posté », « notés » : formes verbales légitimes
        meilleur = None
        for v in lex.voisins_orthographiques(bas, distance_max=1, limite=30, validite_min="proposable"):
            cle = v.ortho.lower()
            if v.propre or cle == bas or _sans_accents(cle) != squelette or v.zipf - zipf < ECART_ZIPF_ACCENT:
                continue
            if self._rectifiee(bas, cle):
                continue                              # « gout », « paraitre » : orthographe rectifiée de 1990, admise
            if meilleur is None or v.zipf > meilleur.zipf:
                meilleur = v
        if meilleur is None or self.juge is None:
            return
        gain = self.juge.note(self._rendu(texte, lus, faites, j, _casse(meilleur.ortho, forme))) \
            - self.juge.note(self._rendu(texte, lus, faites, j, forme))
        marge = MARGES_ACCENT_LEXIQUE[mode]
        if meilleur.zipf - zipf < ECART_ZIPF_ACCENT_SUR:
            marge = max(marge, 1.0)                           # écart de fréquence modeste : le modèle de langue doit trancher net
        if gain < marge:
            return
        faites[j] = Correction(m.mot.debut, m.mot.fin, forme, _casse(meilleur.ortho, forme), "accent", gain,
                               f"accent : {meilleur.ortho} (zipf {meilleur.zipf:.1f}) plutôt que {bas} ({zipf:.1f})",
                               {"gain": gain, "regle": "accent_lexique", "zipf": zipf, "zipf_cible": meilleur.zipf},
                               explication=f"« {forme} » s'écrit « {_casse(meilleur.ortho, forme)} » : "
                                           "attention à l'accent.")

    def _homophones(self, texte, lus, deja, faites, seuil, p_max: float = 1.0, attentes: dict | None = None,
                    analyses_dual=None, collecte: bool = False, marge_lm: float = -1e9, lm_fort: float = 1e9,
                    refusees: dict | None = None, marge_juge: float = -1e9, juge_fort: float = 1e9,
                    juge_muet: float = 1e9, juge_muet_lm: float = 1e9, lm_muet: float = 1e9) -> None:
        attentes = attentes or {}
        refusees = refusees or {}
        formes = [faites[i].proposition if i in faites else m.mot.forme for i, m in enumerate(lus)]
        cles = [self.chaine._cle_lue(m) or "" for m in lus]
        types = ["p" if m.origine == "ponctuation" else "m" for m in lus]
        # Premier passage : les mots à relire en prononciation seule (tête de graphie, ou flexions homophones du
        # lexique jugées par les traits) ; puis une seule analyse pour toutes ces variantes de la phrase (graphe par
        # lot ; sinon une analyse par mot), les mots déjà corrigés restant en écrit seul.
        examens = []
        for j, m in enumerate(lus):
            if j in faites or not self._examinable(m, cles[j], j, lus) or m.mot.debut in deja:
                continue
            tete = len(self.analyseur.graphies_candidates(cles[j])) >= 2
            variantes = []
            if not tete:
                if self.generateur is None:
                    continue
                variantes = [c for c in self.generateur.flexions(m.mot.forme, m.phone, homophones=True)
                             if _son(c.phone) == _son(m.phone)]
                if not variantes:
                    continue
            examens.append((j, tete, variantes))
        if not examens:
            return
        canaux = ["ortho" if i in faites else self.contexte for i in range(len(lus))]
        details_examens = self.analyseur.analyser_variantes(
            formes, cles, canaux, types, [(j, cles[j] if tete else "") for j, tete, _v in examens])
        for (j, tete, variantes), detail in zip(examens, details_examens):
            m = lus[j]
            if j in faites:
                continue
            recue = m.mot.forme
            if tete:
                probas = detail.graphies
            else:
                probas = {g: self._p_traits(detail, g) for g in [recue] + [c.forme for c in variantes]}
            p_recue = max((p for g, p in probas.items() if g.lower() == recue.lower()), default=None)
            if p_recue is None:
                continue                          # graphie reçue inconnue de la tête : on ne juge pas
            meilleure = max(probas, key=probas.get)
            regle = "tete" if tete else "traits"
            verdict = "sans_objet"
            if meilleure.lower() != recue.lower():
                # flexion du même lemme : l'analyse doit la justifier (sujet, déterminant, nom…), sinon on s'abstient ;
                # justifiée, elle passe sans condition de probabilité (comme un accord)
                verdict = self._verdict_accord(attentes, j, recue, meilleure, formes, analyses_dual)
            lm = 0.0
            if self.juge is not None and meilleure.lower() != recue.lower() and verdict != "pour":
                # second juge : « Le 6 met 2011 », « le coup d'un tel projet » sont sûrs pour la tête de graphie,
                # mais pas pour le modèle de langue écrit ; très net, il ouvre aussi une seconde voie (lm_fort)
                lm = self.juge.note(self._rendu(texte, lus, faites, j, _casse(meilleure, recue))) \
                    - self.juge.note(self._rendu(texte, lus, faites, j, recue))
            jg = None
            if self.juge_homophones is not None and meilleure.lower() != recue.lower() and verdict != "pour":
                # troisième juge : le juge des homophones du transducer lit la phrase entière dans les deux sens ;
                # quand il connaît le couple, il a un veto (marge_juge) et, très net, ouvre une troisième voie
                jg = self.juge_homophones.note(formes, j, recue, meilleure)
            jg_veto, jg_fort = jg is not None and jg < marge_juge, jg is not None and jg >= juge_fort
            if verdict == "pour" and refusees.get(j, "").lower() == meilleure.lower():
                continue                                      # accord déjà refusé par le modèle de langue (« nous est présenté »)
            if verdict == "pour":
                regle = "accord"
            elif meilleure.lower() == recue.lower() or probas[meilleure] - p_recue < seuil \
                    or (p_recue > p_max and lm < lm_fort and not jg_fort) or lm < marge_lm or jg_veto \
                    or verdict == "contre" or (verdict == "muet" and not collecte
                                               and not (jg is not None and jg >= juge_muet)
                                               and not (jg is not None and jg >= juge_muet_lm and lm >= lm_muet)):
                # la catégorie prédite en lisant la phrase écrite contredit la graphie reçue (« a chaque fois » :
                # préposition) : seule une graphie homophone de cette catégorie convient
                alt = self._categorie_contredite(recue, probas, analyses_dual[j]) if analyses_dual else None
                if alt is None:
                    continue
                meilleure, regle, verdict = alt, "categorie", "sans_objet"
            if self.generateur is not None and not homophone_permis(self.generateur.lex, recue, meilleure):
                continue
            if j > 0 and lus[j - 1].mot.forme.lower() in CLITIQUES and self._infinitif(recue) \
                    and not self._infinitif(meilleure):
                continue                                      # « les ranger » : pronom + infinitif, pas un nom
            if meilleure.lower() == "des" and j > 0 and analyses_dual is not None and analyses_dual[j - 1].upos == "NUM":
                continue                                      # « deux dés rouges » : après un nombre, le nom reste
            if regle == "categorie":
                lm, jg = 0.0, None                            # règle de catégorie : pas jugée par le modèle de langue
            explication = ""
            if verdict == "pour":
                att = attentes.get(j) if attentes else None
                if att is not None and not _couple_genre(recue.lower(), meilleure.lower()):
                    explication = Accordeur._expliquer(recue, meilleure, att)
                else:                                         # « une ami » → amie : le genre, pas le nombre
                    # couple de genre tranché par le déterminant (`_verdict_genre`, « sa dit » → « dite ») : pas
                    # d'attente de l'analyse (plantage KeyError signalé par Module NLP le 17/10)
                    det = formes[j - 1] if j > 0 and analyses_dual is not None and analyses_dual[j - 1].upos == "DET" else ""
                    gp = {l.traits().get("Gender") for l in self.generateur.lex.lectures(meilleure.lower())
                          if l.upos == "NOUN"} - {None}
                    genre = GENRE.get(next(iter(gp)), "") if len(gp) == 1 else ""
                    explication = ((f"Après « {det} »" if det else f"Ici") + (f", le nom est au {genre}" if genre else ", le nom change de genre")
                                   + f" : « {meilleure} » (« {recue} » est l'autre forme du couple).")
            upos = max(detail.upos, key=detail.upos.get) if detail.upos else ""
            if regle == "categorie":
                upos = analyses_dual[j].upos
                explication = (f"Dans cette phrase, « {recue} » est {_article(CATEGORIES[upos])}"
                               f" ; cette catégorie s'écrit « {meilleure} ».")
                astuce = ASTUCES.get(tuple(sorted((recue.lower(), meilleure.lower()))))
                if astuce:
                    explication += " " + astuce
            faites[j] = Correction(m.mot.debut, m.mot.fin, recue, _casse(meilleure, recue), "homophone",
                                   probas[meilleure] - p_recue,
                                   f"p({meilleure}) = {probas[meilleure]:.2f}, p({recue}) = {p_recue:.2f} ({regle})",
                                   {"p_meilleure": probas[meilleure], "p_recue": p_recue, "tete": tete,
                                    "accord": verdict, "upos": upos, "regle": regle, "lm": round(lm, 3),
                                    "juge": None if jg is None else round(jg, 3),
                                    "upos_dual": analyses_dual[j].upos if analyses_dual else "",
                                    "p_upos": float(analyses_dual[j].confiance) if analyses_dual else 0.0},
                                   explication=explication)
            if not collecte:
                formes[j] = faites[j].proposition

    def _p_traits(self, detail, forme: str) -> float:
        """Probabilité, d'après les traits prédits par le tagger, de la meilleure lecture de ``forme``."""
        meilleure = 0.0
        for l in self.generateur.lex.lectures(forme.lower()):
            if detail.upos.get(l.upos, 0.0) < 0.05 and not ({l.upos, max(detail.upos, key=detail.upos.get)}
                                                            <= {"AUX", "VERB"}):
                continue
            p = 1.0
            for k, v in (t.split("=", 1) for t in l.feats.split("|") if "=" in t):
                if k in TRAITS_FLEXION and k in detail.traits:
                    p *= detail.traits[k].get(v, 0.0)
            meilleure = max(meilleure, p)
        return meilleure

    def _flexions_audibles(self, texte, lus, examinables, faites, mode, attentes: dict | None = None) -> None:
        """Une à une (la meilleure de la phrase, puis on rejuge), par le modèle de langue sur la phrase entière.
        Les flexions (un / une, est / sont) que l'analyse justifie sont déjà faites (``_accords``) ; celles qu'elle
        ne justifie pas ne sont gardées qu'en collecte (mesure « accord » = « muet »)."""
        attentes = attentes or {}
        flexions = {j: ([] if mode != "collecte" or j in attentes else self.generateur.flexions(m.mot.forme, m.phone))
                    + self.generateur.quasi_homophones(m.mot.forme, m.phone) for j, m, v in examinables
                    if v != "inconnue" and m.origine == "lexique" and j not in faites}
        flexions = {j: c for j, c in flexions.items() if c}
        for _ in range(3):
            base = self.juge.note(self._rendu(texte, lus, faites))
            gain, choix = 0.0, None             # excès sur la marge
            for j, cands in flexions.items():
                if j in faites:
                    continue
                forme = lus[j].mot.forme
                for c in cands:
                    g = self.juge.note(self._rendu(texte, lus, faites, j, _casse(c.forme, forme))) - base
                    # gain au-delà de la marge propre à l'origine (quasi-homophone : marge plus basse)
                    exces = g - (MARGES_QUASI if c.origine == "quasi" else MARGES_FLEXION)[mode]
                    if exces > gain:
                        gain, choix = exces, (j, c)
            if choix is None:
                break
            j, c = choix
            m = lus[j]
            faites[j] = Correction(m.mot.debut, m.mot.fin, m.mot.forme, _casse(c.forme, m.mot.forme),
                                   "quasi_homophone" if c.origine == "quasi" else "flexion", gain,
                                   f"+{gain:.1f} (log10) au-delà de la marge, sur {m.mot.forme}",
                                   {"gain": gain, "accord": "sans_objet" if c.origine == "quasi" else "muet"})

    @staticmethod
    def _examinable(m, cle: str, j: int, lus=None) -> bool:
        from lectura_nlp_fr.analyseur.structures import TypeMot

        if not cle or m.origine != "lexique" or m.mot.type is not TypeMot.MOT or m.mot.nature:
            return False
        forme = m.mot.forme
        if not forme[:1].isalpha():                          # clitique inversé (« -tu »), élision isolée
            return False
        if not mot(forme):                                   # nombre, locution (« en train »), élision « l »
            return False
        return not (forme[:1].isupper() and not _premier_mot(lus, j))   # nom propre ou sigle : on ne touche pas
