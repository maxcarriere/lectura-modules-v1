# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Analyseur de l'anglais (fonction de base de ``lectura-nlp-en``) : texte ⇄ phonétique de l'anglais américain
(tokenisation aux conventions UD English-EWT, abrègements, formules, analyse grammaticale, modèle de mot, jonctions de
phrase) avec alignement linéaire. Même interface que l'Analyseur du français (``lectura_nlp_fr.analyseur``).

Reprend ``lectura-transducer-en`` 0.1.2 (code gelé ; adaptateurs de développement retirés). L'entrée habituelle est
``lectura_nlp_en.creer_moteur()``, qui ajoute les modes, Lexicon et le Correcteur.
"""

from .decoupage_texte import TYPES_DE_FORMULE, MotTexte, decouper
from .moteur import creer_moteur
from .recomposition import recomposer
from .structures import Canal, Document, Mot, NiveauPhone, Phrase, Segment, TypeMot
from .tokeniseur import tokeniser, tokeniser_phone

__version__ = "1.0.0"

__all__ = [
    "Canal",
    "Document",
    "Mot",
    "MotTexte",
    "NiveauPhone",
    "Phrase",
    "Segment",
    "TYPES_DE_FORMULE",
    "TypeMot",
    "creer_moteur",
    "decouper",
    "recomposer",
    "tokeniser",
    "tokeniser_phone",
]
