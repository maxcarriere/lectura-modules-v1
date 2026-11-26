# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Accès aux Analyseurs de Lectura (``lectura-nlp-fr``, ``lectura-nlp-en``), seule dépendance linguistique du
Traducteur. On ne s'en sert qu'en mode local :

- ``decouper(langue)`` : découpage du texte en phrases et en mots, formules repérées (sans modèle, sans réseau) ;
- ``analyseur_local(langue)`` : l'Analyseur en mode **local** (ses modèles sur la machine, jamais l'API), pour le
  glossaire (lemme, catégorie, prononciation de chaque mot).

Les modules sont cherchés parmi les paquets **installés**, dans l'ordre de ``MODULES`` : le nom v1, puis l'ancien nom
de la brique (gardé en alias par les paquets v1). Aucun chemin de développement n'est ajouté au chemin d'import.
"""
from __future__ import annotations

import importlib

# langue → (paquets possibles, du plus récent au plus ancien), paquet pip à installer
MODULES = {
    "fr": (("lectura_nlp_fr.analyseur", "lectura_transducer"), "lectura-nlp-fr"),
    "en": (("lectura_nlp_en.analyseur", "lectura_transducer_en"), "lectura-nlp-en"),
}
_cache: dict[str, object] = {}


def module(langue: str):
    """Paquet de l'Analyseur de la langue (``creer_moteur``, ``decoupage_texte``)."""
    if langue not in MODULES:
        raise ValueError(f"langue « {langue} » : fr ou en")
    if langue not in _cache:
        noms, pip = MODULES[langue]
        for nom in noms:
            try:
                _cache[langue] = importlib.import_module(nom)
                break
            except ImportError:
                continue
        else:
            raise ImportError(f"Analyseur {langue} absent : pip install {pip}")
    return _cache[langue]


def decouper(langue: str):
    """Fonction ``decouper(texte) -> list[list[mot]]`` de l'Analyseur (phrases, puis mots avec ``forme``, ``debut``,
    ``fin``, ``type``, ``type_formule``). Sans modèle ni réseau."""
    racine = module(langue)
    return importlib.import_module(racine.__name__ + ".decoupage_texte").decouper


def analyseur_local(langue: str, models_dir=None):
    """Analyseur de la langue en mode local (ses propres modèles : ``models_dir``, ``LECTURA_MODELS_DIR``,
    ``~/.lectura/models/…``). ``FileNotFoundError`` (``ModelesAbsents``) si ses modèles manquent : jamais de repli
    sur l'API. Le glossaire ne fait que lire : en français, le juge des homophones (qui sert à l'écriture) n'est pas
    chargé."""
    options = {"juge": False} if langue == "fr" else {}
    return module(langue).creer_moteur("local", models_dir=models_dir, **options)
