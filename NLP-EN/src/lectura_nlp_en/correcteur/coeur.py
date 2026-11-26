# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Cœur du correcteur anglais : la chaîne du transducteur anglais (découpage, analyse UD, prononciation de chaque
mot), le lexique anglais (lectura-lexicon-en) et un modèle de langue écrit (KenLM 4-grammes).

Étapes, du plus sûr au plus coûteux (même principe que le français : garder ce qui a été écrit autant que possible) :
1. règles sûres : « i » → « I », contractions sans apostrophe (dont → don't), mot répété, « could of » → « could
   have » ;
2. fautes connues du lexique (seperate → separate) et mots inconnus : voisins orthographiques et phonétiques, mots
   collés, jugés par le modèle de langue ;
3. accords et formes verbales justifiés par l'analyse (sujet → verbe, déterminant → nom, modal / do / to → base
   verbale, have → participe passé), le modèle de langue ne pouvant que s'y opposer franchement ;
4. « a » / « an » d'après la prononciation du mot suivant ;
5. confusions (their / there / they're, then / than…) et homophones du lexique, jugés par le modèle de langue.

Modes : « suggestions » (correcteur interactif), « automatique » (avant TTS : presque aucune fausse correction),
« collecte » (toutes les décisions, avec leurs mesures, pour régler les seuils hors ligne).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .explications import PERSONNES, astuce, texte as gabarit
from .regles import (APOSTROPHES, APOSTROPHES_AMBIGUES, APOSTROPHES_AMBIGUES_ACTIVES, CONFUSIONS, DEMONSTRATIFS,
                     DET_PLURIEL, DET_SINGULIER, DOUBLES_ADMIS, MODAUX, MODAUX_OF, OUTILS, QUANTIFIEURS, variantes_gb_us)
from .tete import phone_jeton

# Écarts de log10 P(phrase) exigés (gain de la phrase corrigée sur la phrase reçue, coûts déduits).
MARGES_HORS_LEXIQUE = {"suggestions": 2.0, "automatique": 3.0, "collecte": -1e9}
MARGES_VARIANTE = {"suggestions": -1.0, "automatique": 0.0, "collecte": -1e9}
MARGES_ACCORD = {"suggestions": 0.0, "automatique": 0.5, "collecte": -1e9}
MARGES_DETERMINANT = {"suggestions": 1.0, "automatique": 1.5, "collecte": -1e9}
MARGES_APOSTROPHE_AMBIGUE = {"suggestions": 1.0, "automatique": 2.0, "collecte": -1e9}
MARGES_MODAL_OF = {"suggestions": -1.0, "automatique": 0.0, "collecte": -1e9}
MARGES_CONFUSION = {"suggestions": 2.0, "automatique": 3.0, "collecte": -1e9}
MARGES_HOMOPHONE = {"suggestions": 3.0, "automatique": 4.0, "collecte": -1e9}
MARGES_POSSESSIF = {"suggestions": 1.0, "automatique": 2.0, "collecte": -1e9}
MARGES_POSSESSIF_PROPRE = {"suggestions": 0.5, "automatique": 1.0, "collecte": -1e9}
# Mots en -s qui ne sont pas des possessifs de nom propre (pronoms, contractions sans apostrophe : autres règles).
NON_POSSESSIFS = {"its", "lets", "hers", "ours", "yours", "theirs", "whats", "thats", "heres", "theres", "wheres",
                  "hes", "shes", "whos", "this", "thus", "was", "has", "is", "as", "us", "yes", "plus", "always"}
ZIPF_HOMOPHONE = 3.0
# Homophones jugés par la tête de graphie du modèle de phrase (``tete.py``) : écart p(meilleure) − p(reçue),
# 1 − p(reçue), et gain KenLM de la phrase corrigée (second juge).
SEUILS_TETE = {"suggestions": [("ecart", 0.8), ("non_recue", 0.99), ("gain", 0.5)],
               "automatique": [("ecart", 0.9), ("non_recue", 0.998), ("gain", 0.5)],
               "collecte": [("ecart", -1e9)]}
# Mots qui annoncent un groupe nominal possesseur (« the / his fathers house »).
POSSESSEURS = {"the", "his", "her", "my", "your", "our", "their", "its", "this", "that", "every", "each", "whose",
               "these", "those", "both", "all"}
_ACCORDS = ("accord_sujet", "determinant_sing", "determinant_plur", "determinant_demonstratif", "base_modal",
            "base_do", "base_to", "participe_have", "participe_be")
# Seuil de chaque règle par mode : (mesure, valeur minimale) ; les règles absentes passent toujours (i_majuscule,
# apostrophe sûre, doublon, articles). Le réglage hors ligne (banc/balayer.py) lit cette table.
GAINS_HORS_LEXIQUE = {"suggestions": 0.0, "automatique": 0.0, "collecte": -1e9}
SEUILS_MODE = {mode: {"variante": ("gain", MARGES_VARIANTE[mode]),
                      "hors_lexique": [("marge", MARGES_HORS_LEXIQUE[mode]), ("gain", GAINS_HORS_LEXIQUE[mode])],
                      "scission": [("marge", MARGES_HORS_LEXIQUE[mode]), ("gain", GAINS_HORS_LEXIQUE[mode])],
                      "apostrophe_ambigue": ("gain", MARGES_APOSTROPHE_AMBIGUE[mode]),
                      "modal_of": ("gain", MARGES_MODAL_OF[mode]), "confusion": ("gain", MARGES_CONFUSION[mode]),
                      "homophone": ("gain", MARGES_HOMOPHONE[mode]), "homophone_tete": SEUILS_TETE[mode],
                      **{r: ("gain", MARGES_POSSESSIF[mode]) for r in ("possessif_sing", "possessif_plur")},
                      "possessif_propre": ("gain", MARGES_POSSESSIF_PROPRE[mode]), **{r: ("gain", MARGES_ACCORD[mode]) for r in _ACCORDS},
                      **{r: ("gain", MARGES_DETERMINANT[mode]) for r in _ACCORDS if r.startswith("determinant")}}
               for mode in ("suggestions", "automatique", "collecte")}                 # homophone générique proposé seulement s'il est courant
COUT = {("ortho", 1): 1.0, ("ortho", 2): 2.5, ("phone", 0): 0.5, ("phone", 1): 2.0, ("scission", 1): 1.5}
# candidat seul : marge accordée selon l'origine et la distance (sinon 2,0)
SEUL = {("ortho", 1): 3.0, ("phone", 0): 3.0, ("ortho", 2): 2.5, ("phone", 1): 2.0, ("scission", 1): 2.0}
ALPHABET = set("abcdefghijklmnopqrstuvwxyz'-")
OUTILS_UPOS = {"DET", "ADP", "PRON", "AUX", "CCONJ", "SCONJ", "PART"}
VALIDES = ("proposable", "acceptee")
VOYELLES = {"ɑ", "æ", "ɔ", "aʊ", "aɪ", "ɛ", "eɪ", "ɪ", "i", "oʊ", "ɔɪ", "ʊ", "u", "ʌ", "ə", "ɝ", "ɚ"}
PRONOMS_SUJETS = {"i": "1s", "you": "2", "he": "3s", "she": "3s", "it": "3s", "we": "p", "they": "p",
                  "this": "3s", "that": "3s", "these": "p", "those": "p", "everyone": "3s", "everybody": "3s",
                  "someone": "3s", "somebody": "3s", "nobody": "3s", "no one": "3s", "anyone": "3s",
                  "anybody": "3s", "everything": "3s", "something": "3s", "nothing": "3s", "anything": "3s",
                  "each": "3s", "one": "3s"}
COLLECTIFS = {"number", "majority", "lot", "couple", "group", "family", "team", "staff", "police", "government",
              "committee", "class", "crowd", "audience", "public", "board", "band", "company", "jury", "army",
              "rest", "half", "percent", "per", "none", "all", "some", "most", "any", "more", "kind", "sort", "type",
              "series", "species", "variety", "range", "pair", "total", "data", "media", "news", "politics",
              "means", "headquarters", "physics", "mathematics", "economics", "people", "crew", "personnel",
              "family", "couple", "class", "faculty", "council", "management", "enemy", "majority", "minority"}
# verbes et adjectifs qui appellent le subjonctif (« suggest that she get », « it is essential that he be »)
SUBJONCTIF = {"suggest", "insist", "recommend", "demand", "require", "ask", "propose", "request", "urge", "order",
              "advise", "prefer", "essential", "important", "necessary", "vital", "crucial", "imperative", "need",
              "underscore", "mandate", "stipulate", "decree", "move", "pray", "wish", "god", "lest"}
_ADRESSE_RE = re.compile(r"(?:https?://|www\.)\S+|[\w.+-]+@[\w-]+\.[\w.]+|\b[\w-]+\.(?:com|org|net|io|edu|gov|uk)\b")
_INDEX_CONFUSIONS: dict[str, set[str]] = {}
for _g in CONFUSIONS:
    for _m in _g:
        _INDEX_CONFUSIONS.setdefault(_m, set()).update(_g - {_m})


@dataclass
class Correction:
    debut: int
    fin: int
    original: str
    proposition: str
    type: str                 # orthographe, apostrophe, accord, forme_verbale, article, confusion, homophone…
    confiance: float
    motif: str = ""
    mesures: dict = field(default_factory=dict)
    explication: str = ""


@dataclass
class Resultat:
    texte: str
    corrections: list[Correction] = field(default_factory=list)


@dataclass
class Jeton:
    """Jeton de surface : un mot écrit, contraction comprise (do + n't = « don't »), avec l'analyse de son hôte."""

    i: int
    lus: list
    debut: int
    fin: int
    forme: str
    analyse: object = None
    phone: str = ""
    origine: str = ""
    mot: bool = False

    @property
    def bas(self) -> str:
        return self.forme.lower().replace("’", "'")

    @property
    def hote(self):
        return self.lus[0]


def _casse(graphie: str, modele: str) -> str:
    if modele[:1].isupper() and graphie[:1].islower():
        return graphie[:1].upper() + graphie[1:]
    return graphie


def appliquer(texte: str, corrections: list[Correction]) -> str:
    for c in sorted(corrections, key=lambda c: c.debut, reverse=True):
        texte = texte[:c.debut] + c.proposition + texte[c.fin:]
    return texte


def jetons_de(phrase, texte: str) -> list[Jeton]:
    """Jetons de surface d'une phrase lue : les clitiques (n't, 's, 're…) rejoignent leur hôte, les mots d'une
    formule lue sont chacun un jeton, un abrègement épelé reste un jeton (même découpage que l'analyseur, dont les
    indices de tête désignent ces jetons)."""
    from ..analyseur.structures import TypeMot

    groupes: list[list] = []
    for m in phrase.mots:
        if m.lecture and m.mot.type is TypeMot.FORMULE:
            groupes += [[lu] for lu in m.lecture]
        elif m.lecture:
            groupes.append([m] + [])                        # abrègement épelé : un jeton (hôte = le mot écrit)
        elif m.clitique and groupes:
            groupes[-1].append(m)
        else:
            groupes.append([m])
    res = []
    for i, g in enumerate(groupes):
        debut, fin = g[0].mot.debut, g[-1].mot.fin
        h = g[0]
        mot = h.mot.type is TypeMot.MOT and h.origine not in ("formule",)
        res.append(Jeton(i, g, debut, fin, texte[debut:fin], h.analyse, h.phone_enrichi or h.phone.strip("‿ "),
                         h.origine, mot))
    return res


class Correcteur:
    def __init__(self, chaine=None, lexique=None, juge=None, langue: str = "fr", variete: str | None = None,
                 models_dir=None, transducer_dir=None, tete=None):
        """``langue`` : langue des explications (« fr », défaut, ou « en ») ; ``variete`` : « US » pour signaler les
        graphies britanniques (suggestion), sinon les deux sont admises. Sans ``juge`` : le reste est chargé depuis les
        dossiers de modèles (``charger``), en gardant la ``chaine`` et le ``lexique`` donnés."""
        if chaine is None or juge is None:
            from . import charger

            c = charger(models_dir, transducer_dir, lexique, chaine=chaine, langue=langue, variete=variete,
                        tete=tete)
            self.__dict__.update(c.__dict__)
            return
        self.chaine = chaine                      # lectura_nlp_en.analyseur.chaine.Chaine
        self.lex = lexique                        # lectura_lexicon.Lexicon(langue="en"), local, taille standard
        self.juge = juge                          # langue.Juge
        self.langue = langue
        self.variete = variete
        self.tete = tete or None                  # tete.TeteGraphie (homophones en contexte), ou None
        self._conj: dict[str, dict] = {}

    # ── entrée ──────────────────────────────────────────────────────────────

    def corriger(self, texte: str, mode: str = "suggestions", langue: str | None = None) -> Resultat:
        langue = langue or self.langue
        corrections: list[Correction] = []
        for phrase in self.chaine.lire(texte):
            jetons = jetons_de(phrase, texte)
            if not jetons:
                continue
            ctx = _Contexte(self, texte, jetons, mode, langue)
            ctx.corriger()
            corrections += ctx.resultat()
        adresses = [(a.start(), a.end()) for a in _ADRESSE_RE.finditer(texte)]
        corrections = [c for c in corrections if not any(c.debut < f and c.fin > d for d, f in adresses)]
        return Resultat(appliquer(texte, corrections), corrections)

    # ── lexique ─────────────────────────────────────────────────────────────

    def conj(self, lemme: str) -> dict:
        if lemme not in self._conj:
            self._conj[lemme] = self.lex.conjuguer(lemme) if lemme else {}
        return self._conj[lemme]

    def base(self, lemme: str) -> str:
        return self.conj(lemme).get("Inf", {}).get("Pres", {}).get("-", "")

    def troisieme(self, lemme: str) -> str:
        return self.conj(lemme).get("Ind", {}).get("Pres", {}).get("3s", "")

    def participe(self, lemme: str) -> str:
        return self.conj(lemme).get("Part", {}).get("Past", {}).get("-", "")

    def preterit(self, lemme: str) -> str:
        c = self.conj(lemme).get("Ind", {}).get("Past", {})
        return c.get("3s") or c.get("-", "")

    def lemmes_verbaux(self, forme: str) -> set[str]:
        return {l.lemme for l in self.lex.lectures(forme) if l.upos in ("VERB", "AUX")}

    def phone_de(self, forme: str, defaut: str = "") -> str:
        for l in self.lex.lectures(forme):
            if l.phone:
                return l.phone
        return defaut


class _Contexte:
    """Une phrase en cours de correction : jetons, corrections faites (par indice de jeton), notes du modèle."""

    def __init__(self, c: Correcteur, texte: str, jetons: list[Jeton], mode: str, langue: str):
        self.c, self.texte, self.j, self.mode, self.langue = c, texte, jetons, mode, langue
        self.faites: dict[int, Correction] = {}
        self.supplement: list[Correction] = []    # collecte : décisions de la tête gardées à côté de celles de KenLM
        self._notes: dict[str, float] = {}
        self.etrangers = {k for k in range(len(jetons)) if self._etranger(k)}

    # ── outils ──────────────────────────────────────────────────────────────

    def resultat(self) -> list[Correction]:
        vus, res = set(), []
        for c in sorted([*self.faites.values(), *self.supplement], key=lambda c: c.debut):
            if id(c) not in vus:
                vus.add(id(c))
                res.append(c)
        return res

    def rendu(self, remplacements: dict[int, str] | None = None, plages: list[tuple[int, int, str]] | None = None) -> str:
        """Phrase avec les corrections faites, plus ``remplacements`` (jeton → texte) et ``plages`` (début, fin,
        texte) ; une correction déjà faite sur un jeton remplacé est ignorée."""
        d0, f0 = self.j[0].debut, self.j[-1].fin
        t = self.texte[d0:f0]
        remplacements = remplacements or {}
        p = {(c.debut, c.fin, c.proposition) for i, c in self.faites.items() if i not in remplacements}
        p |= {(self.j[i].debut, self.j[i].fin, s) for i, s in remplacements.items()}
        p |= set(plages or [])
        for a, b, s in sorted(p, reverse=True):
            t = t[:a - d0] + s + t[b - d0:]
        return t

    def note(self, phrase: str) -> float:
        if phrase not in self._notes:
            self._notes[phrase] = self.c.juge.note(phrase)
        return self._notes[phrase]

    def gain(self, remplacements: dict[int, str] | None = None, plages=None) -> float:
        return self.note(self.rendu(remplacements, plages)) - self.note(self.rendu())

    def forme(self, k: int) -> str:
        """Forme courante du jeton (corrigée si une correction le couvre)."""
        return self.faites[k].proposition if k in self.faites else self.j[k].forme

    def ajouter(self, k: int, proposition: str, type_: str, confiance: float, regle: str, mesures=None,
                explication: str = "", debut: int | None = None, fin: int | None = None, original: str | None = None,
                indices=()) -> Correction:
        t = self.j[k]
        debut = t.debut if debut is None else debut
        fin = t.fin if fin is None else fin
        corr = Correction(debut, fin, self.texte[debut:fin] if original is None else original, proposition, type_,
                          confiance, regle, {"regle": regle, **(mesures or {})}, explication)
        for i in (k, *indices):
            self.faites[i] = corr
        return corr

    def passe(self, regle: str, **mesures) -> bool:
        """La décision passe-t-elle les seuils de sa règle dans ce mode (``SEUILS_MODE``) ?"""
        s = SEUILS_MODE[self.mode].get(regle)
        if s is None:
            return True
        for mesure, valeur in ([s] if isinstance(s, tuple) else s):
            if mesures.get(mesure, 1e9) < valeur:
                return False
        return True

    def expl(self, regle: str, **champs) -> str:
        return gabarit(regle, self.langue, **champs)

    def examinable(self, k: int, majuscule_debut: bool = True) -> bool:
        """Mot écrit en lettres, pas un nom propre (majuscule hors début de phrase), ni un sigle, ni dans un passage
        étranger ; pas déjà corrigé."""
        t = self.j[k]
        if not t.mot or k in self.faites or k in self.etrangers:
            return False
        f = t.forme.replace("’", "'")
        if not f[:1].isalpha() or not all(ch.isalpha() or ch in "'-" for ch in f):
            return False
        if f.isupper() and len(f) > 1:
            return False
        if f[:1].isupper() and (k > 0 or not majuscule_debut) and f.lower() != "i" and not f.lower().startswith("i'"):
            return False
        return True

    def _etranger(self, k: int) -> bool:
        """Mot pris dans un passage en langue étrangère : au moins deux de ses quatre voisins inconnus du lexique."""
        inconnus = 0
        for i in range(max(0, k - 2), min(len(self.j), k + 3)):
            f = self.j[i].forme
            if i == k or not f.isalpha() or f[:1].isupper():
                continue
            if self.c.lex.validite(f.lower()) == "inconnue":
                inconnus += 1
        return inconnus >= 2

    def suivant(self, k: int) -> int | None:
        return k + 1 if k + 1 < len(self.j) else None

    def enfants(self, tete: int, relations: tuple[str, ...]) -> list[int]:
        return [i for i, t in enumerate(self.j) if t.analyse is not None and t.analyse.tete == tete
                and t.analyse.relation.split(":")[0] in relations]

    # ── étapes ──────────────────────────────────────────────────────────────

    def corriger(self) -> None:
        self.regles_sures()
        self.lexicales()
        self.accords()
        self.articles()
        self.possessifs()
        for _ in range(2):                                     # second passage : il voit les corrections du premier
            avant = len(self.faites)
            self.confusions()
            if len(self.faites) == avant:
                break
        if self.c.variete == "US":
            self.varietes()

    def regles_sures(self) -> None:
        m = self.mode
        for k, t in enumerate(self.j):
            f = t.forme.replace("’", "'")
            bas = f.lower()
            if not t.mot or k in self.etrangers:
                continue
            # « i » → « I » (pas dans une énumération « (i) », ni « i.e. »)
            if bas == "i" and f == "i" or (bas.startswith("i'") and f[0] == "i" and bas in ("i'm", "i've", "i'll", "i'd")):
                avant = self.j[k - 1].forme if k else ""
                if self.texte[t.debut - 1:t.debut] == "-" or self.texte[t.fin:t.fin + 1] == "-":
                    continue                                   # O-Ti-Cot-i
                apres = self.j[k + 1].forme if k + 1 < len(self.j) else ""
                if avant not in ("(", "[") and apres not in (")", ".", "]", "="):
                    self.ajouter(k, "I" + f[1:], "majuscule", 1.0, "i_majuscule",
                                 explication=self.expl("i_majuscule", p="I" + f[1:]))
                    continue
            # contractions sans apostrophe
            if bas in APOSTROPHES or bas in APOSTROPHES_AMBIGUES_ACTIVES:
                cible = APOSTROPHES.get(bas) or APOSTROPHES_AMBIGUES[bas]
                cible = cible if cible[0] == "I" else _casse(cible, f)
                if bas in APOSTROPHES_AMBIGUES_ACTIVES:
                    g = self.gain({k: cible})
                    if g < MARGES_APOSTROPHE_AMBIGUE[m]:
                        continue
                else:
                    g = 0.0
                    if bas == "im" and f == "IM":
                        continue
                self.ajouter(k, cible, "apostrophe", 1.0,
                             "apostrophe_ambigue" if bas in APOSTROPHES_AMBIGUES_ACTIVES else "apostrophe",
                             {"gain": round(g, 2)},
                             explication=self.expl("apostrophe", o=f, p=cible))
                continue
            # mot répété
            if k > 0 and self.j[k - 1].mot and self.j[k - 1].forme.lower() == bas and bas.isalpha() and len(bas) > 1 \
                    and bas not in DOUBLES_ADMIS and k - 1 not in self.faites and self.j[k - 1].fin < t.debut \
                    and f[:1].isupper() == self.j[k - 1].forme[:1].isupper() and not f[:1].isupper() \
                    and not (k + 1 < len(self.j) and self.j[k + 1].bas == bas) \
                    and not (k >= 2 and self.j[k - 2].bas == bas):
                # pas « Twinkle Twinkle », « Zsa Zsa » (deux majuscules), ni « compare compare compare »
                d = self.j[k - 1].fin
                self.ajouter(k, "", "doublon", 1.0, "doublon", debut=d, fin=t.fin,
                             explication=self.expl("doublon", o=self.j[k - 1].forme))
                continue
            # could of → could have
            if bas == "of" and k > 0 and self.j[k - 1].forme.lower().replace("’", "'") in MODAUX_OF:
                n = self.suivant(k)
                if n is not None and self.j[n].analyse is not None and (
                        self.j[n].bas == "been" or self.j[n].analyse.feats.get("VerbForm") == "Part"
                        or self.j[n].analyse.upos in ("VERB", "AUX")):
                    cible = _casse("have", f)
                    g = self.gain({k: cible})
                    if g >= MARGES_MODAL_OF[m]:
                        self.ajouter(k, cible, "forme_verbale", 1.0, "modal_of", {"gain": round(g, 2)},
                                     explication=self.expl("modal_of", m=self.j[k - 1].forme.lower()))

    def lexicales(self) -> None:
        """Fautes connues du lexique (usuelle), puis mots inconnus (voisins jugés par le modèle de langue)."""
        lex, m = self.c.lex, self.mode
        for k, t in enumerate(self.j):
            if not self.examinable(k) or "'" in t.forme or "’" in t.forme:
                continue
            f = t.forme
            bas = f.lower()
            v = lex.validite(f)                                  # casse reçue : « Australia » en tête de phrase
            if v == "variante":
                usuelle = lex.usuelle(bas)
                if usuelle and usuelle != bas:
                    cible = _casse(usuelle, f)
                    g = self.gain({k: cible})
                    if g >= MARGES_VARIANTE[m]:
                        self.ajouter(k, cible, "orthographe", 1.0, "variante", {"gain": round(g, 2)},
                                     explication=self.expl("variante", o=f, p=cible))
                continue
            if v != "inconnue" or len(bas) < 2 or f[:1].isupper() or not set(bas) <= ALPHABET:
                continue                                       # nom propre inconnu ; grâce, bjórr : autre langue
            if lex.validite(f.capitalize()) in VALIDES or lex.validite(f.upper()) in VALIDES:
                continue                                       # philadelphia, iphone : nom propre en minuscules
            if self._derive(bas):
                continue
            if "-" in bas and all(lex.validite(x) in VALIDES for x in bas.split("-") if x):
                continue                                       # composé de mots connus (well-groomed)
            cands = self.candidats(f, t.phone)
            if not cands:
                continue
            notes = []
            for forme, origine, dist in cands:
                cible = forme if origine == "scission" else _casse(forme, f)
                notes.append((self.note(self.rendu({k: cible})) - COUT.get((origine, dist), 3.0), cible, origine, dist))
            notes.sort(reverse=True)
            meilleur = notes[0]
            second = next((n for n in notes[1:] if not self._meme_lemme(n[1], meilleur[1])), None)
            # candidat seul : marge fixe selon la distance (une faute de frappe d'une lettre est plus sûre)
            marge = meilleur[0] - (second[0] if second else meilleur[0] - SEUL.get((meilleur[2], meilleur[3]), 2.0))
            gain = meilleur[0] - self.note(self.rendu())
            regle = "scission" if meilleur[2] == "scission" else "hors_lexique"
            if not self.passe(regle, marge=marge, gain=gain):
                continue
            cible = meilleur[1]
            self.ajouter(k, cible, "orthographe", marge, regle,
                         {"marge": round(marge, 2), "gain": round(gain, 2), "origine": meilleur[2], "distance": meilleur[3],
                          "candidats": "; ".join(f"{n[1]} {n[0]:.1f}" for n in notes[:3])},
                         explication=self.expl(regle, o=f, p=cible))

    def _derive(self, bas: str) -> bool:
        """Dérivé ou flexion régulière d'un mot connu, absent du lexique (lukewarmly, emails, googled)."""
        lex = self.c.lex
        bases = []
        for suf, rempl in (("s", ""), ("es", ""), ("ly", ""), ("ily", "y"), ("ness", ""), ("less", ""), ("ful", ""),
                           ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"), ("er", ""), ("ers", "")):
            if bas.endswith(suf) and len(bas) - len(suf) >= 3:
                bases.append(bas[:-len(suf)] + rempl)
        for pre in ("un", "re", "non", "pre", "over", "under", "mis", "out", "co"):
            if bas.startswith(pre) and len(bas) - len(pre) >= 4:
                bases.append(bas[len(pre):])
        return any(lex.validite(b) in VALIDES for b in bases)

    def _meme_lemme(self, a: str, b: str) -> bool:
        la = {l.lemme for l in self.c.lex.lectures(a)}
        return bool(la & {l.lemme for l in self.c.lex.lectures(b)})

    def _outil(self, forme: str) -> bool:
        """Mot grammatical (ground state, show courts : deux noms collés, composé légitime)."""
        return any(l.upos in OUTILS_UPOS for l in self.c.lex.lectures(forme))

    def candidats(self, forme: str, phone: str) -> list[tuple[str, str, int]]:
        bas = forme.lower()
        lex = self.c.lex
        vus: dict[str, tuple[str, str, int]] = {}
        dmax = 2 if len(bas) >= 6 else 1                       # lhasa ≠ last : distance 2 sur un mot long seulement
        for v in lex.voisins_orthographiques(bas, distance_max=dmax, limite=20, validite_min="proposable"):
            if not v.propre and v.ortho.islower() and v.ortho != bas and v.ortho not in vus \
                    and v.ortho.rstrip("s") != bas.rstrip("s"):   # osteocyte ≠ osteocytes : nombre, pas faute
                vus[v.ortho] = (v.ortho, "ortho", v.distance)    # mot courant en minuscules : pas Isuzu, AND, Dec.
        if phone:
            for v in lex.voisins_phonetiques(phone, tolerance=1, limite=20):
                if not v.propre and v.ortho.islower() and v.validite == "proposable" and v.ortho not in vus \
                        and v.ortho != bas and v.ortho.isalpha():
                    vus[v.ortho] = (v.ortho, "phone", v.distance)
        if bas.isalpha() and len(bas) >= 4:                   # mots collés (inthe, alot déjà connu)
            for i in range(1, len(bas) - 1):
                a, b = bas[:i], bas[i:]
                if (len(a) >= 2 or a in ("a", "i")) and len(b) >= 2 and lex.validite(a) == "proposable" \
                        and lex.validite(b) == "proposable" and min(lex.frequence(a), lex.frequence(b)) >= 3.0 \
                        and max(lex.frequence(a), lex.frequence(b)) >= 5.5 and (self._outil(a) or self._outil(b)):
                    s = f"{'I' if a == 'i' else forme[:i]} {forme[i:]}"     # casse reçue : theSuper → the Super
                    vus.setdefault(s, (s, "scission", 1))
        return list(vus.values())[:30]

    # ── accords et formes verbales ─────────────────────────────────────────

    def _personne(self, s: int) -> str | None:
        """Personne grammaticale du sujet : 1s, 2, 3s, p ; None si incertaine."""
        t = self.j[s]
        a = t.analyse
        bas = self.forme(s).lower()
        if bas in ("that", "which", "who", "whom", "what"):
            return None                                        # relatif : l'accord suit l'antécédent
        if t.forme[:1].isupper() and s > 0 and bas != "i":
            return None                                        # « Only You », « Laser Prototypes » : titre, nom
        if bas in PRONOMS_SUJETS:
            return PRONOMS_SUJETS[bas]
        if a is None or a.upos != "NOUN" or bas in COLLECTIFS:
            return None                                        # nom propre : équipe, pays, société (accord libre)
        # sujet coordonné (« John and Mary ») : pluriel
        for c in self.enfants(s, ("conj",)):
            if any(self.j[x].bas == "and" for x in self.enfants(c, ("cc",))):
                return "p"
        if any(self.j[x].bas in ("of",) for x in range(s + 1, min(len(self.j), s + 2))):
            return None                                        # « one of the », « the rest of » : prudence
        nombre = a.feats.get("Number")
        lectures = [l for l in self.c.lex.lectures(bas) if l.upos in ("NOUN", "PROPN")]
        nombres = {l.traits().get("Number") for l in lectures}
        if lectures and len(nombres) > 1:
            return None                                        # sheep, series : nombre invisible
        if nombre == "Sing" and t.forme[:1].islower() or nombre == "Sing" and a.upos == "PROPN" and not bas.endswith("s"):
            return "3s"
        if nombre == "Plur" and a.upos == "NOUN":
            return "p"
        return None

    def accords(self) -> None:
        self._accord_sujet()
        self._formes_verbales()
        self._determinants()

    def _chaine_verbale(self, tete: int) -> list[int]:
        """Le verbe ``tete`` et ses auxiliaires (aux, cop), dans l'ordre du texte."""
        return sorted([tete] + self.enfants(tete, ("aux", "cop")))

    def _accord_sujet(self) -> None:
        c, m = self.c, self.mode
        for k, t in enumerate(self.j):
            a = t.analyse
            if a is None or a.upos not in ("VERB", "AUX") or not self.examinable(k) or k in self.faites:
                continue
            hote = t.hote.mot.forme.lower().replace("’", "'")
            if hote in MODAUX or "'" in hote:
                continue
            lemmes = c.lemmes_verbaux(hote)
            lemme = a.lemme if a.lemme in lemmes else (next(iter(lemmes)) if len(lemmes) == 1 else None)
            if not lemme:
                continue
            tete = a.tete if a.relation.split(":")[0] in ("aux", "cop") and a.tete is not None and a.tete >= 0 else k
            chaine = self._chaine_verbale(tete)
            if chaine[0] != k:
                continue                                       # pas le premier élément verbal : pas fini
            sujets = self.enfants(tete, ("nsubj",))
            if len(sujets) != 1 or sujets[0] > k or k - sujets[0] > 6:
                continue                                       # sujet absent, inversé (question) ou lointain
            s = sujets[0]
            if any(self.j[x].bas in ("and", "or", "nor", "&", "with", "plus") for x in range(max(0, s - 6), k)) \
                    or any(self.j[x].analyse is not None and self.j[x].analyse.tete == s
                           and self.j[x].analyse.relation.split(":")[0] == "det"
                           and self.j[x].bas in DET_SINGULIER | DET_PLURIEL for x in range(max(0, s - 3), s)) \
                    and self.j[s].analyse.upos == "NOUN" and self._conflit_det(s):
                continue                                       # sujet coordonné ou accompagné : accord incertain
            parent = self.j[tete].analyse.tete if self.j[tete].analyse else None
            if parent is not None and 0 <= parent < len(self.j) and self.j[parent].analyse is not None \
                    and self.j[parent].analyse.lemme in SUBJONCTIF:
                continue                                       # « suggest that she get » : subjonctif
            personne = self._personne(s)
            if personne is None or (self.j[s].analyse and self.j[s].analyse.feats.get("PronType") == "Rel"):
                continue
            attendu = self._forme_attendue(lemme, hote, personne)
            if not attendu or attendu == hote:
                continue
            # forme de l'hôte seule (does dans doesn't) : on remplace l'hôte
            h = t.hote
            cible = _casse(attendu, h.mot.forme)
            g = self.gain(plages=[(h.mot.debut, h.mot.fin, cible)])
            if not self.passe("accord_sujet", gain=g):
                continue
            temps = self.expl("accord_3s") if personne == "3s" and lemme not in ("be", "have") else ""
            self.ajouter(k, cible, "accord", 1.0, "accord_sujet", {"gain": round(g, 2), "sujet": self.forme(s)},
                         debut=h.mot.debut, fin=h.mot.fin,
                         explication=self.expl("accord_sujet", s=self.forme(s), pers=PERSONNES[self.langue if self.langue in PERSONNES else "fr"][personne],
                                               p=cible, temps=temps))

    def _conflit_det(self, s: int) -> bool:
        """« An examples is » : le déterminant contredit le nombre du nom, c'est le nom qu'il faut corriger."""
        n = self.j[s].analyse.feats.get("Number")
        for x in range(max(0, s - 3), s):
            b = self.j[x].bas
            if (b in DET_SINGULIER and n == "Plur") or (b in DET_PLURIEL and n == "Sing"):
                return True
        return False

    def _forme_attendue(self, lemme: str, recue: str, personne: str) -> str:
        if lemme == "be":
            if recue in ("am", "are", "is"):
                return {"1s": "am", "3s": "is"}.get(personne, "are")
            if recue in ("was", "were"):
                if recue == "were" and personne in ("1s", "3s"):
                    return ""                                  # subjonctif (if I were) : admis
                return "was" if personne in ("1s", "3s") else "were"
            return ""
        base, trois = self.c.base(lemme), self.c.troisieme(lemme)
        if not base or not trois or recue not in (base, trois):
            return ""                                          # passé, participe : pas d'accord en anglais
        if recue == base and self.c.preterit(lemme) == base:
            return ""                                          # « It set », « he put » : prétérit identique
        return trois if personne == "3s" else base

    def _formes_verbales(self) -> None:
        """Après un modal, do, to : base verbale ; après have : participe passé ; passif be + prétérit → participe."""
        c, m = self.c, self.mode
        for k, t in enumerate(self.j):
            a = t.analyse
            if a is None or a.upos != "VERB" or not self.examinable(k) or "'" in t.forme:
                continue
            bas = t.bas
            lemmes = c.lemmes_verbaux(bas)
            lemme = a.lemme if a.lemme in lemmes else (next(iter(lemmes)) if len(lemmes) == 1 else None)
            if not lemme:
                continue
            auxs = [x for x in self.enfants(k, ("aux",)) if x < k]
            marques = [x for x in self.enfants(k, ("mark",)) if x < k and self.j[x].bas == "to"]
            regle, cible, aux = "", "", None
            if auxs:
                aux = max(auxs)
                ha = self.j[aux].hote.mot.forme.lower().replace("’", "'")
                lemme_aux = self.j[aux].analyse.lemme if self.j[aux].analyse else ""
                if k - aux > 3:
                    continue
                base = c.base(lemme)
                if ha in MODAUX:
                    regle, cible = "base_modal", base
                elif lemme_aux == "do" or ha in ("do", "does", "did"):
                    regle, cible = "base_do", base
                elif lemme_aux == "have" or ha in ("have", "has", "had", "'ve", "'d"):
                    part, pret = c.participe(lemme), c.preterit(lemme)
                    if part and pret and part != pret and bas == pret:
                        regle, cible = "participe_have", part
                elif (lemme_aux == "be" or ha in ("is", "are", "was", "were", "be", "been", "being", "am")) \
                        and a.relation.endswith("pass"):
                    part, pret = c.participe(lemme), c.preterit(lemme)
                    if part and pret and part != pret and bas == pret:
                        regle, cible = "participe_be", part
                if regle in ("base_modal", "base_do"):
                    formes = {l.feats for l in c.lex.lectures(bas) if l.lemme == lemme}
                    if not base or bas == base or any("VerbForm=Inf" in f for f in formes) \
                            or any("VerbForm=Ger" in f or "VerbForm=Part" in f for f in formes) \
                            and not any("VerbForm=Fin" in f for f in formes):
                        continue                               # « did going », « can been » : autre problème
            elif marques and k - max(marques) <= 2:
                formes = {l.feats for l in c.lex.lectures(bas) if l.lemme == lemme}
                base = c.base(lemme)
                if base and bas != base and not any("VerbForm=Inf" in f or "VerbForm=Ger" in f or "Part" in f
                                                    for f in formes) and any("VerbForm=Fin" in f for f in formes):
                    regle, cible, aux = "base_to", base, max(marques)
            if not regle or not cible or cible == bas:
                continue
            cible = _casse(cible, t.forme)
            g = self.gain({k: cible})
            if not self.passe(regle, gain=g):
                continue
            self.ajouter(k, cible, "forme_verbale", 1.0, regle, {"gain": round(g, 2)},
                         explication=self.expl(regle, a=self.forme(aux) if aux is not None else "", p=cible, o=t.forme))

    def _determinants(self) -> None:
        c, m = self.c, self.mode
        for d, td in enumerate(self.j):
            a = td.analyse
            if a is None or a.relation.split(":")[0] not in ("det", "nummod") or a.tete is None or a.tete <= d:
                continue
            bas = td.bas
            sing, plur = bas in DET_SINGULIER, bas in DET_PLURIEL
            if not (sing or plur) or d in self.faites:
                continue
            n = a.tete
            tn = self.j[n]
            if tn.analyse is None or tn.analyse.upos != "NOUN" or not self.examinable(n) or n - d > 3:
                continue
            if tn.analyse.relation.split(":")[0] in ("compound", "amod", "nmod") or (
                    n + 1 < len(self.j) and self.j[n + 1].analyse is not None
                    and self.j[n + 1].analyse.upos in ("NOUN", "PROPN") and self.j[n + 1].mot):
                continue                                       # « five hour chase », « eight circuit model »
            if bas == "each" and n + 1 < len(self.j) and self.j[n].bas.startswith("other"):
                continue
            if any(self.j[x].bas in QUANTIFIEURS or (self.j[x].analyse and self.j[x].analyse.upos == "NUM")
                   for x in range(d + 1, n)):
                continue                                       # « every few days », « a lot of », « those two men »
            if d + 1 < len(self.j) and self.j[d + 1].bas in QUANTIFIEURS:
                continue
            lectures = [l for l in c.lex.lectures(tn.bas) if l.upos == "NOUN"]
            if any(l.lemme == tn.analyse.lemme for l in lectures):
                lectures = [l for l in lectures if l.lemme == tn.analyse.lemme]   # days : lemme day, pas « days »
            nombres = {l.traits().get("Number") for l in lectures}
            if not lectures or len(nombres) != 1:
                continue                                       # sheep, data, inconnu : on ne juge pas
            nombre = nombres.pop()
            if (sing and nombre != "Plur") or (plur and nombre != "Sing"):
                continue
            # candidats : l'autre nombre du nom, ou le démonstratif de l'autre nombre
            cible_nom = ""
            for _l, x in c.lex.variante(tn.bas, Number="Sing" if sing else "Plur"):
                if x.upos == "NOUN" and c.lex.validite(x.ortho) == "proposable":
                    cible_nom = x.ortho
                    break
            options = []
            if cible_nom:
                options.append(("nom", n, _casse(cible_nom, tn.forme)))
            if bas in DEMONSTRATIFS:
                options.append(("det", d, _casse(DEMONSTRATIFS[bas], td.forme)))
            if not options:
                continue
            notes = sorted(((self.gain({i: s}), quoi, i, s) for quoi, i, s in options), reverse=True)
            g, quoi, i, s = notes[0]
            regle = ("determinant_sing" if sing else "determinant_plur") if quoi == "nom" else "determinant_demonstratif"
            if not self.passe(regle, gain=g):
                continue
            if quoi == "nom":
                regle = "determinant_sing" if sing else "determinant_plur"
                expl = self.expl(regle, d=td.forme, p=f"{td.forme} {s}")
            else:
                regle = "determinant_demonstratif"
                nb = {"fr": ("au singulier", "au pluriel"), "en": ("singular", "plural")}[self.langue if self.langue == "en" else "fr"]
                expl = self.expl(regle, nombre=nb[0] if nombre == "Sing" else nb[1], p=s)
            self.ajouter(i, s, "accord", 1.0, regle, {"gain": round(g, 2)}, explication=expl)

    # ── a / an ──────────────────────────────────────────────────────────────

    def articles(self) -> None:
        from lectura_lexicon.en.cles import cle_phone, phonemes

        for k, t in enumerate(self.j):
            bas = t.bas
            if bas not in ("a", "an") or k in self.faites or not t.mot or (t.forme[:1].isupper() and k > 0):
                continue
            if t.analyse is None or t.analyse.upos != "DET":
                continue
            n = self.suivant(k)
            if n is None or not (self.j[n].mot or self.j[n].origine in ("formule", "lexique", "modele")):
                continue
            tn = self.j[n]
            if not tn.forme[:1].isalnum() or tn.bas in ("a", "an", "the"):
                continue                                       # « a a bird » : doublon, pas « a an »
            forme_n = self.forme(n)
            phone = self.c.phone_de(forme_n.lower(), "") if n in self.faites else tn.phone
            if not phone:
                continue
            ph = phonemes(cle_phone(phone))
            if not ph:
                continue
            attendu = "an" if ph[0] in VOYELLES else "a"
            if self.mode == "automatique" and tn.origine == "modele":
                # prononciation du modèle de mot (mot hors lexique) : seulement si la première lettre dit la même
                # chose ; u, o, h, e, y (unicorn, one, hour, euro, yttrium) et les sigles restent douteux
                lettre = forme_n[:1].lower()
                if lettre in "uohey" or (forme_n.isupper() and len(forme_n) > 1) \
                        or attendu != ("an" if lettre in "aeiou" else "a"):
                    continue
            if attendu == bas:
                continue
            if bas == "an" and ph[0] == "h" and not phone.startswith("ˈ"):
                continue                                       # « an historic », « an hotel » : usage admis
            cible = _casse(attendu, t.forme)
            regle = "article_an" if attendu == "an" else "article_a"
            self.ajouter(k, cible, "article", 1.0, regle, {"phone": phone},
                         explication=self.expl(regle, n=forme_n, s=phone.replace("ˈ", "").replace("ˌ", "")))

    # ── possessifs sans apostrophe ─────────────────────────────────────────

    def possessifs(self) -> None:
        """Possessif écrit sans apostrophe : nom au pluriel en -s (ou pluriel irrégulier + s) collé à un groupe nominal
        qui suit (« his fathers sleepy eyes », « the members homes », « childrens museum ») ; candidats « father's »
        (singulier) et « fathers' » (pluriel), jugés par le modèle de langue (il garde ces formes entières)."""
        c = self.c
        for k, t in enumerate(self.j):
            bas = t.bas
            if len(bas) < 4 or not bas.endswith("s") or bas.endswith("ss") or "'" in bas or not self.examinable(k):
                continue
            if t.analyse is None or t.analyse.upos != "NOUN":
                continue
            n = self.suivant(k)
            if n is None or not self.j[n].mot or n in self.faites or self.j[n].analyse is None \
                    or self.texte[t.fin:self.j[n].debut].strip():
                continue
            an = self.j[n].analyse
            if not (an.upos in ("NOUN", "ADJ", "NUM") or an.upos == "VERB" and an.feats.get("VerbForm") == "Ger") \
                    or self.j[n].bas in OUTILS:
                continue
            options: dict[str, str] = {}
            for l in c.lex.lectures(bas):
                if l.upos == "NOUN" and "Number=Plur" in l.feats and l.lemme != bas and l.lemme.isalpha():
                    options[l.lemme + "'s"] = "possessif_sing"
                    options[bas + "'"] = "possessif_plur"
            if any(l.upos == "NOUN" and "Number=Plur" in l.feats for l in c.lex.lectures(bas[:-1])):
                options[bas[:-1] + "'s"] = "possessif_plur"           # childrens → children's
            if not options:
                continue
            notes = sorted(((self.gain({k: _casse(x, t.forme)}), x, r) for x, r in options.items()), reverse=True)
            g, x, regle = notes[0]
            marge = g - notes[1][0] if len(notes) > 1 else 9.0
            avant = self.j[k - 1].bas if k else ""
            mesures = {"gain": round(g, 2), "marge": round(marge, 2), "det": int(avant in POSSESSEURS)}
            if not self.passe(regle, **mesures):
                continue
            cible = _casse(x, t.forme)
            self.ajouter(k, cible, "apostrophe", g, regle, mesures,
                         explication=self.expl(regle, o=t.forme, p=cible))
        self.possessifs_propres()

    def possessifs_propres(self) -> None:
        """Possessif d'un nom propre sans apostrophe (« Camerons Father », « Eisenhowers huge army », « Japans
        largest ») : mot capitalisé en -s collé à un mot plein qui suit ; « X's » jugé par le modèle de langue, qui
        connaît les possessifs des noms courants (« cameron's ») et garde les noms en -s (Williams, Jones)."""
        for k, t in enumerate(self.j):
            f = t.forme
            if not t.mot or k in self.faites or k in self.etrangers or len(f) < 4 or not f[0].isupper() \
                    or not f[1:].isalpha() or not f[1:].islower() or not f.endswith("s") \
                    or f[-2] in "su'" or t.bas in NON_POSSESSIFS:
                continue
            n = self.suivant(k)
            if n is None or not self.j[n].mot or n in self.faites or self.texte[t.fin:self.j[n].debut] != " " \
                    or not self.j[n].forme.isalpha() or self.j[n].bas in OUTILS:
                continue
            an = self.j[n].analyse
            if an is not None and (an.upos in OUTILS_UPOS or an.upos == "VERB" and an.feats.get("VerbForm") != "Ger"):
                continue
            cible = f[:-1] + "'s"
            g = self.gain({k: cible})
            mesures = {"gain": round(g, 2), "debut": int(k == 0)}
            if not self.passe("possessif_propre", **mesures):
                continue
            self.ajouter(k, cible, "apostrophe", g, "possessif_propre", mesures,
                         explication=self.expl("possessif_sing", o=f, p=cible))

    # ── confusions et homophones ───────────────────────────────────────────

    def confusions(self) -> None:
        from lectura_lexicon.en.cles import cle_phone

        c, m = self.c, self.mode
        for k, t in enumerate(self.j):
            if not self.examinable(k) or self._tete(k, t):
                continue
            bas = t.bas
            options: dict[str, str] = {}
            for x in _INDEX_CONFUSIONS.get(bas, ()):
                if " " not in x:
                    options[x] = "confusion"
            if bas not in OUTILS and t.phone and t.origine == "lexique" and "'" not in bas:
                for h in c.lex.homophones(t.phone):
                    o = h.ortho
                    if (o.lower() != bas and o.lower() not in options and not h.propre and not h.special
                            and o.isalpha() and o.islower() and h.validite == "proposable" and h.zipf >= ZIPF_HOMOPHONE
                            and o not in OUTILS and not self._meme_lemme(o, bas)
                            and c.lex.americaine(bas) != o and c.lex.americaine(o) != bas and not c.lex.britannique(bas)
                            and not {l.upos for l in c.lex.lectures(o)} <= {"INTJ", "NUM", "X", "SYM"}):
                        options[o.lower()] = "homophone"
            if not options:
                continue
            notes = sorted(((self.gain({k: _casse(x, t.forme)}), x, nature) for x, nature in options.items()),
                           reverse=True)
            g, x, nature = notes[0]
            marge = (MARGES_CONFUSION if nature == "confusion" else MARGES_HOMOPHONE)[m]
            if g < marge:
                continue
            cible = _casse(x, t.forme)
            expl = self.expl(nature, o=t.forme, p=cible)
            ast = astuce(bas, x, self.langue)
            if ast:
                expl += " " + ast
            self.ajouter(k, cible, nature, g, nature, {"gain": round(g, 2)}, explication=expl)

    def _tete(self, k: int, t) -> bool:
        """Homophone jugé par la tête de graphie : le mot redonné par sa seule prononciation, quelle graphie le
        contexte écrit attend-il ? Second juge : KenLM (``gain``). Rend vrai si une correction est faite."""
        c = self.c
        if c.tete is None:
            return False
        recue = t.bas                              # filtres d'abord : un passage du graphe coûte ~10 ms
        cands = c.tete.candidats(phone_jeton(t))
        if recue not in cands or len(cands) < 2 or c.lex.validite(recue) != "proposable":
            return False
        u_recue = {l.upos for l in c.lex.lectures(recue)}
        if "SYM" in u_recue or u_recue <= {"PROPN", "INTJ", "X"}:      # lettres (u, b, y), interjections, noms propres
            return False
        if t.forme[:1].isupper() and recue != "i" and c.lex.frequence(recue) < 4.0:   # Rea, Syed en tête de phrase
            return False
        options = [g for g in cands if g != recue and len(g) > 1 and c.lex.validite(g) == "proposable"
                   and not c.lex.britannique(g) and not variantes_gb_us(recue, g)
                   and c.lex.americaine(recue) != g and c.lex.americaine(g) != recue
                   and not {l.upos for l in c.lex.lectures(g)} <= {"PROPN", "INTJ", "NUM", "X", "SYM"}]
        if not options:
            return False
        p = c.tete.probas(self.j, k, formes={i: x.proposition for i, x in self.faites.items()})
        if recue not in p:
            return False
        pr = p[recue]
        b = max(options, key=p.get)
        if p[b] <= pr:
            return False
        cible = _casse(b, t.forme)
        g = self.gain({k: cible})
        mes = {"ecart": round(p[b] - pr, 4), "non_recue": round(1 - pr, 5), "gain": round(g, 2),
               "p_meilleure": round(p[b], 4), "p_recue": round(pr, 5)}
        if not self.passe("homophone_tete", **mes):
            return False
        expl = self.expl("homophone", o=t.forme, p=cible)
        ast = astuce(recue, b, self.langue)
        if ast:
            expl += " " + ast
        if self.mode == "collecte":                # KenLM juge aussi ce mot : le réglage hors ligne choisit
            if not any(x.debut == t.debut and x.proposition == cible for x in self.supplement):
                self.supplement.append(Correction(t.debut, t.fin, t.forme, cible, "homophone", p[b], "homophone_tete",
                                                  {"regle": "homophone_tete", **mes}, expl))
            return False
        self.ajouter(k, cible, "homophone", p[b], "homophone_tete", mes, explication=expl)
        return True

    def varietes(self) -> None:
        for k, t in enumerate(self.j):
            if not self.examinable(k):
                continue
            us = self.c.lex.americaine(t.bas)
            if us:
                cible = _casse(us, t.forme)
                self.ajouter(k, cible, "variete", 1.0, "variete", explication=self.expl("variete", p=cible))
