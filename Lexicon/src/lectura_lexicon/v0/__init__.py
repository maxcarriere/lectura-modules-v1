# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
# Copie de lectura-lexique 1.6.1 (module Lexique v0), incluse dans lectura-lexicon (Lexicon v1) :
# imports renommés lectura_lexique → lectura_lexicon.v0, code inchangé.
"""lectura-lexique : module partage d'acces au lexique Lectura.

Usage::

    from lectura_lexicon.v0 import Lexique

    with Lexique("lexique.db") as lex:
        print(lex.existe("chat"))       # True
        print(lex.phone_de("chat"))     # "ʃa"
        print(lex.homophones("ʃa"))     # [{"ortho": "chat", ...}, ...]
"""

__version__ = "1.6.1"

from lectura_lexicon.v0._types import (
    Categorie,
    Concept,
    EntreeForme,
    EntreeLemme,
    EntreeLexicale,
    LexiqueProtocol,
    SensDefinition,
)
from lectura_lexicon.v0._utils import generer_phones_proches, normaliser_ortho
from lectura_lexicon.v0.lexique import Lexique

__all__ = [
    "Categorie",
    "Concept",
    "EntreeForme",
    "EntreeLemme",
    "EntreeLexicale",
    "Lexique",
    "LexiqueProtocol",
    "SensDefinition",
    "generer_phones_proches",
    "normaliser_ortho",
]
