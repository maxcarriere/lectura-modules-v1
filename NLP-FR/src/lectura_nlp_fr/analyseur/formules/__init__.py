# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Formules : forme écrite ↔ mots, dans les deux sens, avec alignement.

- ``analyser`` : forme écrite → valeur et lecture alignée (sens du TTS) ;
- ``reconnaitre`` : mots → valeurs et formes écrites (sens du STT) ;
- ``ecrire`` : valeur → forme écrite de référence.
"""

from __future__ import annotations

from dataclasses import dataclass

from .nombres import MotLu, elements
from .autres_types import (
    DUREE,
    FRACTION,
    INTERVALLE,
    MESURE,
    PLAGE,
    ROMAIN,
    SIGLE,
    TELEPHONE,
    Duree,
    Fraction,
    Intervalle,
    Mesure,
    Plage,
    Romain,
    Sigle,
    Telephone,
)
from .maths import MATHS, SCIENTIFIQUE
from .types import DATE, HEURE, MONNAIE, NOMBRE, ORDINAL, POURCENTAGE, Date, Heure, Monnaie, Nombre, Ordinal, Pourcentage

Valeur = object  #  | Pourcentage | Heure | Date | Monnaie | Telephone | Fraction | Mesure | Romain | Sigle

# Ordre d'essai : du plus spécifique au plus général.
TYPES = (DATE, HEURE, DUREE, TELEPHONE, MONNAIE, POURCENTAGE, MESURE, SCIENTIFIQUE, FRACTION, MATHS, PLAGE, ORDINAL, NOMBRE)
# Type qui commence par un crochet : essayé sur la ponctuation ouvrante.
TYPES_CROCHET = (INTERVALLE,)
# Types écrits en lettres : essayés sur les mots en capitales, pas sur les chaînes à chiffres.
TYPES_LETTRES = (ROMAIN, SIGLE)
TYPE_DE = {
    Date: DATE, Heure: HEURE, Duree: DUREE, Plage: PLAGE, Intervalle: INTERVALLE, Telephone: TELEPHONE, Monnaie: MONNAIE, Pourcentage: POURCENTAGE, Mesure: MESURE,
    Fraction: FRACTION, Ordinal: ORDINAL, Nombre: NOMBRE, Romain: ROMAIN, Sigle: SIGLE,
}

__all__ = [
    "Date", "Formule", "Fraction", "Heure", "Mesure", "Monnaie", "MotLu", "Nombre", "Ordinal", "Pourcentage",
    "Reconnue", "Romain", "Sigle", "Telephone",
    "analyser", "ecrire", "lire", "plages_par_composant", "reconnaitre", "reconnaitre_phone", "texte_lu",
]

# Mots trop ambigus pour être convertis quand ils sont seuls (article, adjectif, nom).
_SEULS_NON_CONVERTIS = frozenset(
    # « mil » / « mille » seuls : le mil (céréale) et « mille » sont homophones ; « mille » en lettres reste usuel.
    "un une neuf premier première premiers premières second seconde seconds secondes mil mille".split()
)


@dataclass(frozen=True)
class Formule:
    type: str
    valeur: Valeur
    debut: int
    fin: int
    lecture: list[MotLu]


@dataclass(frozen=True)
class Reconnue:
    debut: int          # indice du premier mot
    fin: int            # indice après le dernier mot
    type: str
    valeur: Valeur
    ecriture: str


def analyser(texte: str, position: int = 0, types: tuple = TYPES + TYPES_LETTRES) -> Formule | None:
    """Formule écrite la plus longue commençant à ``position`` (à longueur égale, le premier type)."""
    meilleur = None
    for t in types:
        m = t.motif.match(texte, position)
        if m and (meilleur is None or m.end() > meilleur[1].end()):
            if t.construire(m) is not None:
                meilleur = (t, m)
    if meilleur is None:
        return None
    t, m = meilleur
    return Formule(t.nom, t.construire(m), m.start(), m.end(), t.lire(m))


def lire(texte: str) -> list[str] | None:
    """Mots de la lecture d'une formule écrite seule."""
    formule = analyser(texte.strip())
    if formule is None or formule.fin != len(texte.strip()):
        return None
    return [m.texte for m in formule.lecture]


def plages_par_composant(lecture: list[MotLu]) -> list[tuple[int, int]]:
    """Plage de la source lue par chaque composant (surlignage par bloc)."""
    plages: dict[int, tuple[int, int]] = {}
    for m in lecture:
        debut, fin = plages.get(m.composant, (m.debut, m.fin))
        plages[m.composant] = (min(debut, m.debut), max(fin, m.fin))
    return [plages[k] for k in sorted(plages)]


def texte_lu(lecture: list[MotLu]) -> tuple[str, list[tuple[int, int]]]:
    """Texte de la lecture et place de chaque mot dans ce texte."""
    places, position = [], 0
    for m in lecture:
        places.append((position, position + len(m.texte)))
        position += len(m.texte) + 1
    return " ".join(m.texte for m in lecture), places


def ecrire(valeur: Valeur, **options) -> str:
    return TYPE_DE.get(type(valeur), MATHS).ecrire(valeur, **options)


def reconnaitre(mots: list[str], seuls_non_convertis: frozenset[str] = _SEULS_NON_CONVERTIS) -> list[Reconnue]:
    """Formules dites dans une suite de mots (formes du tokeniseur, composés à trait d'union).

    ``seuls_non_convertis`` : mots laissés tels quels quand ils forment un nombre à eux seuls.
    """
    elems, proprietaire = [], []
    for k, mot in enumerate(mots):
        for e in elements([mot]):
            elems.append(e)
            proprietaire.append(k)
    reconnues = []
    i = 0
    while i < len(elems):
        debut_de_mot = i == 0 or proprietaire[i] != proprietaire[i - 1]
        trouve = _reconnaitre_a(elems, proprietaire, i, seuls_non_convertis) if debut_de_mot else None
        if trouve is None:
            i += 1
            continue
        t, valeur, j = trouve
        reconnues.append(Reconnue(proprietaire[i], proprietaire[j - 1] + 1, t.nom, valeur, t.ecrire(valeur)))
        i = j
    return reconnues


def _reconnaitre_a(elems: list[str], proprietaire: list[int], i: int, seuls_non_convertis: frozenset[str]):
    meilleur = None
    for t in TYPES:
        resultat = t.reconnaitre(elems, i)
        if resultat is None:
            continue
        valeur, j = resultat
        if j < len(elems) and proprietaire[j] == proprietaire[j - 1]:
            continue  # s'arrête au milieu d'un mot composé
        if meilleur is None or j > meilleur[2]:
            meilleur = (t, valeur, j)
    if meilleur and meilleur[0] in (NOMBRE, ORDINAL) and meilleur[2] - i == 1 and elems[i] in seuls_non_convertis:
        return None
    return meilleur


from .phone import reconnaitre_phone  # noqa: E402
