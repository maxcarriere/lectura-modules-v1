# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Fonctions communes aux lexiques de l'analyseur (embarqué, correctifs) : traits UD et couples d'alignement."""

from __future__ import annotations

import json

from .analyse import Couple


def traits(feats: str) -> dict[str, str]:
    return dict(x.split("=", 1) for x in feats.split("|") if "=" in x) if feats and feats != "_" else {}


def couples_de(lineaire: str) -> tuple[Couple, ...]:
    if not lineaire:
        return ()
    return tuple(Couple(p, " " if g == "␣" else g) for p, g in json.loads(lineaire))
