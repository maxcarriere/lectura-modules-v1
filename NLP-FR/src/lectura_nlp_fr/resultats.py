# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Résultat du Correcteur, le même en mode local et en mode API."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Correction:
    """Une correction : ``debut`` et ``fin`` (positions dans le texte reçu), ``original``, ``proposition``, ``type``
    (frappe, accent, homophone, accord…), ``confiance``, ``motif``, ``explication`` (en français, pour l'élève)."""

    debut: int
    fin: int
    original: str
    proposition: str
    type: str                 # frappe, accent, homophone…
    confiance: float
    motif: str = ""
    mesures: dict = field(default_factory=dict)
    explication: str = ""     # en français, pour l'utilisateur (correcteur pédagogique)


@dataclass
class Resultat:
    """Texte corrigé et liste des corrections."""

    texte: str
    corrections: list[Correction] = field(default_factory=list)
