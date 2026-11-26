# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Index phonétique du lexique : ce que la recomposition a besoin de savoir d'une suite de phonèmes.

Les clés sont des suites de phonèmes sans aucune marque (ni « . », ni « ‿ », ni séparateur).
L'index est un fichier dérivé de ``lexik.db`` (``outils/construire_index_phone.py``).
"""

from __future__ import annotations

import itertools
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MOT = "mot"          # forme d'un mot en isolation
ELIDEE = "elidee"    # forme élidée (« ʒ » de « j' », « ʒysk » de « jusqu' »)
LIEE = "liee"        # forme en liaison, consonne latente réalisée (« pətit », « diz »)
ABREGE = "abrege"    # prononciation d'un abrègement (« ɛtseteʁa » : etc.) ; empêche seulement de couper l'unité


@dataclass(frozen=True)
class Lecture:
    nature: str
    base: str        # forme en isolation ; égale à la clé sauf pour LIEE
    zipf: float


@dataclass(frozen=True)
class Compose:
    phone_sep: str
    zipf: float
    locution: bool   # séparateurs à espaces : plusieurs mots


class IndexPhone(Protocol):
    def lectures(self, cle: str) -> dict[str, Lecture]: ...

    def composes(self, cle: str) -> list[Compose]: ...

    def prononciations(self, cle: str, neutre: bool = False) -> list[str]:
        """Écritures syllabées que le lexique donne à cette suite de phonèmes ; avec ``neutre``,
        aussi celles qui n'en diffèrent que par le timbre d'une voyelle moyenne (e/ɛ, o/ɔ, ø/œ)."""
        ...


class IndexMemoire:
    """Index en mémoire, pour les tests et les petits lexiques."""

    def __init__(self, lectures: list[tuple[str, str, str, float]] = (), composes: list[tuple[str, float]] = ()):
        self._lectures: dict[str, dict[str, Lecture]] = {}
        for cle, nature, base, zipf in lectures:
            self._lectures.setdefault(cle, {})[nature] = Lecture(nature, base, zipf)
        self._composes: dict[str, list[Compose]] = {}
        for phone_sep, zipf in composes:
            self._composes.setdefault(cle_de(phone_sep), []).append(Compose(phone_sep, zipf, " " in phone_sep))

    def lectures(self, cle: str) -> dict[str, Lecture]:
        return self._lectures.get(cle, {})

    def composes(self, cle: str) -> list[Compose]:
        return self._composes.get(cle, [])

    def prononciations(self, cle: str, neutre: bool = False) -> list[str]:
        if not neutre:
            return [cle] if cle in self._lectures else []
        return [c for c in self._lectures if neutraliser(c) == neutraliser(cle)]


class IndexSqlite:
    def __init__(self, chemin: str | Path):
        # Lecture seule, partagée entre fils (serveur : moteur créé dans un fil, utilisé dans un autre).
        self._base = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True, check_same_thread=False)

    def lectures(self, cle: str) -> dict[str, Lecture]:
        lignes = self._base.execute("SELECT nature, base, zipf FROM unites WHERE cle = ?", (cle,))
        return {nature: Lecture(nature, base, zipf) for nature, base, zipf in lignes}

    def composes(self, cle: str) -> list[Compose]:
        lignes = self._base.execute(
            "SELECT phone_sep, zipf, locution FROM composes WHERE cle = ? ORDER BY zipf DESC", (cle,)
        )
        return [Compose(p, z, bool(loc)) for p, z, loc in lignes]

    def prononciations(self, cle: str, neutre: bool = False) -> list[str]:
        if neutre:
            requete, valeur = "SELECT DISTINCT phone FROM prononciations WHERE neutre = ?", neutraliser(cle)
        else:
            requete, valeur = "SELECT phone FROM prononciations WHERE cle = ?", cle
        return [p for (p,) in self._base.execute(requete, (valeur,))]


_MARQUES = str.maketrans("", "", ".‿'- ")


def cle_de(phone: str) -> str:
    return phone.translate(_MARQUES)


_ACCOLADES = re.compile(r"\{([^{}]*)\}")
_AUTRES_MARQUES = re.compile(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*")


def alternatives(phone_enrichi: str) -> list[str]:
    """Clés des prononciations libres d'une entrée : « {e|ɛ}[t] » → ["e", "ɛ"] (la première est celle de
    ``phone``). Les autres marques (consonne latente, son facultatif, h aspiré) sont ignorées."""
    corps = _AUTRES_MARQUES.sub("", phone_enrichi)
    choix = [m.group(1).split("|") for m in _ACCOLADES.finditer(corps)]
    morceaux = _ACCOLADES.split(corps)[::2]
    cles = []
    for combinaison in itertools.product(*choix):
        texte = morceaux[0] + "".join(c + m for c, m in zip(combinaison, morceaux[1:]))
        cle = cle_de(texte)
        if cle not in cles:
            cles.append(cle)
    return cles


_NEUTRES = {"ɛ": "e", "ɔ": "o", "œ": "ø"}


def neutraliser(cle: str) -> str:
    """Confond les voyelles moyennes orales (e/ɛ, o/ɔ, ø/œ), opposition instable en parole ; les nasales restent."""
    resultat = []
    for i, c in enumerate(cle):
        nasale = cle[i + 1 : i + 2] == "\u0303"
        resultat.append(c if nasale else _NEUTRES.get(c, c))
    return "".join(resultat)


def forme_liee(cle: str, latente: str) -> str | None:
    """Réalise une marque de consonne latente du cadre : « [z] » ou « [a>b] » (spec 02 §4.2)."""
    # Marque à deux contextes « [a>b;a>c] » : le premier remplacement vaut devant voyelle
    # (séparateur « ; » dans le format v2, « , » dans l'ancien).
    marque = latente.strip("[]").replace(";", ",").split(",")[0]
    if not marque:
        return None
    if ">" not in marque:
        return cle + marque
    avant, apres = marque.split(">")
    if not apres or not cle.endswith(avant):
        return None
    return cle[: len(cle) - len(avant)] + apres
