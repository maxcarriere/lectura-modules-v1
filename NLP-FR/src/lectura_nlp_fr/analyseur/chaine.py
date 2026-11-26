# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""La chaîne complète, sens lecture : texte → analyse → prononciation → alignement linéaire."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from functools import cache
from importlib import resources

from .alignement import (
    CLITIQUE,
    COLLE,
    ELISION,
    ENCHAINEMENT,
    ESPACE,
    LIAISON_,
    SYLLABE,
    MotAligne,
    PhraseAlignee,
    commence_par_voyelle,
    decomposer,
    devant_consonne,
    enchainer,
    est_prononce,
    lier,
)
from .analyse import Analyse, Analyseur, Couple, Entree, Lexique, ModeleDeMot, accord, choisir
from .decoupage import TABLES_PHONE
from .e_caduc import SCHWA, avec_schwa_final, chutes, restaurer, sans_schwas
from .formules import reconnaitre, reconnaitre_phone
from .formules.nombres import ELEMENTS as ELEMENTS_NOMBRE
from .formules.detection import detecter_formules
from .formules.phone import mot_de
from .index_phone import LIEE as LIEE_
from .index_phone import MOT as MOT_
from .index_phone import IndexPhone, alternatives, cle_de, forme_liee
from .liaisons import LECTURE, MotAnalyse, Politique, jonction
from .recomposition import AMBIGU, LIAISON, recomposer
from . import supplement
from .structures import Mot, TypeMot
from .tokeniseur import tokeniser, tokeniser_phone

# Longueur maximale, en mots, d'un mot composé à espace.
_MAX_MOTS_COMPOSE = 5


@cache
def _mots_composes_a_espace() -> frozenset[str]:
    texte = resources.files("lectura_nlp_fr.analyseur.data").joinpath("mots_composes_espace.txt").read_text(encoding="utf-8")
    return frozenset(l for l in texte.splitlines() if l and not l.startswith("#")) - _DEUX_MOTS


# Suites de la table LeXiK des composés à espace qui restent deux mots (décision de l'utilisateur, 11/10) : la
# préposition et l'article se phonémisent séparément (« de l'album » : /də l‿al.bɔm/, pas /də‿l‿al.bɔm/).
_DEUX_MOTS = frozenset({"de l'", "de la"})


# Recherche globale : une graphie concurrente ne peut être plus rare que la graphie reçue de plus de cet écart (zipf).
_ECART_FREQUENCE_COHERENCE = 2.5
# Avantage, en points de fréquence, d'une entrée dont la prononciation est exactement celle dite.
_PRIME_EXACTE = 1.0
# Confiance minimale de l'analyse pour qu'elle choisisse la graphie dans le sens phonétique → orthographe.
_CONFIANCE_GRAPHIE = 0.3
# Poids du modèle de langue face aux points d'accord avec l'analyse (réglé sur l'aller-retour du dev).
_POIDS_LANGUE = 1.0
# Points donnés à la graphie choisie par la tête de graphie (accord : 4 la catégorie, 2 le lemme, ±1 chaque trait).
_POIDS_GRAPHIE = 3.0
# Passes de réajustement des graphies par le modèle de langue (deux voisins ambigus se règlent en deux passes).
_PASSES_LANGUE = 2
_DEBUT, _FIN = "<s>", "</s>"
# Mots des formules qui n'ancrent pas une formule phonétique : liaisons de la lecture, hors vocabulaire.
_NON_ANCRES = frozenset({"et", "de", "pour", "moins", "le", "\u2205"})
_MULTIPLICATEURS = frozenset({"cent", "cents", "mille", "million", "millions", "milliard", "milliards"})
_AMALGAMES_ARTICLE = frozenset({"des", "aux", "du", "au"})
_UPOS_ANCRE = frozenset({"NOUN", "PROPN", "NUM", "SYM", "X"})
# Nombre dit sans ancre, en phonétique : au moins deux mots de nombre, dont un qui ne se confond guère avec un mot
# courant (« ɥi sɑ̃ mil » : huit cent mille, pas « huis sans mille » ; « si mil » : six mille) ; ou trois mots.
# « ɥi » seul reste un mot (« huis clos »).
# « si sɑ̃ », « di sɑ̃ » (si sans, dit sans) restent des mots.
# Nombres d'un mot homophones de mots courants (cette, sans, vin, si, dit, saint) : pas d'accord forcé après eux.
_NOMBRES_HOMOPHONES = frozenset("sept cent cents vingt six dix cinq".split())
# Écriture usuelle en chiffres romains (consigne de Maxime, 27/10/2026) : numéro d'un souverain ou d'un pape après son
# nom (« Louis XIV », « Jean-Paul II »), siècle et millénaire (« XIXe siècle », « Ier millénaire »), République
# (« Ve République »). Pendant de ``formules.detection._romain_en_contexte`` à la lecture.
_SOUVERAINS = frozenset(
    "Louis Henri Charles Philippe François Napoléon Jean Jean-Paul Benoît Pie Léon Grégoire Clément Innocent Boniface "
    "Urbain Sixte Paul Édouard Edouard Élisabeth Elisabeth Elizabeth Guillaume Frédéric Richard Jacques Ferdinand "
    "Alexandre Nicolas Pierre Ramsès Amenhotep Thoutmôsis George Georges Victor-Emmanuel Humbert Alphonse Juan Carlos "
    "Philippe-Auguste Childéric Clotaire Dagobert Pépin Lothaire Baudouin Albert Léopold Christian Gustave Olaf "
    "Haakon Constantin Justinien Théodose Mehmed Soliman Sélim Mohammed Hassan Abdallah Hussein Fayçal Rama".split())
_APRES_ORDINAL_ROMAIN = frozenset("siècle siècles millénaire millénaires république".split())
_ENTRE_ORDINAUX = frozenset(["au", "à", "et", "ou", "-", ",", "le", "la", "du"])
_CHIFFRES_ROMAINS = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
                     (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))


def _en_romain(n: int) -> str:
    texte = ""
    for valeur, chiffre in _CHIFFRES_ROMAINS:
        q, n = divmod(n, valeur)
        texte += chiffre * q
    return texte


def _ecrit(m: MotAligne) -> str:
    return "".join(c.graphe for c in m.couples if c != SYLLABE)


def _romains_usuels(alignes: list[MotAligne]) -> None:
    """« Louis 14 » → « Louis XIV », « 19e siècle » → « XIXe siècle », « 5e République » → « Ve République »."""
    for i, m in enumerate(alignes):
        if m.mot.type is not TypeMot.FORMULE or m.mot.valeur is None:
            continue
        sorte, valeur = getattr(m.mot, "type_formule", ""), m.mot.valeur
        if sorte == "nombre" and i > 0 and valeur.entier.isdigit() and not valeur.decimales and not valeur.negatif:
            avant = alignes[i - 1]
            apres = alignes[i + 1] if i + 1 < len(alignes) else None
            nom_apres = apres is not None and apres.analyse is not None and apres.analyse.upos == "NOUN"   # « Pierre 2 fois »
            if avant.mot.type is TypeMot.MOT and _ecrit(avant) in _SOUVERAINS and 1 <= int(valeur.entier) <= 40 and not nom_apres:
                alignes[i] = replace(m, mot=replace(m.mot, forme=_en_romain(int(valeur.entier))))
        elif sorte == "ordinal" and i + 1 < len(alignes) and not getattr(valeur, "second", False):
            apres = alignes[i + 1]
            if apres.mot.type is TypeMot.MOT and _ecrit(apres).lower() in _APRES_ORDINAL_ROMAIN and 1 <= valeur.rang <= 40:
                alignes[i] = _ordinal_romain(m)
                # Énumération : « du 11e au 13e siècle » → « du XIe au XIIIe siècle ».
                j = i - 1
                while True:
                    k = j
                    while k >= 0 and j - k < 3 and _ecrit(alignes[k]).lower() in _ENTRE_ORDINAUX:
                        k -= 1
                    if k == j or k < 0 or getattr(alignes[k].mot, "type_formule", "") != "ordinal" \
                            or alignes[k].mot.valeur is None or not 1 <= alignes[k].mot.valeur.rang <= 40:
                        break
                    alignes[k] = _ordinal_romain(alignes[k])
                    j = k - 1


def _ordinal_romain(m: MotAligne) -> MotAligne:
    valeur = m.mot.valeur
    suffixe = ("re" if valeur.feminin else "er") if valeur.rang == 1 else "e"
    return replace(m, mot=replace(m.mot, forme=_en_romain(valeur.rang) + suffixe))

# Sigle épelé inconnu du lexique (« ɛf ka pe » : « F cas P » → « FKP ») : les noms des lettres, en suite d'au moins deux.
_NOMS_LETTRES = {"a": "A", "be": "B", "se": "C", "de": "D", "ə": "E", "ø": "E", "ɛf": "F", "ʒe": "G", "aʃ": "H", "i": "I",
                 "ʒi": "J", "ka": "K", "ɛl": "L", "ɛm": "M", "ɛn": "N", "o": "O", "pe": "P", "ky": "Q", "ɛʁ": "R",
                 "ɛs": "S", "te": "T", "y": "U", "ve": "V", "dubləve": "W", "iks": "X", "iɡʁɛk": "Y", "zɛd": "Z"}
# Mots-outils homophones d'un nom de lettre : ils ne prolongent pas un sigle (« la vitamine C et », « au B »).
_PAS_LETTRE = frozenset("à a au aux eau eaux haut eu eus eut des dès de ces ses c'est s'est sait sais et est y il "
                        "elle elles j'ai t'ai".split())


_LETTRES_DITES = {lettre: phone for phone, lettre in _NOMS_LETTRES.items() if phone != "ø"}
_VOYELLES_CAPITALES = frozenset("AEIOUY")
_ROMAIN = re.compile(r"M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})")
# Groupes de consonnes qui ouvrent une syllabe, et qui finissent un mot, dans un mot en capitales lu comme un mot.
_ATTAQUES = frozenset("BL BR CL CR DR FL FR GL GR PL PR TR VR CH PH TH SC SP ST SK SL SM SN SW KR KL".split())
_FINALES = frozenset("NS NT ND RS RT RD LT LS ST SK CK CT PS PT RN RM RK LF RG NG NK".split())


def _imprononcable(forme: str) -> bool:
    """Mot en capitales qu'on épelle plutôt qu'on ne le lit (« FIH », « PSA », « USGS ») : sans voyelle, deux lettres,
    trois lettres hors consonne-voyelle-consonne, ou un groupe de consonnes qui n'est ni une attaque ni une finale du
    français ; jamais un nombre romain. Sur les sigles et acronymes de
    la table des abrègements, cette règle retrouve la bonne lecture dans 83 % des cas (92 % des sigles épelés)."""
    if not _VOYELLES_CAPITALES.intersection(forme):
        return True
    if _ROMAIN.fullmatch(forme):
        return False                     # « LXXXIV » hors contexte : lu comme en 1.0.2, pas lettre à lettre
    if len(forme) == 3:
        # Consonne, voyelle, consonne (sans h muet) : lu comme un mot (« KIN », « NAB », « SAM » des livres) ; la table des
        # abrègements est partagée sur ce motif (206 sigles épelés, 156 acronymes lus).
        return not (forme[0] not in _VOYELLES_CAPITALES and forme[1] in _VOYELLES_CAPITALES
                    and forme[2] not in _VOYELLES_CAPITALES and "H" not in (forme[0], forme[2]))
    if len(forme) < 3:
        return True
    for groupe in re.finditer(r"[^AEIOUY]+", forme):
        s, debut, fin = groupe.group(), groupe.start() == 0, groupe.end() == len(forme)
        if len(s) >= 3 and not (len(s) == 3 and s[1:] in _ATTAQUES):
            return True
        if len(s) == 2 and ((debut and s not in _ATTAQUES) or (fin and s not in _FINALES)):
            return True
    return False


def _epele(forme: str) -> tuple[Couple, ...]:
    """Sigle épelé d'un seul tenant, une lettre par syllabe (« FIH » → ɛf.i.aʃ), comme les sigles du lexique."""
    couples: list[Couple] = []
    for lettre in forme:
        couples += ([SYLLABE] if couples else []) + [Couple(_LETTRES_DITES[lettre], lettre)]
    return tuple(couples)


def _lettres(phone: str) -> list[tuple[str, str]] | None:
    """Découpage d'une prononciation (sans séparateurs) en noms de lettres ; None s'il n'y en a pas."""
    if not phone:
        return []
    for n in (7, 5, 3, 2, 1):
        tete = _NOMS_LETTRES.get(phone[:n])
        if tete is not None and (suite := _lettres(phone[n:])) is not None:
            return [(phone[:n], tete)] + suite
    return None


@cache
def _sigles_connus() -> dict[str, str]:
    """Prononciation épelée (sans séparateurs) → sigle, pour les sigles de la table des abrègements qui ne sont pas
    aussi un mot courant (« DVD » de.ve.de, « LCD » ɛl.se.de ; pas « CEP »)."""
    from .abregements import SIGLE, table

    connus = {}
    for a in table().values():
        if a.nature == SIGLE and a.ambigu != "mot" and a.forme.isalpha() and a.forme.isupper() and len(a.forme) >= 2:
            cle = re.sub(r"[ .‿]", "", a.phone)
            if _lettres(cle) is not None and len(_lettres(cle)) == len(a.forme):
                connus.setdefault(cle, a.forme)
    return connus


# Zipf sous lequel un mot écrit est assez rare pour être un nom de lettre mal écrit (« Hess » S, « pé » P, « haches » H).
_RARE = 3.0
# Essais (30/10) : sigles hors de la table faits de plusieurs mots, et mot rare du lexique seul fait de noms de lettres.
_LIBRES = True
_SEUL_RARE = True
_ANNONCES = True
# Mots-outils sautés dans les initiales d'une forme longue (« Institut fédéral pour le développement durable » → IFDD).
_HORS_INITIALES = frozenset("de du des d la le les l pour et en à au aux sur par un une dans of the and for".split())


def _sigle_connu(alignes: list[MotAligne], i: int, frequence=None) -> tuple[int, str] | None:
    """Plus longue suite d'au moins deux mots à partir de ``i`` qui se prononce comme un sigle connu, mots-outils
    compris (« des V dès » → « DVD ») : (fin, sigle) ou None. La suite doit déjà contenir une lettre isolée, un mot
    inconnu du lexique ou un mot rare (zipf sous ``_RARE`` selon ``frequence(forme)``) : des mots courants seuls restent
    écrits (« des pays » n'est pas « DPI », « à ses » pas « AC »)."""
    connus, cle, trouve, indice = _sigles_connus(), "", None, False
    indices = courants = 0
    libre = _LIBRES
    lettres: list[str] = []
    for j in range(i, min(i + 6, len(alignes))):
        m = alignes[j]
        if m.mot.type is not TypeMot.MOT or m.lecture or (j > i and not m.espace_avant):
            break
        phone = re.sub(r"[ .‿]", "", m.phone)
        cle += phone
        signe = (len(_ecrit(m)) == 1 and _ecrit(m).lower() not in _PAS_LETTRE) or m.origine != "lexique" \
            or (frequence is not None and frequence(_ecrit(m)) < _RARE)
        indice = indice or signe
        if j > i and indice and cle in connus:
            trouve = (j + 1, connus[cle])
        outil = _ecrit(m).lower() in _PAS_LETTRE
        libre = libre and (decoupe := _lettres(phone)) is not None and not (outil and (j == i or decoupe[0][1] != "C"))
        if not libre:
            continue
        lettres += [l for _, l in decoupe]
        # Sigle hors de la table : chaque mot est fait de noms de lettres, et les indices au moins aussi nombreux que
        # les mots courants (« hesse el hesse » → SLS, « ji air » → JR, « NG ses » → NGC ; pas « des pays » → DPI).
        # Un mot-outil n'ouvre jamais la suite, et seuls ceux qui disent C la prolongent (« le CIO a » n'est pas CIOA).
        indices, courants = indices + signe, courants + (not signe)
        if j > i and indices >= max(1, courants) and (trouve is None or trouve[0] < j + 1):
            trouve = (j + 1, "".join(lettres))
    return trouve


def _sigles_epeles(alignes: list[MotAligne], frequence=None, rare=None) -> list[MotAligne]:
    """Suites de noms de lettres → sigle en capitales : plusieurs mots dont l'un déjà écrit comme une lettre seule
    (« F cas P », « Z Hicks »), ou un mot que le lexique ne connaît pas (« be.ka » : « Becca » → « BK ») ; ou plusieurs
    mots qui se prononcent comme un sigle connu de la table des abrègements (``_sigle_connu``)."""
    def lettres(m: MotAligne) -> list[tuple[str, str]] | None:
        if m.mot.type is not TypeMot.MOT or m.lecture or m.origine not in ("lexique", "modele", "inconnu"):
            return None
        if _ecrit(m).lower() in _PAS_LETTRE:
            return None
        decoupe = _lettres(re.sub(r"[ .‿]", "", m.phone))
        if not decoupe or (len(decoupe) > 1 and m.origine == "lexique"
                           and not (_SEUL_RARE and rare is not None and rare(_ecrit(m)))):
            return None
        return decoupe

    resultat, i = [], 0
    while i < len(alignes):
        j, suite = i, []
        while j < len(alignes) and (j == i or alignes[j].espace_avant) and (d := lettres(alignes[j])) is not None:
            suite.append(d)
            j += 1
        isolee, connu = any(len(_ecrit(alignes[k])) == 1 for k in range(i, j)), None
        if not (sum(map(len, suite)) >= 2 and (isolee or (j - i == 1 and alignes[i].origine != "lexique"))) \
                and (connu := _sigle_connu(alignes, i, frequence)) is not None:
            j = connu[0]
            suite = [_lettres(re.sub(r"[ .‿]", "", "".join(m.phone for m in alignes[i:j])))]
        seul_rare = j - i == 1 and _SEUL_RARE and rare is not None and rare(_ecrit(alignes[i]))
        if sum(map(len, suite)) >= 2 and (isolee or (j - i == 1 and alignes[i].origine != "lexique") or connu
                                          or seul_rare):
            premier, dernier = alignes[i], alignes[j - 1]
            couples: list[Couple] = []
            for d in suite:
                for phone, lettre in d:
                    couples += ([SYLLABE] if couples else []) + [Couple(phone, lettre)]
            forme = "".join(c.graphe for c in couples if c != SYLLABE)
            mot = replace(premier.mot, forme=forme, fin=dernier.mot.fin)
            resultat.append(MotAligne(mot, tuple(couples), "".join(c.phone for c in couples if c != SYLLABE),
                                      premier.analyse, "sigle", dernier.jonction,
                                      phone="".join(m.phone for m in alignes[i:j]), espace=premier.espace))
            i = j
        else:
            resultat.append(alignes[i])
            i += 1
    return resultat

# Pronoms sujets de la 3e personne dont le nombre ne s'entend pas (« il » / « ils », « elle » / « elles »).
_SUJETS_3_PAIRES = {"il": "il", "ils": "il", "elle": "elle", "elles": "elle"}
_SUJETS_3 = frozenset(_SUJETS_3_PAIRES)
_CLITIQUES_PREVERBAUX = frozenset("ne n' se s' le la l' les lui leur y en me m' te t' nous vous".split())
_NOMBRE_SUR = frozenset({"mille", "mil", "million", "millions", "milliard", "milliards", "huit"})
# Clitiques sujets qui prennent un trait d'union après leur verbe (« est-il », « dit-on »).
_SUJETS_INVERSES = TABLES_PHONE.sujets | frozenset({"ʒə", "ty", "nu", "vu", "sə"})



def _enveloppe(nom: str):
    """L'enveloppe (correction des entrées fautives : nettoyage, tolérance phonétique, cohérence) relève du Correcteur
    (``lectura_nlp_fr.correcteur.nettoyage``), pas de l'Analyseur : elle n'est chargée que sur demande."""
    import importlib

    try:
        return importlib.import_module(f"lectura_nlp_fr.correcteur.nettoyage.{nom}")
    except ModuleNotFoundError as e:
        raise ImportError("La correction des entrées relève du Correcteur : pip install \"lectura-nlp-fr[correcteur]\".") from e

class Chaine:
    def __init__(
        self,
        analyseur: Analyseur,
        lexique: Lexique,
        modele: ModeleDeMot | None = None,
        politique: Politique = LECTURE,
        index: IndexPhone | None = None,
        langue=None,
        poids_langue: float = _POIDS_LANGUE,
        poids_graphie: float | None = None,
        e_caduc: bool = False,
        schwas_finaux: bool = False,
        liaisons: bool = True,
        enchainements: bool = True,
        elisions: bool = True,
    ):
        self.analyseur = analyseur
        self.lexique = lexique
        self.modele = modele
        self.politique = politique
        self.index = index          # nécessaire au sens phonétique → orthographe
        # Modèle de langue des homophones (optionnel) : ``score(gauche, candidat, droite)``, log-probabilité ;
        # il départage les graphies homophones selon les mots voisins, avec le poids ``poids_langue``.
        self.langue = langue
        self.poids_langue = poids_langue
        # Points de la graphie choisie par la tête de graphie de l'analyseur (sens phonétique → orthographe).
        self.poids_graphie = _POIDS_GRAPHIE if poids_graphie is None else poids_graphie
        # Couche de correction (``enveloppe``) : objet qui a ``ajuster_phone(mots, analyses)`` ; aucune par défaut.
        self.correcteur = None
        # Recherche globale (``enveloppe``) : objet qui a ``choisir(chaine, mots, analyses, inverses, entrees)`` et rend
        # les graphies choisies ensemble sur la phrase ; aucune par défaut (chaque mot choisi seul).
        self.recherche = None
        # Phonétique → orthographe : suites de mots de nombre sûres converties sans mot d'ancrage (``_NOMBRE_SUR``).
        self.nombres_sans_ancre = True
        # Index de la tolérance phonétique (``enveloppe``) : l'index complet, quand l'index de la chaîne est celui, réduit,
        # du lexique embarqué (un mot rare absent de l'index réduit n'est pas une faute du décodeur) ; None : ``index``.
        self.index_tolerance = None
        # Tête de graphie entre flexions d'un même lemme (besoin / besoins) ; False : les traits prédits décident.
        self.tete_meme_lemme = True
        self.tete_exactes = False
        # Seuil de confiance de l'UPOS au-delà duquel la catégorie prédite l'emporte sur la tête de graphie (None : jamais).
        self.tete_upos = None
        # Lecture courante : l'e caduc tombe selon la loi des trois consonnes (« sam.di », « lə pti ») ;
        # sans l'option, lecture soignée, le schwa est toujours dit.
        self.e_caduc = e_caduc
        # Diction soignée (lecture syllabée) : l'e muet final après consonne est dit /ə/ devant consonne ou pause
        # (« ta.blə », « pɔʁ.tə ») ; devant voyelle aussi quand l'enchaînement est désactivé.
        self.schwas_finaux = schwas_finaux
        # Jonctions entre mots (toutes actives par défaut, comme dans l'ancien Aligneur) : sans liaisons, aucune
        # consonne latente n'est dite ; sans enchaînements, chaque mot garde ses syllabes (« il a » et non « i.l‿a ») ;
        # sans élisions, le mot élidé reste une syllabe à part (« l.e.kɔl » et non « l‿e.kɔl »).
        self.liaisons = liaisons
        self.enchainements = enchainements
        self.elisions = elisions
        self._lectures_sigles: dict[str, MotAligne | None] = {}

    def lire(self, texte: str, corriger: bool = False) -> list[PhraseAlignee]:
        """Texte → alignement. ``corriger`` : les fautes qui changent la prononciation sont d'abord
        nettoyées (enveloppe) ; les corrections faites sont jointes à chaque phrase."""
        document = tokeniser(texte)
        corrections = []
        if corriger:
            document, corrections = _enveloppe("nettoyage").Nettoyeur(self.lexique, self.modele).nettoyer(document)
        document = detecter_formules(document)
        # Mot seul : seulement quand toute l'entrée est un mot (liste de mots), pas une phrase d'un mot dans un récit
        # (« Chut ! Ils se moqueraient… » garde ʃyt ; « X. L'homme… » garde dis).
        seul = sum(lu.type is not TypeMot.PONCTUATION for p in document.phrases for m in p.mots
                   for lu in (m.lecture or [m])) == 1
        phrases = [self._phrase(p.mots, seul) for p in document.phrases]
        for phrase in phrases:
            phrase.corrections = [c for c in corrections if phrase.mots and phrase.mots[0].mot.debut <= c.debut < phrase.mots[-1].mot.fin + 1]
        return phrases

    def _phrase(self, mots: list[Mot], seul: bool = False) -> PhraseAlignee:
        # La phrase analysée est celle qui se dit : les formules y sont remplacées par leur lecture.
        lus = [lu for m in mots for lu in (m.lecture or [m])]
        analyses = self._analyser_ecrit(mots, lus)
        if seul and sum(m.type is not TypeMot.PONCTUATION for m in lus) == 1:
            analyses = [a if m.type is TypeMot.PONCTUATION else self._analyse_isolee(m, a) for m, a in zip(lus, analyses)]
        capitales = [m.type is TypeMot.MOT and len(m.forme) > 1 and m.forme.isupper() for m in lus]
        mots_seuls = [k for k, m in enumerate(lus) if m.type is TypeMot.MOT]
        passage = set()                  # mots en capitales voisins d'un autre (titre : « CRAIG ET FRY ») : pas épelés
        for a, b in zip(mots_seuls, mots_seuls[1:]):
            if capitales[a] and capitales[b]:
                passage |= {a, b}
        alignes = [self._mot(m, a, epeler=k not in passage) for k, (m, a) in enumerate(zip(lus, analyses))]
        mots, alignes = self._composes_a_espace(mots, alignes)
        # D'abord la forme de chaque mot (schwas ajoutés ou retirés), puis les jonctions sur ces formes.
        if self.schwas_finaux:
            _schwas_finaux(alignes)
        if self.e_caduc:
            _e_caducs(alignes)
        self._jonctions(alignes)
        resultat, k = [], 0
        for m in mots:
            n = len(m.lecture) or 1
            if m.lecture:
                resultat.append(MotAligne(m, origine="formule", analyse=alignes[k].analyse, lecture=alignes[k : k + n]))
            else:
                resultat.append(alignes[k])
            k += n
        return PhraseAlignee(resultat)

    def _analyser_ecrit(self, mots: list[Mot], lus: list[Mot]) -> list[Analyse]:
        """Analyse de la phrase dite. Un analyseur qui reçoit le type des mots (``types_de_mots``, modèle 2 v3) voit
        chaque mot lu d'une formule typé ``f:<type>``, un abrègement comme un seul jeton typé ``a:<nature>`` (son
        analyse vaut pour chaque mot de sa lecture), une formule sans lecture ``s``, la ponctuation ``p``."""
        if not getattr(self.analyseur, "types_de_mots", False):
            return self.analyseur.analyser([m.forme for m in lus])
        formes, types, rangs = [], [], []
        for m in mots:
            n = len(m.lecture) or 1
            if m.abregement:
                formes.append(m.forme)
                types.append(f"a:{m.abregement}")
                rangs += [len(formes) - 1] * n
                continue
            for lu in m.lecture or [m]:
                formes.append(lu.forme)
                if m.lecture:
                    types.append(f"f:{m.type_formule}")
                elif m.type is TypeMot.FORMULE:
                    types.append("s")
                elif m.type is TypeMot.PONCTUATION:
                    types.append("p")
                else:
                    types.append("m")
                rangs.append(len(formes) - 1)
        analyses = self.analyseur.analyser(formes, types=types)
        return [analyses[k] for k in rangs]

    def _composes_a_espace(self, mots: list[Mot], alignes: list[MotAligne]) -> tuple[list[Mot], list[MotAligne]]:
        """Regroupe en un mot une suite de la liste fermée (« parce que », « tout à fait »).

        Le tokeniseur a livré les mots séparés ; la suite devient un mot si l'analyse la donne pour
        figée (relation ``fixed``), ou si sa prononciation porte une jonction propre au mot composé
        (« tu.t‿a.fɛ », « də.tɑ̃.z‿ɑ̃.tɑ̃ »), que les mots séparés ne feraient pas.
        """
        if len(mots) != len(alignes):       # phrase à formule : les deux listes ne se correspondent plus
            return mots, alignes
        liste = _mots_composes_a_espace()
        nouveaux_mots, nouveaux = [], []
        i = 0
        while i < len(mots):
            for j in range(min(len(mots), i + _MAX_MOTS_COMPOSE), i + 1, -1):
                groupe = mots[i:j]
                if not all(m.type is TypeMot.MOT for m in groupe) or not all(m.espace_avant for m in groupe[1:]):
                    continue
                graphie = " ".join(m.forme for m in groupe)
                if graphie.lower() not in liste:
                    continue
                entree = choisir(self.lexique.lectures(graphie), alignes[i].analyse)
                fige = all(a.analyse and a.analyse.relation == "fixed" for a in alignes[i + 1 : j])
                if entree is None or not (fige or "‿" in entree.phone_enrichi):
                    continue
                mot = Mot(TypeMot.MOT, graphie, groupe[0].debut, groupe[-1].fin, [s for m in groupe for s in m.segments], groupe[0].espace_avant)
                couples = tuple(replace(c, graphe=" ") if c.graphe == "\u2423" else c for c in entree.couples)
                couples = _a_la_casse(couples, graphie) or (Couple(entree.phone_enrichi, graphie),)
                analyse = Analyse(entree.upos, entree.feats, entree.lemme, alignes[i].analyse.tete, alignes[i].analyse.relation)
                nouveaux_mots.append(mot)
                nouveaux.append(MotAligne(mot, couples, entree.phone_enrichi, analyse, "lexique", source=entree.origine))
                i = j
                break
            else:
                nouveaux_mots.append(mots[i])
                nouveaux.append(alignes[i])
                i += 1
        return nouveaux_mots, nouveaux

    def _analyse_isolee(self, mot: Mot, analyse: Analyse) -> Analyse:
        """Mot seul, sans phrase autour : l'analyseur n'a rien pour décider, la lecture la plus fréquente du lexique
        l'emporte (« mon » déterminant, et non le nom de la langue môn ; « fit » /fi/, « vis » /vis/ du verbe…)."""
        entrees = [e for e in self._lectures(mot.forme) if not mot.nature or e.type == mot.nature]
        if not entrees or analyse is None:
            return analyse
        # Une capitale initiale n'en fait pas un nom propre : « Chut ! » ʃyt (interjection), pas « Chu » ʃy.
        entrees = [e for e in entrees if e.upos != "PROPN"] or entrees
        e = max(entrees, key=lambda e: e.frequence)
        # Un déterminant ne se dit pas seul : un pronom presque aussi fréquent l'emporte (« Tous. » tus, pas tu).
        pronoms = [p for p in entrees if p.upos == "PRON" and p.frequence >= e.frequence - 1]
        if e.upos in ("DET", "ADJ") and pronoms:
            e = max(pronoms, key=lambda p: p.frequence)
        return replace(analyse, upos=e.upos, feats=e.feats, lemme=e.lemme)

    def _mot(self, mot: Mot, analyse: Analyse, epeler: bool = True) -> MotAligne:
        if mot.type is TypeMot.PONCTUATION:
            return MotAligne(mot, (Couple("", mot.forme),), analyse=analyse, origine="ponctuation")
        lectures = self._lectures(mot.forme)
        entree = choisir(lectures, analyse, mot.nature)
        if entree is not None and analyse is not None and analyse.lemme.lower() not in {e.lemme.lower() for e in lectures}:
            # Lemme de l'analyseur inconnu pour cette forme (« mûres » → « sûr », « admiration » → « administration ») :
            # celui de la lecture la plus fréquente de même catégorie, s'il y en a une.
            memes = [e for e in lectures if e.upos == analyse.upos]
            if memes:
                analyse = replace(analyse, lemme=max(memes, key=lambda e: e.frequence).lemme)
        if entree is not None:
            couples = _a_la_casse(entree.couples, mot.forme) or (Couple(entree.phone_enrichi, mot.forme),)
            return MotAligne(mot, couples, entree.phone_enrichi, analyse, "lexique", source=entree.origine)
        if epeler and 2 <= len(mot.forme) <= 6 and mot.forme.isascii() and mot.forme.isalpha() and mot.forme.isupper() \
                and _imprononcable(mot.forme):
            # Mot en capitales inconnu du lexique, imprononçable : épelé, d'un seul tenant (« FIH » ɛf.i.aʃ).
            couples = _epele(mot.forme)
            return MotAligne(mot, couples, "".join(c.phone for c in couples), analyse, "modele")
        couples = self.modele.aligner(mot.forme, analyse) if self.modele else None
        if couples:
            couples = _a_la_casse(couples, mot.forme) or couples
            return MotAligne(mot, couples, "".join(c.phone for c in couples), analyse, "modele")
        return MotAligne(mot, (Couple("", mot.forme),), analyse=analyse, origine="inconnu")

    def _lectures(self, forme: str) -> list[Entree]:
        """Lectures du lexique ; une majuscule initiale sans accent (« Eglise », « Etat ») est aussi cherchée
        accentuée, l'usage omettant souvent les accents sur les capitales."""
        entrees = self.lexique.lectures(forme)
        if not entrees and len(forme) > 1 and forme.isupper():
            entrees = self.lexique.lectures(forme.capitalize())     # « JUDITH » : Judith
        if entrees or forme[:1] not in _CAPITALES_ACCENTUABLES:
            return entrees
        for initiale in _CAPITALES_ACCENTUABLES[forme[0]]:
            entrees = self.lexique.lectures(initiale + forme[1:])
            if entrees:
                return entrees
        return []

    # ── Sens phonétique → orthographe ──────────────────────────────────────────

    def ecrire(
        self, chaine: str, formules: bool = True, passes: int = 1, tolerance: bool = False, e_caduc: bool | None = None
    ) -> list[PhraseAlignee]:
        """Phrase phonétique (mots séparés par des espaces, « . » et « ‿ » facultatifs) → alignement.

        ``passes`` = 2 : une fois les graphies choisies, la phrase est réanalysée avec les deux canaux
        (graphie et prononciation), et les graphies sont choisies à nouveau.
        ``e_caduc`` (défaut : celui de la chaîne) : l'entrée peut avoir perdu des schwas (« pti », « sam.di »,
        « ʒ sɥi ») ; ils sont remis avant la lecture quand ils rendent le mot nettement plus fréquent.
        ``tolerance`` (enveloppe, optionnelle) : les mots inconnus du lexique sont d'abord rapprochés
        d'un mot connu (erreurs typiques du décodeur CTC) ; corrections dans ``PhraseAlignee.corrections``.
        """
        if self.index is None:
            raise ValueError("Le sens phonétique → orthographe demande un index phonétique.")
        with supplement.ecriture():         # supplément d'écriture (``supplement.py``) actif dans ce sens seulement
            return self._ecrire(chaine, formules, passes, tolerance, e_caduc)

    def _ecrire(self, chaine: str, formules: bool, passes: int, tolerance: bool, e_caduc: bool | None) -> list[PhraseAlignee]:
        corrections: list = []
        if self.e_caduc if e_caduc is None else e_caduc:
            chaine = restaurer(chaine, self.index)      # parole courante : schwas tombés remis
        if tolerance:
            chaine, corrections = _enveloppe("phonetique").Tolerant(self.index_tolerance or self.index).nettoyer(chaine)
        document = recomposer(tokeniser_phone(chaine), self.index)
        contexte: dict = {}         # nombre du dernier sujet entendu, d'une phrase à la suivante
        phrases = [self._phrase_phone(chaine, p.mots, formules, passes, contexte) for p in document.phrases]
        if phrases and corrections:
            phrases[0].corrections = corrections
        return phrases

    def _phrase_phone(self, chaine: str, mots: list[Mot], formules: bool, passes: int = 1,
                      contexte: dict | None = None) -> PhraseAlignee:
        cles = [self._cles(m) for m in mots]
        phones = [c[0] if c else "" for c in cles]
        options = {}
        if getattr(self.analyseur, "types_de_mots", False):
            # Modèle 2 v3 : la consonne d'une liaison réalisée reste au mot de gauche, la ponctuation a son symbole.
            phones = ["".join(s.forme for s in m.segments) if m.type is TypeMot.MOT else "" for m in mots]
            options = {"types": ["m" if m.type is TypeMot.MOT else "p" for m in mots],
                       "formes": [m.forme if m.type is not TypeMot.MOT else "" for m in mots]}
            if getattr(self.analyseur, "tete_graphie", False):
                # Tête de graphie : homophones cherchés sous la prononciation sans consonne de liaison.
                options["cles"] = [c[0] if c else "" for c in cles]
        analyses = self.analyseur.analyser_phone(phones, **options)
        if self.correcteur is not None:
            # Couche de correction optionnelle (enveloppe, hors du paquet) : règles d'accord sur l'analyse.
            analyses = self.correcteur.ajuster_phone(mots, analyses)
        for _ in range(passes - 1):
            if not hasattr(self.analyseur, "analyser_dual"):
                break
            graphies = [self._graphie(m, False, a) if m.type is TypeMot.MOT else None for m, a in zip(mots, analyses)]
            formes = [e.ortho if e else m.forme for m, e in zip(mots, graphies)]
            analyses = self.analyseur.analyser_dual(formes, phones, **({"types": options["types"]} if options else {}))
        categories: list[str] = []      # catégorie retenue pour chaque mot : celle du lexique quand il tranche
        inverses: list[bool] = []
        entrees: list[Entree | None] = []
        for i, (mot, analyse) in enumerate(zip(mots, analyses)):
            if mot.type is not TypeMot.MOT:
                categories.append("PUNCT")
                inverses.append(False)
                entrees.append(None)
                continue
            inverses.append(self._sujet_inverse(i, mots, cles, analyses, categories))
            entrees.append(self._graphie(mot, inverses[-1], analyse))
            categories.append(entrees[-1].upos if entrees[-1] else analyse.upos)
        self._numeral_lie(mots, analyses, entrees)
        if self.recherche is not None:
            entrees = self.recherche.choisir(self, mots, analyses, inverses, entrees)
        if self.langue is not None:
            self._selon_les_voisins(mots, analyses, inverses, entrees)
        self._accord_des_sujets(mots, analyses, inverses, entrees, {} if contexte is None else contexte)
        self._accord_des_groupes(mots, analyses, inverses, entrees, phones, options.get("types"))
        alignes: list[MotAligne] = []
        for i, (mot, analyse) in enumerate(zip(mots, analyses)):
            # Prononciation telle que donnée en entrée, avec l'espace qui précède et le « ‿ » qui suit.
            avant = " " if mot.debut > 0 and chaine[mot.debut - 1].isspace() else ""
            source = avant + chaine[mot.debut : mot.fin] + ("‿" if chaine[mot.fin : mot.fin + 1] == "‿" else "")
            if mot.type is not TypeMot.MOT:
                alignes.append(MotAligne(mot, (Couple("", mot.forme),), analyse=analyse, origine="ponctuation", phone=source))
                continue
            entree = entrees[i]
            numeral = mot_de(mot) if entree is None else ""
            couples = None
            if entree is None and "\u2205" in numeral and self.modele:
                couples = self.modele.graphier(self._prononciation(chaine, mot), analyse)
            if entree is None and "\u2205" not in numeral:
                # Numéral absent du lexique sous cette forme (« vɛ̃t.si.z » : vingt-six en liaison).
                aligne = MotAligne(mot, (Couple(chaine[mot.debut : mot.fin], numeral),), analyse=analyse, origine="lexique")
            elif couples:
                aligne = MotAligne(mot, couples, "".join(c.phone for c in couples), analyse, "modele")
            elif entree is None:
                aligne = MotAligne(mot, (Couple(chaine[mot.debut : mot.fin], ""),), analyse=analyse, origine="inconnu")
            else:
                couples = entree.couples or (Couple(entree.phone_enrichi, entree.ortho),)
                aligne = MotAligne(mot, couples, entree.phone_enrichi, analyse, "lexique", source=entree.origine)
            precedent = alignes[-1] if alignes else None
            ecrit = "".join(c.graphe for c in aligne.couples if c != SYLLABE)
            aligne.espace = bool(precedent) and not (
                ecrit.startswith("-") or "".join(c.graphe for c in precedent.couples).endswith(("'", "(", "«"))
            )
            aligne.phone = source
            aligne.jonction = mot.jonction or ESPACE
            alignes.append(aligne)
        if formules:
            alignes = self._formules_phone(mots, analyses, alignes)
            alignes = self._formules_dites(alignes)
            self._pluriel_apres_nombre(alignes)
            _romains_usuels(alignes)
        alignes = _sigles_epeles(alignes, self._frequence_forme, self._rare_pour_sigle)
        if _ANNONCES:
            alignes = self._sigles_annonces(alignes)
        _majuscule_initiale(alignes)
        return PhraseAlignee(alignes)

    @staticmethod
    def _prononciation(chaine: str, mot: Mot) -> str:
        """Prononciation donnée au modèle de mot : telle qu'écrite, sans la consonne de liaison éventuelle."""
        dite = chaine[mot.debut : mot.fin]
        if mot.jonction == LIAISON and mot.forme_isolee:
            return mot.forme_isolee
        return dite

    def _cles(self, mot: Mot) -> list[str]:
        """Suites de phonèmes sous lesquelles chercher le mot. Quand la consonne finale peut être une
        liaison ou appartenir au mot, les deux lectures sont gardées, la plus fréquente en tête."""
        if mot.type is not TypeMot.MOT:
            return []
        cle = "".join(s.forme for s in mot.segments)
        if mot.jonction == LIAISON:
            return [mot.forme_isolee]
        if mot.jonction == AMBIGU:
            lectures = self.index.lectures(cle)
            liee, finale = lectures.get(LIEE_), lectures.get(MOT_)
            if liee and finale and finale.zipf > liee.zipf:
                return [cle, mot.forme_isolee]
            return [mot.forme_isolee, cle]
        return [cle]

    @staticmethod
    def _sujet_inverse(i: int, mots: list[Mot], cles: list[list[str]], analyses: list[Analyse], categories: list[str]) -> bool:
        """« ɛ.t‿il » : pronom sujet juste après un verbe conjugué, et qui n'est pas le sujet du verbe suivant."""
        if i == 0 or not cles[i] or cles[i][0] not in _SUJETS_INVERSES or analyses[i].upos != "PRON":
            return False
        if mots[i - 1].type is not TypeMot.MOT or categories[i - 1] not in ("VERB", "AUX"):
            return False
        if mots[i - 1].lie_au_suivant and mots[i - 1].jonction in (LIAISON, AMBIGU):
            return True      # liaison du verbe sur le pronom : il ne peut être que postposé
        suivant = analyses[i + 1] if i + 1 < len(mots) and mots[i + 1].type is TypeMot.MOT else None
        return not (suivant and suivant.upos in ("VERB", "AUX") and suivant.feats.get("VerbForm") == "Fin")

    def _selon_les_voisins(self, mots: list[Mot], analyses: list[Analyse], inverses: list[bool], entrees: list[Entree | None]) -> None:
        """Réajuste les graphies choisies avec le modèle de langue, chaque mot entre ses voisins déjà écrits."""

        def ecrit(j: int) -> str:
            if j < 0:
                return _DEBUT
            if j >= len(mots):
                return _FIN
            return (entrees[j].ortho if entrees[j] else mots[j].forme).lower()

        for _ in range(_PASSES_LANGUE):
            change = False
            for i, mot in enumerate(mots):
                if entrees[i] is None or mot.type is not TypeMot.MOT:
                    continue
                autre = self._graphie(mot, inverses[i], analyses[i], (ecrit(i - 1), ecrit(i + 1)))
                if autre is not None and autre.ortho != entrees[i].ortho:
                    entrees[i], change = autre, True
            if not change:
                break

    def _graphie(self, mot: Mot, inverse: bool, analyse: Analyse, voisins: tuple[str, str] | None = None) -> Entree | None:
        """Entrée du lexique qui se prononce ainsi, s'écrit avec les mêmes séparateurs et s'accorde le
        mieux avec l'analyse. Une prononciation qui ne diffère que par le timbre d'une voyelle moyenne
        est admise, avec un handicap ; à accord égal, la plus fréquente l'emporte."""
        notes = self._notes_graphie(mot, inverse, analyse, voisins)
        if not notes:
            return None
        meilleure, _note = max(notes, key=lambda c: c[1])
        return self.lexique.aligner(meilleure)

    def _notes_graphie(
        self, mot: Mot, inverse: bool, analyse: Analyse, voisins: tuple[str, str] | None = None
    ) -> list[tuple[Entree, tuple[float, float]]]:
        """Graphies candidates du mot et leur note (points d'accord, de langue et de tête ; puis fréquence) : la
        meilleure note est la graphie choisie seule (``_graphie``) ; la recherche globale de l'enveloppe les reprend."""
        dite = "".join(s.forme for s in mot.segments)
        tiret = inverse or mot.segments[0].sep_avant == "-"
        elide = mot.segments[-1].sep_apres == "'"
        internes = [s.sep_avant for s in mot.segments[1:]]
        candidates = self._candidates(self._cles(mot), dite, tiret, elide, internes, voisines=True)
        if not candidates:
            return []
        # Analyse peu sûre (confiance de l'UPOS sous le seuil) : la catégorie ne départage plus, la fréquence décide.
        sure = analyse.confiance >= _CONFIANCE_GRAPHIE

        def langue(e: Entree) -> float:
            if voisins is None or self.langue is None:
                return 0.0
            return self.poids_langue * self.langue.score(voisins[0], e.ortho.lower(), voisins[1])

        if voisins is not None and len({e.ortho.lower() for e, _ in candidates}) < 2:
            return []                # une seule graphie possible : rien à départager
        # Tête de graphie : des points pour la graphie qu'elle choisit, quand elle a vu toutes les concurrentes (sa table
        # ignore les élisions, « c'est », et les timbres voisins, « ses » pour sɛ). Des points et non une décision : elle
        # se trompe surtout sur le nombre des noms (« besoins »), où l'analyse voit mieux.
        vues = {g.lower() for g in analyse.graphies}
        # Concurrentes que la tête doit avoir vues : toutes, ou (``tete_exactes``) celles de prononciation exacte, les
        # timbres voisins (« travaillé » pour tʁavajɛ) se départageant ensuite par l'accord. Les entrées d'un lexique
        # branché (``origine``) n'en sont pas : un homophone rare (« publis ») ne doit pas faire taire la tête
        # (2026-10-14, mesure de Lexicon : publient → publie, griffes → griffe).
        a_voir = [e for e, sc in candidates
                  if not e.origine and (not self.tete_exactes or sc - e.frequence >= _PRIME_EXACTE / 2)]
        tete = analyse.graphie.lower() if analyse.graphie and all(e.ortho.lower() in vues for e in a_voir) else ""
        if tete and not self.tete_meme_lemme and len({e.lemme.lower() for e, _ in candidates}) == 1:
            tete = ""
        if tete and self.tete_upos is not None and analyse.confiance >= self.tete_upos:
            # Catégorie prédite sûre que la graphie de la tête n'a pas, et qu'une concurrente a (eux / euh, a / à) :
            # la catégorie décide.
            choisies = [e for e, _ in candidates if e.ortho.lower() == tete]
            if all(e.upos != analyse.upos for e in choisies) and any(e.upos == analyse.upos for e, _ in candidates):
                tete = ""

        def graphie(e: Entree) -> float:
            return self.poids_graphie * (e.ortho.lower() == tete) if tete else 0.0

        return [(e, ((accord(e, analyse) if sure else 0) + langue(e) + graphie(e), sc)) for e, sc in candidates]

    def _candidates(
        self, cles: list[str], dite: str, tiret: bool, elide: bool, internes: list[str], voisines: bool
    ) -> list[tuple[Entree, float]]:
        """Entrées du lexique prononcées comme ``cles``, de même forme de séparateurs, avec leur score de fréquence."""
        candidates: list[tuple[Entree, float]] = []
        for cle in cles:
            liaison = cle != dite          # lecture en liaison : l'entrée doit avoir cette consonne latente
            exactes = set(self.index.prononciations(cle))
            proches = (set(self.index.prononciations(cle, neutre=True)) - exactes) if voisines else set()
            for e in self.lexique.graphies(sorted(exactes | proches)):
                coeur = e.ortho.removeprefix("-").removesuffix("'")
                if e.ortho.startswith("-") != tiret or e.ortho.endswith("'") != elide:
                    continue
                if [c for c in coeur if c in "-' "] != internes:
                    continue
                h, corps, latente = decomposer(e.phone_enrichi)
                # Prononciations libres « {e|ɛ} » : chacune vaut une prononciation exacte de l'entrée.
                dites = alternatives(e.phone_enrichi) if "{" in e.phone_enrichi else [cle_de(corps)]
                if liaison and all(forme_liee(d, latente) != dite for d in dites):
                    continue
                exacte = _PRIME_EXACTE if cle in dites else 0.0
                candidates.append((e, e.frequence + exacte))
        return candidates

    # ── Correction par la chaîne ───────────────────────────────────────────────

    def corriger(
        self, texte: str, nettoyer: bool = True, canal: str = "dual", ecart: int = 4, confiance: float = 0.85, coherence: bool = False
    ) -> list[PhraseAlignee]:
        """Mode correcteur : lecture (prononciation de chaque mot), analyse sur la prononciation (canal
        « phone ») ou sur la graphie et la prononciation (« dual »), puis graphie attendue de chaque mot ;
        une correction est proposée quand la graphie reçue s'accorde moins bien avec l'analyse (de
        ``ecart`` points au moins ; 4 = une autre catégorie) qu'une graphie homophone, et que l'analyse
        est assez sûre. Réglage par défaut : le plus prudent mesuré (voir ETAT.md)."""
        Correction = _enveloppe("nettoyage").Correction
        phrases = self.lire(texte, corriger=nettoyer)
        for phrase in phrases:
            lus = phrase._lus()
            cles = [self._cle_lue(m) for m in lus]
            if canal == "dual" and hasattr(self.analyseur, "analyser_dual"):
                analyses = self.analyseur.analyser_dual([m.mot.forme for m in lus], [c or "" for c in cles])
            else:
                analyses = self.analyseur.analyser_phone([c or "" for c in cles])
            propositions = self._coherence(lus, cles, analyses) if coherence else [None] * len(lus)
            for m, cle, analyse, proposition in zip(lus, cles, analyses, propositions):
                if proposition is None:
                    if analyse.confiance < confiance:
                        continue
                    proposition = self._graphie_attendue(m, cle, analyse, ecart)
                if proposition is None:
                    continue
                entree, score = proposition
                phrase.corrections.append(Correction(m.mot.debut, m.mot.fin, m.mot.forme, _casse_de(entree.ortho, m.mot.forme), "grammaire", score))
                graphie = _casse_de(entree.ortho, m.mot.forme)
                couples = _a_la_casse(entree.couples, graphie) or entree.couples or (Couple(entree.phone_enrichi, graphie),)
                m.couples, m.phone_enrichi, m.analyse = couples, entree.phone_enrichi, analyse
        return phrases

    def _coherence(self, lus: list[MotAligne], cles: list[str], analyses: list[Analyse]) -> list:
        """Recherche globale (prototype) : graphies homophones choisies ensemble, avec les accords."""
        coherence = _enveloppe("coherence")
        Choix = coherence.Choix
        candidats: list[list] = []
        for m, cle, analyse in zip(lus, cles, analyses):
            forme = m.mot.forme
            recue = choisir(self.lexique.lectures(forme), analyse) if m.origine == "lexique" else None
            choix = [Choix(recue, True)] if recue else [Choix(Entree(forme, analyse.upos, {}, "", "", ()), True)]
            numeral = bool(recue) and recue.upos == "NUM"     # « vingt » ne devient pas « vin »
            if cle and m.origine == "lexique" and m.mot.type is TypeMot.MOT and not m.mot.nature and not numeral and not (forme[:1].isupper() and m.mot.debut > 0):
                tiret, elide = forme.startswith("-"), forme.endswith("'")
                internes = [c for c in forme.removeprefix("-").removesuffix("'") if c in "-' "]
                plancher = (recue.frequence if recue else 0.0) - _ECART_FREQUENCE_COHERENCE
                for e, _s in self._candidates([cle], cle, tiret, elide, internes, voisines=False):
                    # Ni symbole ni sigle (« 30 », « IV »), ni nom propre à la place d'un mot, ni mot bien plus rare.
                    if e.ortho.lower() == forme.lower() or e.type or e.frequence < plancher:
                        continue
                    if e.upos == "PROPN" and not (recue and recue.upos == "PROPN"):
                        continue
                    choix.append(Choix(e, False))
            candidats.append(choix)
        retenus = coherence.choisir(candidats, analyses)
        resultat = []
        for cs, k in zip(candidats, retenus):
            resultat.append(None if cs[k].recue else (self.lexique.aligner(cs[k].entree), 1.0))
        return resultat

    @staticmethod
    def _cle_lue(m: MotAligne) -> str:
        if m.origine not in ("lexique", "modele") or not m.phone_enrichi:
            return ""
        return cle_de(decomposer(m.phone_enrichi)[1])

    def _graphie_attendue(self, m: MotAligne, cle: str, analyse: Analyse, ecart: int = 2) -> tuple[Entree, float] | None:
        """Graphie homophone qui s'accorde strictement mieux avec l'analyse que la graphie reçue."""
        if not cle or m.origine != "lexique" or m.mot.type is not TypeMot.MOT or m.mot.nature:
            return None
        forme = m.mot.forme
        if forme[:1].isupper() and m.mot.debut > 0:
            return None                      # nom propre ou sigle : on ne touche pas
        tiret, elide = forme.startswith("-"), forme.endswith("'")
        internes = [c for c in forme.removeprefix("-").removesuffix("'") if c in "-' "]
        candidates = self._candidates([cle], cle, tiret, elide, internes, voisines=False)
        if not candidates:
            return None
        recues = [c for c in candidates if c[0].ortho.lower() == forme.lower()]
        if not recues:
            return None                      # la graphie reçue n'est pas une lecture connue de cette prononciation
        accord_recu = max(accord(e, analyse) for e, _s in recues)
        meilleure, score = max(candidates, key=lambda c: (accord(c[0], analyse), c[1]))
        if meilleure.ortho.lower() == forme.lower() or accord(meilleure, analyse) - accord_recu < ecart:
            return None
        return self.lexique.aligner(meilleure), float(accord(meilleure, analyse) - accord_recu)

    def _formules_phone(self, mots: list[Mot], analyses: list[Analyse], alignes: list[MotAligne]) -> list[MotAligne]:
        """Formules reconnues sur la phonétique, avant que le choix des graphies ne prenne l'homophone du nombre
        (« di kilɔmɛtʁ » : « dit kilomètres » → « 10 km » ; « tʁwa viʁɡyl sɛ̃k » : « 3 virgules 5 » → « 3,5 »).
        Pour éviter les faux positifs (« sans mettre », « il dit que »), la formule doit contenir un mot d'ancrage
        (unité, heure, mois, devise, virgule…) que l'analyse ne prend pas pour un verbe ; ``alignes`` correspond encore
        mot pour mot à ``mots``."""
        resultat, k = [], 0
        for r in reconnaitre_phone(mots):
            ancres = [j for j in range(r.debut, r.fin) if mot_de(mots[j]) not in _NON_ANCRES
                      and not set(mot_de(mots[j]).split("-")) <= ELEMENTS_NOMBRE]
            # L'ancre doit être analysée comme un nom ou un nombre : « il m'a dit mais » n'est pas « 10 mai », « une ou
            # plusieurs » n'est pas « 1er août » (« mais », « ou » : conjonctions).
            if not ancres and self._nombre_sans_ancre(mots[r.debut : r.fin], analyses[r.debut : r.fin]):
                pass
            elif r.type == "pourcentage":
                pass                         # « vɛ̃ puʁ sɑ̃ » : « pour cent » tient lieu d'ancre (« vint pour 100 » sinon)
            elif not ancres or any(analyses[j].upos not in _UPOS_ANCRE for j in ancres):
                continue
            resultat.extend(alignes[k : r.debut])
            lus = alignes[r.debut : r.fin]
            mot = Mot(TypeMot.FORMULE, r.ecriture, lus[0].mot.debut, lus[-1].mot.fin, type_formule=r.type, valeur=r.valeur)
            resultat.append(MotAligne(mot, origine="formule", analyse=lus[0].analyse, lecture=lus, espace=lus[0].espace))
            k = r.fin
        return resultat + alignes[k:]

    def _accord_des_sujets(self, mots: list[Mot], analyses: list[Analyse], inverses: list[bool],
                           entrees: list[Entree | None], contexte: dict) -> None:
        """« il trouve » / « ils trouvent » : le pronom sujet et son verbe prennent le même nombre. Celui que l'un des deux
        fait entendre (« ils‿ont », « finissent ») ; sinon celui du dernier sujet entendu avant eux, dans la phrase ou la
        précédente (pronom sujet, déterminant du sujet : « les poissons… ils ») ; à défaut celui de l'analyse.
        Mesuré le 17/10 (bancs STT, cadre) : le singulier par défaut, ou le nombre d'un verbe conjugué entendu avant
        (souvent celui d'un autre sujet), font moins bien."""

        def meme_mot(c: Entree, e: Entree) -> bool:
            # Pronom : « il » / « ils » n'ont pas toujours le même lemme dans le lexique.
            if e.upos == "PRON":
                return _SUJETS_3_PAIRES.get(c.ortho.lower()) == _SUJETS_3_PAIRES.get(e.ortho.lower()) is not None
            return c.lemme == e.lemme

        garder = ("Person", "Tense", "Mood", "VerbForm")

        def formes(i: int, upos: tuple[str, ...]) -> list[tuple[Entree, tuple]]:
            """Homophones du mot choisi qui n'en diffèrent que par le nombre (« finisse » subjonctif écarté)."""
            e = entrees[i]
            return [(c, n) for c, n in self._notes_graphie(mots[i], inverses[i], analyses[i])
                    if meme_mot(c, e) and c.upos in upos and all(c.feats.get(k) == e.feats.get(k) for k in garder)]

        def entendu(i: int, upos: tuple[str, ...]) -> str | None:
            e = entrees[i]
            nombre = e.feats.get("Number") if e is not None else None
            if nombre not in ("Sing", "Plur") or e.upos not in upos:
                return None
            return nombre if {c.feats.get("Number") for c, _ in formes(i, upos)} <= {nombre} else None

        def au_nombre(i: int, nombre: str, upos: tuple[str, ...]) -> Entree | None:
            """Entrée du mot ``i`` au nombre voulu (la sienne s'il l'a déjà), ou None si le lexique ne l'a pas."""
            e = entrees[i]
            if e.feats.get("Number") == nombre:
                return e
            notes = [(c, n) for c, n in formes(i, upos) if c.feats.get("Number") == nombre]
            return self.lexique.aligner(max(notes, key=lambda c: c[1])[0]) if notes else None

        verbes = ("VERB", "AUX")
        for i, mot in enumerate(mots):
            e = entrees[i]
            if e is None or mot.type is not TypeMot.MOT:
                continue
            ecrit = e.ortho.lower()
            if ecrit in _SUJETS_3 and e.upos == "PRON" and not inverses[i]:
                v = self._verbe_du_sujet(i, mots, analyses, entrees)
                if v is None:
                    continue
                nombre = entendu(i, ("PRON",)) or entendu(v, verbes) or contexte.get("nombre") \
                    or entrees[i].feats.get("Number")
                # Les deux mots changent ensemble, ou aucun : jamais « elle finissent ».
                pronom, verbe = au_nombre(i, nombre, ("PRON",)), au_nombre(v, nombre, verbes)
                if pronom is not None and verbe is not None:
                    entrees[i], entrees[v] = pronom, verbe
                contexte["nombre"] = entrees[i].feats.get("Number") or nombre
                continue
            # Indice pour la suite : déterminant d'un nom sujet.
            if e.upos == "DET" and analyses[i].tete is not None and 0 <= analyses[i].tete < len(mots) \
                    and analyses[analyses[i].tete].relation.startswith("nsubj"):
                contexte["nombre"] = entendu(i, ("DET",)) or contexte.get("nombre")

    def _accord_des_groupes(self, mots: list[Mot], analyses: list[Analyse], inverses: list[bool],
                            entrees: list[Entree | None], phones: list[str], types: list[str] | None) -> None:
        """Groupe nominal cohérent en nombre, et verbe accordé à un nom sujet entendu. Le nom, ses adjectifs (``amod``) et ses déterminants homophones entre
        singulier et pluriel (« leur » / « leurs ») prennent le même nombre, même quand rien ne s'entend (« en grands
        groupes », « une loi environnementale »). Celui qu'un membre fait entendre (« les », « chevaux »), sinon celui
        du nom (choisi par le juge). Un membre change seulement si le lexique a sa forme homophone au bon nombre."""
        garder = ("Gender", "Person", "Tense", "Mood", "VerbForm")

        def formes(i: int) -> list[tuple[Entree, tuple]]:
            e = entrees[i]
            return [(c, n) for c, n in self._notes_graphie(mots[i], inverses[i], analyses[i])
                    if c.lemme == e.lemme and c.upos == e.upos and all(c.feats.get(k) == e.feats.get(k) for k in garder)]

        def entendu(i: int) -> str | None:
            if entrees[i].ortho.lower() in ("de", "d'"):
                return None                              # « de » : partitif ou préposition, il ne dit pas le nombre
            nombre = entrees[i].feats.get("Number")
            if nombre not in ("Sing", "Plur"):
                return None
            return nombre if {c.feats.get("Number") for c, _ in formes(i)} <= {nombre} else None

        def au_nombre(i: int, nombre: str) -> None:
            if entrees[i].feats.get("Number") in ("Sing", "Plur") and entrees[i].feats["Number"] != nombre:
                notes = [(c, x) for c, x in formes(i) if c.feats.get("Number") == nombre]
                if notes:
                    entrees[i] = self.lexique.aligner(max(notes, key=lambda c: c[1])[0])

        n = len(mots)
        if not any(e is not None and e.upos == "NOUN" for e in entrees):
            return
        # Liens entre mots : ceux de la phrase écrite (graphies choisies et prononciation), plus sûrs que ceux de la
        # prononciation seule (« véhicules industriels lourds » rattaché au bon nom).
        arcs = analyses
        if hasattr(self.analyseur, "analyser_dual"):
            ecrits = [e.ortho if e is not None else (m.forme if m.type is not TypeMot.MOT else "") for m, e in zip(mots, entrees)]
            arcs = self.analyseur.analyser_dual(ecrits, phones, **({"types": types} if types else {}))
        analyses = [replace(a, tete=b.tete, relation=b.relation) for a, b in zip(analyses, arcs)]
        for h in range(n):
            nom = entrees[h]
            if nom is None or nom.upos != "NOUN" or nom.feats.get("Number") not in ("Sing", "Plur"):
                continue
            # Nom sujet dont le nombre s'entend (« des‿éboulements ») : son verbe conjugué, ses auxiliaires et son
            # participe le prennent (« s'étaient produits »).
            dets = [i for i in range(n) if entrees[i] is not None and analyses[i].tete == h and analyses[i].relation == "det"
                    and entrees[i].upos == "DET"]
            sujet = {x for x in (entendu(i) for i in [h, *dets]) if x}
            v = analyses[h].tete
            # Pluriel seulement (« la plupart […] portent ») ; pas de sujet coordonné (« la connaissance et la compréhension »).
            coordonne = any(analyses[k].tete == h and analyses[k].relation == "conj" for k in range(n))
            if sujet == {"Plur"} and not coordonne and analyses[h].relation.startswith("nsubj") and v is not None \
                    and h < v < n and entrees[v] is not None and entrees[v].upos in ("VERB", "AUX"):
                nombre = next(iter(sujet))
                lies = [v] + [k for k in range(n) if entrees[k] is not None and analyses[k].tete == v
                              and analyses[k].relation in ("aux", "aux:pass", "aux:tense", "cop")]
                avec_etre = any(entrees[k].lemme == "être" for k in lies[1:])       # « ont lu » : pas d'accord
                for k in lies:
                    e = entrees[k]
                    if e.feats.get("VerbForm") == "Fin" or (k == v and avec_etre and e.feats.get("VerbForm") == "Part"):
                        au_nombre(k, nombre)
            membres = [i for i in range(n) if i != h and entrees[i] is not None and analyses[i].tete == h
                       and ((analyses[i].relation == "amod" and entrees[i].upos == "ADJ")
                            or (analyses[i].relation == "det" and entrees[i].upos == "DET"))]
            if not membres:
                continue
            entendus = {x for x in (entendu(i) for i in [h, *membres]) if x}
            if len(entendus) > 1:
                continue                                 # indices contraires : on ne touche à rien
            nombre = entendus.pop() if entendus else nom.feats["Number"]
            # « hôpitaux de campagne gratuits » : l'adjectif peut aller au nom dont celui-ci est le complément ; s'il
            # s'accorde déjà avec lui, il reste.
            g = analyses[h].tete
            premier = entrees[g] if analyses[h].relation == "nmod" and g is not None and 0 <= g < n else None
            for i in [h, *membres]:
                if i != h and entrees[i].upos == "ADJ" and premier is not None and premier.upos == "NOUN" \
                        and entrees[i].feats.get("Number") == premier.feats.get("Number"):
                    continue
                au_nombre(i, nombre)

    @staticmethod
    def _verbe_du_sujet(i: int, mots: list[Mot], analyses: list[Analyse], entrees: list[Entree | None]) -> int | None:
        """Verbe conjugué dont le pronom ``i`` est le sujet : sa tête d'analyse, sinon le premier verbe qui suit, par-dessus
        les clitiques (« il ne se le dit »)."""
        t = analyses[i].tete
        if analyses[i].relation.startswith("nsubj") and t is not None and 0 <= t < len(mots) and entrees[t] is not None \
                and entrees[t].upos in ("VERB", "AUX") and entrees[t].feats.get("VerbForm") == "Fin":
            return t
        for j in range(i + 1, min(i + 5, len(mots))):
            e = entrees[j]
            if e is None:
                return None
            if e.upos in ("VERB", "AUX"):
                return j if e.feats.get("VerbForm") == "Fin" else None
            if e.ortho.lower() not in _CLITIQUES_PREVERBAUX:
                return None
        return None

    def _numeral_lie(self, mots: list[Mot], analyses: list[Analyse], entrees: list[Entree | None]) -> None:
        """« di.z‿a.ʒɑ̃ » : dix agents, pas « disent agents ». Devant un nom, la liaison en /z/ de /di/ ou /si/ est
        celle du numéral (dix, six), que l'analyse prend parfois pour un verbe."""
        for i, mot in enumerate(mots[:-1]):
            if mot.type is not TypeMot.MOT or mot.jonction not in (LIAISON, AMBIGU) or mot_de(mot) not in ("dix", "six"):
                continue
            if not "".join(s.forme for s in mot.segments).endswith("z") or analyses[i + 1].upos not in ("NOUN", "ADJ"):
                continue
            entree = self._graphie(mot, False, replace(analyses[i], upos="NUM", feats={}))
            if entree is not None and entree.ortho.lower() == mot_de(mot):
                entrees[i] = entree

    def _nombre_sans_ancre(self, mots: list[Mot], analyses: list[Analyse]) -> bool:
        """Suite de mots de nombre assez sûre pour être un nombre sans ancre (``_NOMBRE_SUR``) ; option
        ``nombres_sans_ancre``. Un mot analysé comme verbe l'exclut (« ʒə di mil fwa » : je dis mille fois)."""
        if not self.nombres_sans_ancre or len(mots) < 2 or any(a.upos in ("VERB", "AUX") for a in analyses):
            return False
        elements = [e for m in mots for e in mot_de(m).split("-")]
        if not set(elements) <= ELEMENTS_NOMBRE:
            return False
        return len(mots) >= 3 or bool(set(elements) & _NOMBRE_SUR)

    def _pluriel_apres_nombre(self, alignes: list[MotAligne]) -> None:
        """Nom (et adjectifs) qui suivent un nombre entier ≥ 2 : graphie homophone au pluriel du même lemme (« 800
        habitants », « 3 grands arbres ») ; l'analyse, faite sur la phonétique, ne voit pas toujours le nombre
        (« ɥi sɑ̃ » pris pour un nom)."""
        for i, m in enumerate(alignes):
            valeur = m.mot.valeur if m.mot.type is TypeMot.FORMULE else None
            if getattr(m.mot, "type_formule", "") != "nombre" or valeur is None or valeur.decimales or valeur.negatif:
                continue
            if not valeur.entier.isdigit() or int(valeur.entier) < 2:
                continue
            if len(valeur.entier) == 4 and 1000 <= int(valeur.entier) <= 2100:
                continue                     # année probable (« en 1800 disparition »)
            lus = m.lecture or []
            if len(lus) == 1 and "".join(c.graphe for c in lus[0].couples).lower() in _NOMBRES_HOMOPHONES:
                continue                     # « sept » seul : souvent « cette » mal entendu (« 7 scène »)
            for suivant in alignes[i + 1 : i + 3]:
                if suivant.origine != "lexique" or suivant.mot.type is not TypeMot.MOT or suivant.analyse is None:
                    break
                if suivant.analyse.upos not in ("NOUN", "ADJ"):
                    break                    # « 3 ou 4 », « 5 sur », « 2005 tout »
                ecrit = "".join(c.graphe for c in suivant.couples if c != SYLLABE)
                actuelles = [e for e in self.lexique.lectures(ecrit) if e.upos in ("NOUN", "ADJ")]
                if not actuelles:
                    break
                if all(e.feats.get("Number") != "Sing" for e in actuelles):
                    if any(e.upos == "NOUN" for e in actuelles):
                        break
                    continue
                pluriel = replace(suivant.analyse, feats={**suivant.analyse.feats, "Number": "Plur"})
                notes = self._notes_graphie(suivant.mot, False, pluriel)
                lemmes = {e.lemme for e in actuelles}
                choix = [(e, n) for e, n in notes if e.feats.get("Number") == "Plur" and e.lemme in lemmes
                         and e.upos in ("NOUN", "ADJ")]
                if not choix:
                    break
                entree = self.lexique.aligner(max(choix, key=lambda c: c[1])[0])
                suivant.couples = entree.couples or (Couple(entree.phone_enrichi, entree.ortho),)
                suivant.phone_enrichi = entree.phone_enrichi
                if entree.upos == "NOUN":
                    break

    def _sigles_annonces(self, alignes: list[MotAligne]) -> list[MotAligne]:
        """Sigle entre parenthèses après sa forme longue : « … pour le développement durable (i.ɛf.de.de) » → « (IFDD) ».
        Les initiales des derniers mots (mots-outils sautés, ou tous les mots) proposent un sigle ; il est retenu s'il se
        lit exactement comme le contenu de la parenthèse, épelé ou lu comme un mot."""
        k = 0
        while k < len(alignes):
            fin = next((j for j in range(k + 2, min(k + 8, len(alignes))) if _ecrit(alignes[j]) == ")"), None) \
                if _ecrit(alignes[k]) == "(" else None
            dedans = alignes[k + 1:fin] if fin else []
            if not dedans or any(m.mot.type is not TypeMot.MOT or m.lecture for m in dedans):
                k += 1
                continue
            dit = "".join(re.sub(r"[ .‿]", "", m.phone) for m in dedans)
            mots = [_ecrit(m).rstrip("'’") for m in alignes[:k] if m.mot.type is TypeMot.MOT and _ecrit(m)[:1].isalpha()]
            pleins = [w for w in mots if w.lower() not in _HORS_INITIALES]
            initiales = lambda ws, n: "".join(unicodedata.normalize("NFD", w)[0].upper() for w in ws[-n:])
            for sigle in dict.fromkeys(initiales(ws, n) for n in range(6, 1, -1) for ws in (pleins, mots) if len(ws) >= n):
                lu = self._lecture_sigle(sigle)
                if sigle.isalpha() and lu is not None and re.sub(r"[ .‿]", "", lu.phone) == dit:
                    mot = replace(dedans[0].mot, forme=sigle, fin=dedans[-1].mot.fin)
                    alignes[k + 1:fin] = [replace(lu, mot=mot, origine="sigle", phone="".join(m.phone for m in dedans),
                                                  espace=dedans[0].espace, jonction=dedans[-1].jonction)]
                    break
            k += 1
        return alignes

    def _lecture_sigle(self, sigle: str) -> MotAligne | None:
        if sigle not in self._lectures_sigles:
            mots = [m for p in self.lire(sigle) for m in p.mots if m.mot.type is TypeMot.MOT]
            self._lectures_sigles[sigle] = mots[0] if len(mots) == 1 else None
        return self._lectures_sigles[sigle]

    def _rare_pour_sigle(self, forme: str) -> bool:
        """Mot du lexique assez rare pour cacher un sigle épelé (« Hercé » RC, « Becca » BK, « cavé » KV) : nom propre
        seulement, de zipf sous ``_RARE`` ; sinon zipf sous 2."""
        entrees = self.lexique.lectures(forme)
        zipf = max((e.frequence for e in entrees), default=0.0)
        return zipf < (_RARE if all(e.upos == "PROPN" for e in entrees) else 2.0)

    def _frequence_forme(self, forme: str) -> float:
        """Zipf le plus haut des lectures de ``forme`` dans le lexique (0 si elle n'y est pas)."""
        return max((e.frequence for e in self.lexique.lectures(forme)), default=0.0)

    def _formules_dites(self, alignes: list[MotAligne]) -> list[MotAligne]:
        """Remplace les suites de mots qui disent une formule par sa forme écrite."""
        ecrits = ["".join(c.graphe for c in m.couples if c != SYLLABE) if m.origine == "lexique" else "\u2205" for m in alignes]
        resultat, k = [], 0
        for r in reconnaitre(ecrits):
            resultat.extend(alignes[k : r.debut])
            lus = alignes[r.debut : r.fin]
            mot = Mot(TypeMot.FORMULE, r.ecriture, lus[0].mot.debut, lus[-1].mot.fin, type_formule=r.type, valeur=r.valeur)
            resultat.append(MotAligne(mot, origine="formule", analyse=lus[0].analyse, lecture=lus, espace=lus[0].espace))
            k = r.fin
        return resultat + alignes[k:]

    # ── Jonctions ──────────────────────────────────────────────────────────────

    @staticmethod
    def _resyllaber_compose(m: MotAligne, corps: str) -> str:
        """Composé à espace élidé devant voyelle (« bien qu'il ») : la consonne élidée ouvre la syllabe du mot suivant
        (« kil ») et ne se rattache plus au mot qui précède : « bjɛ̃‿k » → « bjɛ̃.k‿il » (syllabes bjɛ̃ / kil).
        Le lexique écrit « bjɛ̃‿k » (consonne élidée rattachée à gauche, comme « lorsqu' » lɔʁsk), juste pour le
        composé seul. Gardé après « s » (« parce qu'il » : paʁ.skil, groupe « sk » possible en attaque)."""
        avant, sep, elidee = corps.rpartition("‿")
        if not sep or not avant or "." in elidee or avant.endswith("s"):
            return corps
        for k in range(len(m.couples) - 1, -1, -1):
            if m.couples[k].phone == "‿":
                m.couples = (*m.couples[:k], Couple(".", m.couples[k].graphe), *m.couples[k + 1:])
                break
        return avant + "." + elidee

    def _jonctions(self, mots: list[MotAligne]) -> None:
        for i, m in enumerate(mots):
            suivant = mots[i + 1] if i + 1 < len(mots) else None
            avant = " " if m.mot.espace_avant else ""
            if not est_prononce(m):
                m.phone = avant + (m.mot.forme if m.mot.type is TypeMot.PONCTUATION else "")
                continue
            h, corps, latente = decomposer(m.phone_enrichi)
            voisin = suivant is not None and est_prononce(suivant) and suivant.mot.type is not TypeMot.PONCTUATION
            if not voisin:
                m.phone = corps
                continue
            h_suivant, corps_suivant, _ = decomposer(suivant.phone_enrichi)
            voyelle = commence_par_voyelle(corps_suivant) and not h_suivant
            if m.schwa_final and voyelle and self.enchainements:
                # « grande amie » : le schwa ajouté s'élide devant la voyelle, la consonne s'enchaîne.
                corps = sans_schwas(corps, [corps.count(SCHWA) - 1])
                m.couples = _sans_schwa_final(m.couples)
            clitique = suivant.mot.forme.startswith("-")
            if m.mot.forme.endswith("'"):
                if " " in m.mot.forme and self.elisions:
                    corps = self._resyllaber_compose(m, corps)
                m.jonction, m.phone = ELISION, corps + ("‿" if self.elisions else ".")
                continue
            decision = jonction(self._contexte(m), self._contexte(suivant))
            m.regle = decision.regle
            if self.liaisons and decision.realisee(self.politique):
                m.jonction, m.phone = LIAISON_, lier(corps, latente)
                continue
            if not voyelle:
                corps = devant_consonne(corps, latente) if self._determine(m, suivant) else corps
            if voyelle and corps.endswith("nœf") and m.analyse and m.analyse.upos == "NUM" \
                    and suivant.mot.forme.lower() in ("ans", "heure", "heures"):
                corps = corps[:-1] + "v"                 # « neuf ans », « neuf heures » : /nœ.v‿ɑ̃/
            enchaine = enchainer(corps) if voyelle and self.enchainements else None
            if enchaine:
                m.jonction, m.phone = ENCHAINEMENT, enchaine
            elif clitique:
                m.jonction, m.phone = CLITIQUE, corps + "."
            else:
                m.jonction, m.phone = ESPACE, corps
        # L'espace se place devant le mot qui suit un mot non lié.
        for i, m in enumerate(mots):
            if i and est_prononce(m) and est_prononce(mots[i - 1]) and mots[i - 1].jonction == ESPACE:
                m.phone = " " + m.phone
            elif i and est_prononce(m) and not est_prononce(mots[i - 1]) and m.mot.espace_avant:
                m.phone = " " + m.phone
            if est_prononce(m) and i + 1 < len(mots) and not est_prononce(mots[i + 1]):
                m.jonction = COLLE if not mots[i + 1].mot.espace_avant else ESPACE

    @staticmethod
    def _determine(m: MotAligne, suivant: MotAligne) -> bool:
        """Un numéral devant le nom ou l'adjectif qu'il détermine (« dix livres » : /di/), ou devant un numéral
        multiplicateur (« six cents », « dix mille » : /si sɑ̃/, /di mil/)."""
        if not (m.analyse and suivant.analyse and m.analyse.upos == "NUM"):
            return False
        return suivant.analyse.upos in ("NOUN", "ADJ") or suivant.mot.forme.lower() in _MULTIPLICATEURS

    @staticmethod
    def _contexte(m: MotAligne) -> MotAnalyse:
        h, corps, latente = decomposer(m.phone_enrichi)
        a = m.analyse or Analyse("X")
        upos = a.upos
        if upos == "MWT" and m.mot.forme.lower() in _AMALGAMES_ARTICLE:
            upos = "DET"                       # « des », « aux » (de + les, à + les) : liaison d'article (« parler des amis »)
        return MotAnalyse(m.mot.forme, upos, corps, latente, h, a.lemme, a.feats)


def _forme(h: bool, corps: str, latente: str) -> str:
    """Prononciation enrichie recomposée après une retouche du corps (marques h aspiré et latente gardées)."""
    return ("*h*" if h else "") + corps + latente


def _schwas_finaux(alignes: list[MotAligne]) -> None:
    """Ajoute le schwa des « e » finals muets après consonne, sur la forme du mot (avant les jonctions, qui
    l'élideront devant voyelle si l'enchaînement est actif), avec resyllabation."""
    for m in alignes:
        if not est_prononce(m) or m.mot.type is TypeMot.PONCTUATION or not m.couples or m.mot.forme.endswith("'"):
            continue
        h, corps, latente = decomposer(m.phone_enrichi)
        # Dernier « e » muet du mot, sans phonème après lui (« table », « tables », « parlent »).
        k = next((j for j in range(len(m.couples) - 1, -1, -1) if _phoneme_de(m.couples[j])), -1)
        cible = next((j for j in range(len(m.couples) - 1, k, -1) if "e" in m.couples[j].graphe.lower()), None)
        if cible is None or not corps or corps[-1] in "aeɛioɔuyøœəɑ̃":
            continue
        c = m.couples[cible]
        position = c.graphe.lower().rfind("e")
        avant, e, apres = c.graphe[:position], c.graphe[position], c.graphe[position + 1 :]
        nouveaux = ([Couple("", avant)] if avant else []) + [Couple(SCHWA if apres else SCHWA + c.phone, e)]
        nouveaux += [Couple(c.phone, apres)] if apres else []
        m.couples = m.couples[:cible] + tuple(nouveaux) + m.couples[cible + 1 :]
        m.phone_enrichi = _forme(h, avec_schwa_final(corps), latente)
        m.schwa_final = True


def _sans_schwa_final(couples: tuple[Couple, ...]) -> tuple[Couple, ...]:
    """Le « e » final redevient muet (schwa ajouté puis élidé devant voyelle)."""
    for j in range(len(couples) - 1, -1, -1):
        if couples[j].phone.startswith(SCHWA) and couples[j].graphe.lower() == "e":
            return couples[:j] + (Couple(couples[j].phone[len(SCHWA) :], couples[j].graphe),) + couples[j + 1 :]
    return couples


def _phoneme_de(c: Couple) -> bool:
    """Le couple porte-t-il un phonème réalisé (hors marques de consonne latente) ?"""
    return c != SYLLABE and c.graphe not in ("-", "'", " ") and bool(alternatives(c.phone)[0] if c.phone else "")


def _e_caducs(alignes: list[MotAligne]) -> None:
    """Fait tomber les e caducs de la phrase (règle R3), dans la prononciation et dans les couples."""
    groupes: list[list[MotAligne]] = [[]]
    for m in alignes:
        if est_prononce(m) and m.mot.type is not TypeMot.PONCTUATION:
            groupes[-1].append(m)
        elif groupes[-1]:
            groupes.append([])           # pause : le groupe suivant repart en tête
    groupes = [g for g in groupes if g]
    formes = [[decomposer(m.phone_enrichi) for m in g] for g in groupes]
    rangs = chutes([[corps for _h, corps, _l in f] for f in formes])
    for m, (h, corps, latente), r in zip([m for g in groupes for m in g], [x for f in formes for x in f], rangs):
        if not r or m.mot.forme.startswith("-"):
            continue                     # clitique après le verbe (« prends-le ») : accentué, il reste
        m.phone_enrichi = _forme(h, sans_schwas(corps, r), latente)
        couples, rang = [], 0
        for c in m.couples:
            phone = c.phone
            if SCHWA in phone and c != SYLLABE:
                if rang in r:
                    phone = phone.replace(SCHWA, "", 1)
                rang += phone.count(SCHWA) + (phone != c.phone)
            couples.append(Couple(phone, c.graphe))
        m.couples = tuple(couples)


_CAPITALES_ACCENTUABLES = {"E": "ÉÈÊ", "A": "À", "I": "Î", "O": "Ô", "U": "Ù"}
_SANS_ACCENT_INITIAL = {a: e for e, accentuees in _CAPITALES_ACCENTUABLES.items() for a in accentuees}


def _a_la_casse(couples: tuple[Couple, ...], forme: str) -> tuple[Couple, ...]:
    """Rend aux graphèmes la casse du texte (majuscule de début de phrase sur une entrée en minuscules), et la
    capitale sans accent du texte (« Eglise » lu comme « Église »)."""
    ecrit = "".join(c.graphe for c in couples if c != SYLLABE)
    capitale = bool(ecrit) and _SANS_ACCENT_INITIAL.get(ecrit[0].upper()) == forme[:1] and ecrit[1:].lower() == forme[1:].lower()
    if ecrit == forme or (ecrit.lower() != forme.lower() and not capitale):
        return couples
    resultat, reste = [], forme
    for c in couples:
        if c == SYLLABE:
            resultat.append(c)
        else:
            resultat.append(replace(c, graphe=reste[: len(c.graphe)]))
            reste = reste[len(c.graphe) :]
    return tuple(resultat)


def _majuscule_initiale(alignes: list[MotAligne]) -> None:
    """Majuscule au premier mot écrit de la phrase."""
    for m in alignes:
        if m.lecture or m.origine != "lexique":
            if m.origine in ("formule", "inconnu", "sigle"):
                return
            continue
        for k, c in enumerate(m.couples):
            if c.graphe[:1].isalpha():
                m.couples = m.couples[:k] + (replace(c, graphe=c.graphe[0].upper() + c.graphe[1:]),) + m.couples[k + 1 :]
                return
        return


def _casse_de(graphie: str, modele: str) -> str:
    """Donne à la graphie proposée la casse du mot reçu (majuscule initiale)."""
    return graphie[0].upper() + graphie[1:] if modele[:1].isupper() and graphie else graphie
