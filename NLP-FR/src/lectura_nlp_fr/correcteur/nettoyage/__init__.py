# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""L'enveloppe : ce qui rend la chaîne tolérante aux entrées fautives (orthographe mal tapée,
phonétique mal transcrite). Le noyau, lui, suppose une phrase bien écrite ; rien d'ici n'est
appelé par défaut."""

from .ctc import depuis_ctc
from .nettoyage import Correction, Nettoyeur
from .phonetique import Tolerant

__all__ = ["Correction", "Nettoyeur", "Tolerant", "depuis_ctc"]
