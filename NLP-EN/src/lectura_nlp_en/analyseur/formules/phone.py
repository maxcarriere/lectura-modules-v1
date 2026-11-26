# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Formules dites dans une chaîne phonétique (sens STT) : **à porter** pour l'anglais."""

from __future__ import annotations

from ..structures import Mot
from . import Reconnue


def mot_de(mot: Mot) -> str:
    return mot.forme


def reconnaitre_phone(mots: list[Mot]) -> list[Reconnue]:
    return []
