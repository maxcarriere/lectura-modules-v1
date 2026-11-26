# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Alias d'import des anciens noms : ``lectura_transducer_en`` → ``lectura_nlp_en.analyseur``, ``lectura_corrector_en`` →
``lectura_nlp_en.correcteur``.

Le chercheur rend **les mêmes objets de module** (pas une seconde copie) : ``lectura_transducer_en.chaine.Chaine`` est
``lectura_nlp_en.analyseur.chaine.Chaine``, et les ressources chargées (modèles, caches) ne le sont qu'une fois. Il est
installé en tête de ``sys.meta_path`` par ``import lectura_nlp_en`` ; si un ancien paquet ``lectura_transducer_en`` a déjà
été importé dans le processus, il est laissé tel quel et un avertissement le signale.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
import warnings

ALIAS = {"lectura_transducer_en": "lectura_nlp_en.analyseur", "lectura_corrector_en": "lectura_nlp_en.correcteur"}


class _Chargeur(importlib.abc.Loader):
    def __init__(self, cible: str):
        self.cible = cible

    def create_module(self, spec):
        return importlib.import_module(self.cible)

    def exec_module(self, module) -> None:
        pass


class Alias(importlib.abc.MetaPathFinder):
    def find_spec(self, nom, chemin=None, cible=None):
        for ancien, nouveau in ALIAS.items():
            if nom == ancien or nom.startswith(ancien + "."):
                vrai = nouveau + nom[len(ancien):]
                try:
                    spec = importlib.util.find_spec(vrai)
                except ModuleNotFoundError:
                    return None
                if spec is None:
                    return None
                return importlib.machinery.ModuleSpec(nom, _Chargeur(vrai),
                                                      is_package=spec.submodule_search_locations is not None)
        return None


def installer() -> None:
    if any(isinstance(f, Alias) for f in sys.meta_path):
        return
    for ancien, nouveau in ALIAS.items():
        deja = sys.modules.get(ancien)
        if deja is not None and getattr(deja, "__name__", "") != nouveau:
            from .erreurs import AvertissementNLP

            warnings.warn(f"« {ancien} » (ancien paquet) est déjà importé dans ce processus : l'alias vers {nouveau} "
                          "ne s'applique pas. Désinstaller l'ancien paquet (pip uninstall).", AvertissementNLP,
                          stacklevel=3)
    sys.meta_path.insert(0, Alias())
