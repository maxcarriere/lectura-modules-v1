# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Branchement optionnel de Lexicon sur le transducteur anglais (``lectura_transducer_en``), sans changer son code.

Le transducteur écrit (phonétique → orthographe) avec son lexique embarqué, élagué : ce qu'il ne connaît pas est
écrit par le modèle de mot (P2G), qui se trompe sur les graphies irrégulières. Branché, Lexicon complète les
homophones d'une prononciation **que l'embarqué ne connaît pas** par les formes de la taille standard qui se
prononcent ainsi (acceptées, ni fautes connues, ni graphies britanniques, ni noms propres seuls, ni Spéciaux) ;
l'embarqué fait foi pour ce qu'il couvre, la lecture (orthographe → phonétique) est inchangée.

    from lectura_lexicon.en.transducer import brancher
    brancher(moteur.chaine, Lexicon(langue="en", mode="local", taille="standard").moteur)   # mode local seulement
"""

from __future__ import annotations

from functools import lru_cache

from .lexicon import _RANG, ACCEPTEE, Lexicon


class LexiqueElargi:
    def __init__(self, embarque, lexicon: Lexicon, zipf_min: float = 0.0, propres: bool = False,
                 britanniques: bool = False):
        from lectura_transducer_en.analyse import Entree
        from lectura_transducer_en.lexique import traits
        from lectura_transducer_en.phonetique import sans_marques

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
                    or _RANG.get(f.validite, 0) < _RANG[ACCEPTEE] or f.zipf < self.zipf_min:
                continue
            for l in f.lectures:
                if l.masquee or not l.phone or self._cle(l.phone) != cle:
                    continue
                res.append(self._Entree(l.ortho, l.upos, self._traits(l.feats), l.lemme or l.ortho,
                                        l.phone_enrichi or l.phone, (), l.zipf or f.zipf / 10))
        return tuple(res)


def brancher(chaine, lexicon: Lexicon, zipf_min: float = 0.0, propres: bool = False) -> None:
    """Remplace le lexique de la chaîne par sa version élargie (l'embarqué reste prioritaire)."""
    chaine.lexique = LexiqueElargi(chaine.lexique, lexicon, zipf_min, propres)
