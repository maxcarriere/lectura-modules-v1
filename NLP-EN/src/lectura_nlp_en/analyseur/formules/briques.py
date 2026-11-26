# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Briques des formules : signes écrits et leurs lectures, extraits du lexique.

Table ``data/briques_formules.tsv``, générée par ``outils/construire_briques_formules.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib import resources


@dataclass(frozen=True)
class Brique:
    categorie: str
    signe: str
    lecture: str
    lecture_pluriel: str
    genre: str
    phone: str
    origine: str


@cache
def briques(categorie: str) -> dict[str, Brique]:
    """Briques d'une catégorie (ou d'une famille : « maths » couvre « maths:operateur »…), par signe."""
    texte = resources.files("lectura_nlp_en.analyseur.data").joinpath("briques_formules.tsv").read_text(encoding="utf-8")
    resultat = {}
    for ligne in texte.splitlines():
        if ligne and not ligne.startswith("#"):
            b = Brique(*ligne.split("\t"))
            if b.categorie == categorie or b.categorie.startswith(categorie + ":"):
                resultat[b.signe] = b
    return resultat
