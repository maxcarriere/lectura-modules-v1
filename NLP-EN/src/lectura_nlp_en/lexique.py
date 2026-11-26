# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Branchement de Lexicon sur l'écriture de l'Analyseur anglais (base Lexicon locale seulement).

L'Analyseur écrit (phonétique → orthographe) avec son lexique embarqué, élagué ; ce
qu'il ne connaît pas est écrit par le modèle de mot, qui se trompe sur les graphies irrégulières. Branché, Lexicon
(base locale) complète les homophones d'une prononciation **que l'embarqué ne connaît pas** par les formes qui se
prononcent ainsi (acceptées, ni fautes connues, ni graphies britanniques, ni noms propres seuls, ni Spéciaux) ;
l'embarqué fait foi pour ce qu'il couvre, la lecture (orthographe → phonétique) est inchangée. Même règle que
``lectura_lexicon.en.transducer`` (branchement de ``lectura-nlp-en`` 0.3), réécrite sur les modules de ce paquet.
"""

from __future__ import annotations

from functools import lru_cache

_RANG = {"inconnue": 0, "rare": 1, "variante": 2, "acceptee": 3, "proposable": 4}


class LexiqueElargi:
    """Lexique embarqué de la chaîne, complété par Lexicon pour les prononciations qu'il ne connaît pas."""

    def __init__(self, embarque, lexicon, zipf_min: float = 0.0, propres: bool = False, britanniques: bool = False):
        from .analyseur.analyse import Entree
        from .analyseur.lexique import traits
        from .analyseur.phonetique import sans_marques

        self._Entree, self._traits, self._cle = Entree, traits, sans_marques
        self.embarque, self.lexicon = embarque, lexicon
        self.zipf_min, self.propres, self.britanniques = zipf_min, propres, britanniques

    def __getattr__(self, nom):
        return getattr(self.embarque, nom)

    def homophones(self, phone: str) -> list:
        return self.embarque.homophones(phone) or list(self._complement(self._cle(phone)))

    def connait_cle(self, phone: str) -> bool:
        return bool(self.homophones(phone))

    @lru_cache(maxsize=100_000)
    def _complement(self, cle: str) -> tuple:
        if not cle:
            return ()
        res = []
        for f in self.lexicon.homophones(cle, avec_lectures=True):
            if f.special or (f.propre and not self.propres) or (f.britannique and not self.britanniques) \
                    or _RANG.get(f.validite, 0) < _RANG["acceptee"] or f.zipf < self.zipf_min:
                continue
            for l in f.lectures:
                if l.masquee or not l.phone or self._cle(l.phone) != cle:
                    continue
                res.append(self._Entree(l.ortho, l.upos, self._traits(l.feats), l.lemme or l.ortho,
                                        l.phone_enrichi or l.phone, (), l.zipf or f.zipf / 10))
        return tuple(res)


def brancher(chaine, lexicon, zipf_min: float = 0.0, propres: bool = False) -> None:
    """Remplace le lexique de la chaîne locale par sa version élargie (l'embarqué reste prioritaire). ``lexicon`` :
    un ``Lexicon`` anglais **local** (jamais l'API : une requête par prononciation inconnue)."""
    if getattr(lexicon, "mode", "local") != "local":
        raise ValueError("branchement de Lexicon sur l'écriture : base locale seulement")
    chaine.lexique = LexiqueElargi(chaine.lexique, lexicon, zipf_min, propres)


__all__ = ["LexiqueElargi", "brancher"]
