# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Nettoyage phonétique d'un texte avant la chaîne : les fautes qui changent la prononciation.

Un mot inconnu du lexique est confronté à des candidats proches : accents, lettre doublée,
une frappe de différence (clavier compris), mot collé, élision sans apostrophe, abréviation
SMS. Le candidat est retenu s'il est fréquent et clairement meilleur que les autres ; un
candidat qui se prononce comme le mot fautif (prononciation donnée par le modèle de mot)
est fortement favorisé. Dans le doute, le mot reste tel quel : c'est le modèle de mot qui
le prononcera. Les gardes viennent de l'ancien vérificateur de ``lectura_correcteur`` :
noms propres, sigles, contexte étranger, seuils de fréquence selon la longueur du mot.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import cache
from importlib import resources

from lectura_nlp_fr.analyseur.alignement import decomposer
from lectura_nlp_fr.analyseur.analyse import Lexique, ModeleDeMot
from lectura_nlp_fr.analyseur.decoupage import TABLES_ORTHO
from lectura_nlp_fr.analyseur.index_phone import cle_de
from lectura_nlp_fr.analyseur.structures import Document, Mot, Phrase, TypeMot
from lectura_nlp_fr.analyseur.tokeniseur import tokeniser

ALPHABET = "abcdefghijklmnopqrstuvwxyzàâéèêëîïôùûüçœ"
_ACCENTS = {
    "a": "àâ", "e": "éèê", "i": "î", "o": "ô", "u": "ùû", "c": "ç",
    "à": "aâ", "â": "aà", "é": "eèê", "è": "eéê", "ê": "eéè", "î": "i", "ô": "o", "ù": "uû", "û": "uù", "ç": "c",
}
_VOYELLES = frozenset("aeiouyàâéèêëîïôùûüh")
_CLAVIER = ("azertyuiop", "qsdfghjklm", "wxcvbn")
# Bonus de score par nature de candidat, en points de fréquence (zipf).
_BONUS = {"accent": 1.5, "consonne": 1.0, "frappe": 0.0, "clavier": 0.5, "transposition": 0.5, "colle": 0.5, "elision": 1.0, "sms": 2.0}
_BONUS_PRONONCIATION = 2.0
# Fréquence minimale du candidat selon la longueur du mot fautif ; écart minimal avec le second.
_SEUIL = {1: 9.0, 2: 9.0, 3: 5.0, 4: 4.5}
_SEUIL_LONG = 3.0
# Un mot collé ne se coupe qu'en deux mots courants.
_SEUIL_COLLE = 4.5
_ECART = 0.3
# Plus de deux mots inconnus dans la fenêtre : texte étranger ou spécialisé, on ne touche à rien.
_FENETRE, _MAX_INCONNUS = 2, 1


@dataclass(frozen=True)
class Candidat:
    texte: str
    motif: str
    score: float


@dataclass(frozen=True)
class Correction:
    debut: int
    fin: int
    original: str
    remplacement: str
    motif: str
    score: float


@cache
def _sms() -> dict[str, str]:
    texte = resources.files("lectura_nlp_fr.analyseur.data").joinpath("sms.tsv").read_text(encoding="utf-8")
    return dict(l.split("\t") for l in texte.splitlines() if l and not l.startswith("#"))


@cache
def _voisins_clavier() -> dict[str, set[str]]:
    voisins: dict[str, set[str]] = {}
    for r, rangee in enumerate(_CLAVIER):
        for c, lettre in enumerate(rangee):
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if 0 <= r + dr < len(_CLAVIER) and 0 <= c + dc < len(_CLAVIER[r + dr]) and (dr or dc):
                        voisins.setdefault(lettre, set()).add(_CLAVIER[r + dr][c + dc])
    return voisins


class Nettoyeur:
    def __init__(self, lexique: Lexique, modele: ModeleDeMot | None = None):
        self.lexique = lexique
        self.modele = modele

    # ── Lexique ────────────────────────────────────────────────────────────────

    def _frequence(self, mot: str) -> float | None:
        """Fréquence (zipf) la plus haute des lectures d'un mot, ``None`` s'il est inconnu."""
        lectures = self.lexique.lectures(mot)
        return max(e.frequence for e in lectures) if lectures else None

    def _connu(self, mot: str) -> bool:
        return self._frequence(mot) is not None

    def _prononciations(self, mot: str) -> set[str]:
        return {cle_de(decomposer(e.phone_enrichi)[1]) for e in self.lexique.lectures(mot) if e.phone_enrichi}

    # ── Candidats ──────────────────────────────────────────────────────────────

    def candidats(self, mot: str) -> list[Candidat]:
        bruts: dict[str, Candidat] = {}

        def proposer(texte: str, motif: str, bonus: float = 0.0) -> None:
            if texte == mot or texte in bruts:
                return
            parts = texte.replace("'", "' ").split()
            frequences = [self._frequence(p) for p in parts]
            if any(f is None for f in frequences) or (motif == "colle" and min(frequences) < _SEUIL_COLLE):
                return
            score = min(frequences) + _BONUS[motif] + bonus
            bruts[texte] = Candidat(texte, motif, score)

        if mot in _sms():
            proposer(_sms()[mot], "sms")
        for texte in _variantes_accents(mot):
            proposer(texte, "accent")
        for texte in _variantes_consonne(mot):
            proposer(texte, "consonne")
            for texte2 in _variantes_consonne(texte):
                proposer(texte2, "consonne", -0.5)       # « apellé » → appelé : une lettre doublée, une dédoublée
        for texte, nature in _distance_un(mot):
            proposer(texte, nature)
        for texte in _elisions(mot):
            proposer(texte, "elision")
        for texte in _coupures(mot):
            proposer(texte, "colle")
        candidats = list(bruts.values())
        if self.modele and candidats:
            candidats = self._avec_prononciation(mot, candidats)
        return sorted(candidats, key=lambda c: -c.score)

    def _avec_prononciation(self, mot: str, candidats: list[Candidat]) -> list[Candidat]:
        """Un candidat qui se prononce comme le mot fautif gagne un bonus."""
        couples = self.modele.aligner(mot, None)
        if not couples:
            return candidats
        dite = cle_de(decomposer("".join(c.phone for c in couples))[1])
        return [
            replace(c, score=c.score + _BONUS_PRONONCIATION) if "'" not in c.texte and " " not in c.texte and dite in self._prononciations(c.texte) else c
            for c in candidats
        ]

    # ── Décision ───────────────────────────────────────────────────────────────

    def corriger_mot(self, mot: str) -> Candidat | None:
        candidats = self.candidats(mot)
        if not candidats:
            return None
        meilleur = candidats[0]
        seuil = _SEUIL.get(len(mot), _SEUIL_LONG)
        if meilleur.score < seuil:
            return None
        if len(mot) <= 3 and meilleur.motif not in ("accent", "sms"):
            return None       # un mot très court ne se corrige que par ses accents
        if len(candidats) > 1 and meilleur.score - candidats[1].score < _ECART - 1e-9:
            return None
        return meilleur

    def nettoyer(self, document: Document) -> tuple[Document, list[Correction]]:
        corrections: list[Correction] = []
        phrases = []
        for phrase in document.phrases:
            mots = phrase.mots
            suspects = [self._suspect(m) for m in mots]
            nouveaux: list[Mot] = []
            for i, mot in enumerate(mots):
                if not suspects[i] or self._contexte_etranger(suspects, i):
                    nouveaux.append(mot)
                    continue
                choix = self.corriger_mot(mot.forme.lower())
                if choix is None:
                    nouveaux.append(mot)
                    continue
                remplacement = choix.texte if mot.forme.islower() else choix.texte[0].upper() + choix.texte[1:]
                corrections.append(Correction(mot.debut, mot.fin, document.texte[mot.debut : mot.fin], remplacement, choix.motif, choix.score))
                nouveaux.extend(_mots_de(remplacement, mot))
            phrases.append(Phrase(nouveaux))
        return Document(document.texte, document.canal, phrases, document.niveau_phone), corrections

    def _suspect(self, mot: Mot) -> bool:
        forme = mot.forme
        if mot.type is not TypeMot.MOT or mot.nature or len(forme) < 2 or not forme.replace("'", "").replace("-", "").isalpha():
            return False
        if forme.isupper() or (forme[:1].isupper() and forme[1:].islower() and not self._connu(forme.lower()) and mot.debut > 0):
            return False       # sigle, ou majuscule hors début de phrase : nom propre
        if self._connu(forme) or (forme[:1].isupper() and self._connu(forme.lower())):
            return False
        # Connu avec une majuscule (« honda », « france ») : un nom propre mal typé, pas une faute.
        return not self._connu(forme[:1].upper() + forme[1:])

    @staticmethod
    def _contexte_etranger(suspects: list[bool], i: int) -> bool:
        voisins = suspects[max(0, i - _FENETRE) : i] + suspects[i + 1 : i + 1 + _FENETRE]
        return sum(voisins) > _MAX_INCONNUS


# ── Générateurs ────────────────────────────────────────────────────────────────


def _variantes_accents(mot: str) -> list[str]:
    positions = [i for i, c in enumerate(mot) if c in _ACCENTS]
    if not positions:
        return []
    resultat = []
    if len(positions) <= 4:
        import itertools

        options = [(mot[p],) + tuple(_ACCENTS[mot[p]]) for p in positions]
        for combo in itertools.product(*options):
            lettres = list(mot)
            for p, c in zip(positions, combo):
                lettres[p] = c
            resultat.append("".join(lettres))
    else:
        for p in positions:
            for c in _ACCENTS[mot[p]]:
                resultat.append(mot[:p] + c + mot[p + 1 :])
    return [r for r in resultat if r != mot]


def _variantes_consonne(mot: str) -> list[str]:
    resultat = []
    for i, c in enumerate(mot):
        if c in _VOYELLES or not c.isalpha():
            continue
        if i + 1 < len(mot) and mot[i + 1] == c:
            resultat.append(mot[:i] + mot[i + 1 :])      # « addresse » → adresse
        elif i == 0 or mot[i - 1] != c:
            resultat.append(mot[: i + 1] + c + mot[i + 1 :])   # « apeler » → appeler
    return resultat


def _distance_un(mot: str) -> list[tuple[str, str]]:
    """Mots à une opération de distance, avec la nature de l'opération : « frappe » (suppression,
    insertion, substitution), « clavier » (substitution par une touche voisine), « transposition »."""
    voisins = _voisins_clavier()
    resultat = []
    for i in range(len(mot)):
        resultat.append((mot[:i] + mot[i + 1 :], "frappe"))
        if i + 1 < len(mot):
            resultat.append((mot[:i] + mot[i + 1] + mot[i] + mot[i + 2 :], "transposition"))
    for i in range(len(mot) + 1):
        for c in ALPHABET:
            resultat.append((mot[:i] + c + mot[i:], "frappe"))
            if i < len(mot) and c != mot[i]:
                resultat.append((mot[:i] + c + mot[i + 1 :], "clavier" if c in voisins.get(mot[i], ()) else "frappe"))
    return [(t, k) for t, k in resultat if t and t != mot]


def _elisions(mot: str) -> list[str]:
    """« jaime » → j'aime, « lhomme » → l'homme, « quil » → qu'il."""
    resultat = []
    for tete in sorted(TABLES_ORTHO.elidees, key=len, reverse=True):
        reste = mot[len(tete) :]
        if mot.startswith(tete) and len(reste) >= 2 and reste[0] in _VOYELLES:
            resultat.append(f"{tete}'{reste}")
    return resultat


def _coupures(mot: str) -> list[str]:
    """« lamaison » → la maison : deux mots du lexique collés."""
    return [f"{mot[:i]} {mot[i:]}" for i in range(2, len(mot) - 1)]


def _mots_de(remplacement: str, original: Mot) -> list[Mot]:
    """Mots du texte de remplacement, tous situés sur la plage du mot fautif."""
    mots = tokeniser(remplacement).mots
    resultat = []
    for k, m in enumerate(mots):
        segments = [replace(s, debut=original.debut, fin=original.fin) for s in m.segments]
        resultat.append(replace(m, debut=original.debut, fin=original.fin, segments=segments, espace_avant=original.espace_avant if k == 0 else True))
    return resultat
