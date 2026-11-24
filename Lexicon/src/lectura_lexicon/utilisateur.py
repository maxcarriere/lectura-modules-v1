# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Compatibilité avec lectura-lexicon 0.5 : ``lectura_lexicon.utilisateur`` est désormais ``lectura_lexicon.fr.utilisateur``
(français) ; l'anglais est dans ``lectura_lexicon.en.utilisateur``."""

from .fr.utilisateur import *  # noqa: F401,F403
