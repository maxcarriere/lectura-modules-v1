# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Lexique embarqué anglais (``lexique.db`` du dossier des modèles, livré avec eux) derrière l'interface ``Lexique`` : bibliothèque standard seule (sqlite3), sans les jeux TSV ni le code du lexique.

Élagué : Spéciaux, contractions, mots grammaticaux, mots fréquents, et les analyses que le modèle de mot prononce ou
écrit mal ; le reste est laissé au modèle de mot (GPA), que la chaîne appelle quand le lexique ne connaît pas le mot. Index des
homophones (table ``homophones``, comme l'``index_phone`` du français) : pour le sens phonétique → écrit, toutes les
analyses du lexique complet dont la prononciation est partagée par plusieurs graphies, sans couples.
Priorité des Spéciaux : une forme des Mots l'emporte, sauf sigle en capitales ou abréviation à point de même graphie.
"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path

from .analyse import Couple, Entree, sans_etendus
from .lexique import traits
from .phonetique import sans_marques

SCHEMA = """
CREATE TABLE entrees (ortho TEXT, ortho_min TEXT, cle TEXT, upos TEXT, feats TEXT, lemme TEXT, phone TEXT,
                      couples TEXT, zipf REAL, type TEXT, speciale INTEGER, raison TEXT, niveau TEXT);
CREATE INDEX i_forme ON entrees (ortho_min);
CREATE INDEX i_cle ON entrees (cle);
CREATE TABLE meta (cle TEXT, valeur TEXT);
CREATE TABLE homophones (ortho TEXT, ortho_min TEXT, cle TEXT, upos TEXT, feats TEXT, lemme TEXT, phone TEXT,
                         couples TEXT, zipf REAL, type TEXT, speciale INTEGER, raison TEXT, niveau TEXT);
CREATE INDEX i_homophones ON homophones (cle);
"""
_COLONNES = "ortho, upos, feats, lemme, phone, couples, zipf, type, speciale, niveau"


class LexiqueEmbarque:
    def __init__(self, chemin: str | Path):
        chemin = Path(chemin)
        if chemin.is_dir():
            chemin = chemin / "lexique.db"
        self._con = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True, check_same_thread=False)
        self._index = bool(self._con.execute("SELECT name FROM sqlite_master WHERE name = 'homophones'").fetchone())

    @staticmethod
    def _entree(ligne: tuple) -> Entree:
        ortho, upos, feats, lemme, phone, couples, zipf, type_, speciale, niveau = ligne
        cs = tuple(Couple(p, " " if g == "␣" else g) for p, g in json.loads(couples)) if couples else ()
        return Entree(ortho, upos, traits(feats), lemme, phone, cs, zipf or 0.0, type_ or "", bool(speciale), niveau or "")

    @lru_cache(maxsize=50_000)
    def _lignes(self, forme_min: str) -> tuple:
        return tuple(self._con.execute(f"SELECT {_COLONNES} FROM entrees WHERE ortho_min = ?", (forme_min,)).fetchall())

    def lectures(self, forme: str) -> list[Entree]:
        lignes = self._lignes(forme.lower().replace("’", "'"))
        mots = [l for l in lignes if not l[8]]
        speciaux = [l for l in lignes if l[8]]
        lettres = "".join(c for c in forme if c.isalpha())
        if speciaux and ((len(lettres) >= 2 and lettres.isupper()) or forme.endswith(".")) and any(l[0] == forme for l in speciaux):
            return [self._entree(l) for l in speciaux if l[0] == forme]
        return sans_etendus([self._entree(l) for l in (mots or speciaux)])

    def speciales(self, forme: str) -> list[Entree]:
        return [self._entree(l) for l in self._lignes(forme.lower()) if l[8]]

    @lru_cache(maxsize=50_000)
    def homophones(self, phone: str) -> list[Entree]:
        """Entrées gardées de cette prononciation, plus l'index des homophones (toutes les graphies du lexique complet
        qui partagent une prononciation avec une autre, sans couples : la chaîne les aligne au besoin)."""
        cle = sans_marques(phone)
        lignes = self._con.execute(f"SELECT {_COLONNES} FROM entrees WHERE cle = ?", (cle,)).fetchall()
        if self._index:
            lignes += self._con.execute(f"SELECT {_COLONNES} FROM homophones WHERE cle = ?", (cle,)).fetchall()
        return sans_etendus([self._entree(l) for l in lignes])

    def connait_cle(self, phone: str) -> bool:
        return bool(self.homophones(phone))
