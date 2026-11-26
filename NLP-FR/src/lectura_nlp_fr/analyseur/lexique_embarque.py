# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Lexique embarqué du module (``donnees/embarque/lexique.db``, ``outils/construire_lexique_embarque.py``) derrière
l'interface ``Lexique`` : bibliothèque standard seule (sqlite3), sans la base complète ni le code de LeXiK.

Format compact : catégories, traits et natures codés par des tables ; lemme vide s'il est égal à la graphie ;
prononciation enrichie vide si elle est égale à la brute ; couples (phonème, graphème) codés par leurs longueurs
(``coder_couples``), la concaténation des phonèmes redonnant la prononciation enrichie et celle des graphèmes la
graphie (frontières de syllabe notées « . »).
"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path

from .analyse import Couple, Entree, redresser

_CHIFFRES = "0123456789abcdefghijklmnopqrstuvwxyz"
_SYLLABE = (".", ".")


def coder_couples(couples: list[tuple[str, str]], phone_enrichi: str, ortho: str) -> str:
    """« l=l e[z]=es » → « 11 42 » ; « . » pour une frontière de syllabe. Vide si les couples ne se recomposent
    pas en la prononciation et la graphie (le décodeur ne saurait pas les retrouver)."""
    jetons = []
    for p, g in couples:
        if (p, g) == _SYLLABE:
            jetons.append(".")
        elif len(p) < 36 and len(g) < 36:
            jetons.append(_CHIFFRES[len(p)] + _CHIFFRES[len(g)])
        else:
            return ""
    code = " ".join(jetons)
    return code if decoder_couples(code, phone_enrichi, ortho) == [tuple(c) for c in couples] else ""


def decoder_couples(code: str, phone_enrichi: str, ortho: str) -> list[tuple[str, str]]:
    resultat, i, j = [], 0, 0
    for jeton in code.split(" ") if code else ():
        if jeton == ".":
            resultat.append(_SYLLABE)
            i += 1 if phone_enrichi[i : i + 1] == "." else 0
            continue
        lp, lg = _CHIFFRES.index(jeton[0]), _CHIFFRES.index(jeton[1])
        resultat.append((phone_enrichi[i : i + lp], ortho[j : j + lg]))
        i, j = i + lp, j + lg
    return resultat


class LexiqueEmbarque:
    def __init__(self, dossier: str | Path):
        self._base = sqlite3.connect(f"file:{Path(dossier) / 'lexique.db'}?mode=ro", uri=True, check_same_thread=False)
        codes = {}
        for table in ("upos", "traits", "natures"):
            codes[table] = dict(self._base.execute(f"SELECT id, valeur FROM {table}"))
        self._upos, self._traits = codes["upos"], codes["traits"]
        self._natures = {k: tuple(v.split("\t")) for k, v in codes["natures"].items()}

    @lru_cache(maxsize=50_000)
    def lectures(self, forme: str) -> list[Entree]:
        entrees = self._lire(forme)
        if forme != forme.lower():
            entrees += self._lire(forme.lower())
        return entrees

    def graphies(self, phones: list[str]) -> list[Entree]:
        return [e for phone in phones for e in self._graphies(phone)]

    @lru_cache(maxsize=50_000)
    def _graphies(self, phone: str) -> tuple[Entree, ...]:
        lignes = self._base.execute(f"SELECT {_COLONNES} FROM formes WHERE phone = ?", (phone,))
        return tuple(self._entree(*l, avec_couples=False) for l in lignes if self._natures[l[1]][0] in ("Mots", "Spéciaux"))

    def aligner(self, entree: Entree) -> Entree:
        if entree.couples:
            return entree
        memes = [e for e in self._lire(entree.ortho)
                 if (e.upos, e.feats, e.lemme, e.phone_enrichi) == (entree.upos, entree.feats, entree.lemme, entree.phone_enrichi)]
        return memes[0] if memes else entree

    def _lire(self, forme: str) -> list[Entree]:
        return [self._entree(*l) for l in self._base.execute(f"SELECT {_COLONNES} FROM formes WHERE ortho = ?", (forme,))]

    def _entree(self, ortho, nature, upos, traits, lemme, phone, phone_enrichi, couples, frequence, avec_couples=True) -> Entree:
        phone_enrichi = phone_enrichi or phone
        resultat = ()
        if couples and avec_couples:
            paires = json.loads(couples) if couples.startswith("[") else decoder_couples(couples, phone_enrichi, ortho)
            resultat = redresser(tuple(Couple(p, g) for p, g in paires))
        feats = dict(t.split("=", 1) for t in self._traits.get(traits, "").split("|") if "=" in t)
        return Entree(ortho, self._upos.get(upos, ""), feats, lemme or ortho, phone_enrichi, resultat, frequence,
                      self._natures[nature][2])


_COLONNES = "ortho, nature, upos, traits, lemme, phone, phone_enrichi, couples, frequence"
