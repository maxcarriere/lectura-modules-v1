# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Analyseur du français (module NLP-FR v1 de Lectura) : texte ⇄ phonétique (tokenisation, abrègements, formules,
analyse grammaticale, modèle de mot, liaisons, e caduc) avec alignement linéaire.

Anciennement ``lectura-transducer`` 1.1.0 (lecture 1.0.5, écriture 1.1.0) : ce sous-paquet en est la copie figée ;
``import lectura_transducer`` y mène (alias installé par ``lectura_nlp_fr``). Entrée conseillée :
``lectura_nlp_fr.creer_moteur``.
"""

from ..erreurs import AvertissementNLP, ModelesAbsents
from .decoupage_texte import TYPES_DE_FORMULE, MotTexte, decouper
from .moteur import creer_moteur
from .index_phone import IndexMemoire, IndexSqlite
from .recomposition import recomposer
from .structures import Canal, Document, Mot, NiveauPhone, Phrase, Segment, TypeMot
from .tokeniseur import tokeniser, tokeniser_phone

__version__ = "1.1.0"          # version de la chaîne (Transducer 1.1.0) ; celle du paquet : lectura_nlp_fr.__version__

__all__ = [
    "AvertissementNLP",
    "ModelesAbsents",
    "Canal",
    "Document",
    "IndexMemoire",
    "IndexSqlite",
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
