# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Mode dégradé du lexique : aucune base locale, et pas d'API (mode ``local`` ou ``degrade``).

Toutes les fonctions lexicales répondent par ``Indisponible`` : une valeur fausse et vide, dont le texte est le
message « lexique indisponible : installer une base ou autoriser l'API ». Aucune exception : le programme continue.
"""

from __future__ import annotations

import warnings

MESSAGE = "lexique indisponible : installer une base ou autoriser l'API"


class Indisponible(tuple):
    """Réponse d'une fonction lexicale sans lexique : fausse, vide (itération vide, ``len`` 0), texte = message."""

    def __new__(cls, fonction: str = "", raison: str = ""):
        obj = super().__new__(cls)
        obj.fonction, obj.raison = fonction, raison
        return obj

    def __str__(self) -> str:
        return MESSAGE + (f" ({self.raison})" if self.raison else "")

    def __repr__(self) -> str:
        return f"Indisponible({str(self)!r})"


class LexiqueIndisponible:
    """Remplace ``Lexicon`` quand aucune base n'est disponible. ``disponible`` vaut ``False`` ; ``message`` dit
    pourquoi. Chaque fonction rend ``Indisponible`` (un avertissement au premier appel)."""

    disponible = False
    mode = "indisponible"
    langue = "en"

    def __init__(self, raison: str = ""):
        self.raison = raison
        self.message = MESSAGE + (f" ({raison})" if raison else "")
        self._averti = False

    def __repr__(self) -> str:
        return f"LexiqueIndisponible({self.raison!r})"

    def __bool__(self) -> bool:
        return False

    def fonctions(self) -> tuple[str, ...]:
        return ()

    def __getattr__(self, nom: str):
        if nom.startswith("_"):
            raise AttributeError(nom)

        def fonction(*args, **kwargs):
            if not self._averti:
                from .erreurs import AvertissementNLP

                warnings.warn(self.message, AvertissementNLP, stacklevel=2)
                self._averti = True
            return Indisponible(nom, self.raison)

        fonction.__name__ = nom
        return fonction
