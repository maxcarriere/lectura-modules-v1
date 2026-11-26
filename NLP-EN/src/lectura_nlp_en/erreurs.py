# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Erreurs et avertissements de ``lectura_nlp_en``.

Les erreurs de l'API (``ErreurAPI``, ``QuotaDepasse``) sont celles de ``lectura-lexicon`` : une seule classe à
attraper pour tous les modules v1 de Lectura.
"""

from __future__ import annotations


class AvertissementNLP(UserWarning):
    """Quelque chose manque ou change de chemin sans arrêter le calcul : juge absent, supplément absent, passage à
    l'API en mode ``auto``, base Lexicon absente. Jamais en silence."""


class ModelesAbsents(FileNotFoundError):
    """Modèles locaux introuvables alors qu'ils sont exigés (``mode="local"`` ou ``"degrade"``)."""


class FonctionIndisponible(RuntimeError):
    """Fonction impossible dans le mode choisi (par exemple le Correcteur en mode dégradé, sans base Lexicon)."""


try:                                               # mêmes classes que lectura-lexicon (dépendance par défaut)
    from lectura_lexicon.api import ErreurAPI, QuotaDepasse
except ImportError:                                # lectura-lexicon absent : classes équivalentes
    class ErreurAPI(RuntimeError):                 # type: ignore[no-redef]
        """L'API n'a pas répondu (réseau, délai, erreur du serveur) ou a refusé la requête."""

        def __init__(self, message: str, statut: int | None = None):
            super().__init__(message)
            self.statut = statut

    class QuotaDepasse(ErreurAPI):                 # type: ignore[no-redef]
        """Quota de l'API publique atteint (HTTP 429)."""


__all__ = ["AvertissementNLP", "ErreurAPI", "FonctionIndisponible", "ModelesAbsents", "QuotaDepasse"]
