# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Mémoïsation des appels au lexique (``lectura_lexicon.Lexicon``) : les mêmes formes et lemmes reviennent sans cesse
(être, avoir, les…) et ``formes_de`` coûte une requête SQL (15/10 : ~0,3 s dans la version 0.2, sans index sur les
lemmes). Enveloppe transparente : tout autre attribut est délégué au lexique."""

from __future__ import annotations

from functools import lru_cache


class LexiqueCache:
    def __init__(self, lexique, taille: int = 50_000):
        self._lex = lexique
        self.lectures = lru_cache(maxsize=taille)(lexique.lectures)
        self.formes_de = lru_cache(maxsize=taille)(lexique.formes_de)
        self.validite = lru_cache(maxsize=taille)(lexique.validite)
        self.frequence = lru_cache(maxsize=taille)(lexique.frequence)
        self.usuelle = lru_cache(maxsize=taille)(lexique.usuelle)
        self.forme = lru_cache(maxsize=taille)(lexique.forme)
        self.homophones = lru_cache(maxsize=taille)(lexique.homophones)
        self.voisins_orthographiques = lru_cache(maxsize=taille)(lexique.voisins_orthographiques)
        if hasattr(lexique, "rectifiee"):
            self.rectifiee = lru_cache(maxsize=taille)(lexique.rectifiee)
        if hasattr(lexique, "autre_genre"):
            self.autre_genre = lru_cache(maxsize=taille)(lexique.autre_genre)

    def __getattr__(self, nom):
        return getattr(self._lex, nom)
