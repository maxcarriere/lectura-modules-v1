# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Supplément d'écriture : formes absentes du lexique embarqué (mots rares, flexions, noms propres), consultées
**seulement dans le sens phonétique → orthographe**, pour que la lecture (et donc la phonémisation des corpus) ne
change pas.

Fichier ``supplement_ecriture.db`` (SQLite, lu à la demande ; dans le dossier des modèles, éventuellement en
``.xz``, sinon dans ``data/``). Construit par ``outils/construire_supplement_ecriture.py`` à partir de fichiers au
format de ``data/correctifs.tsv`` (recherche v2, piste P2). Les entrées ont la même force que les correctifs (elles
passent devant les analyses de même graphie et de même catégorie), mais les noms propres n'y entrent que là où
aucun mot n'a déjà leur prononciation : cette garde est faite à la construction.

Le sens est porté par ``ECRITURE`` (une ``ContextVar``, sûre entre fils et tâches) : ``Chaine.ecrire`` l'active le
temps d'une écriture ; partout ailleurs, le lexique et l'index enveloppés se comportent exactement comme sans
supplément.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

from .analyse import Entree
from .index_phone import MOT, Lecture, alternatives, neutraliser

FICHIER = "supplement_ecriture.db"
ECRITURE: ContextVar[bool] = ContextVar("ecriture", default=False)


@contextmanager
def ecriture():
    """Active le supplément le temps d'une écriture (phonétique → orthographe)."""
    jeton = ECRITURE.set(True)
    try:
        yield
    finally:
        ECRITURE.reset(jeton)


def trouver(dossier: Path | None) -> Path | None:
    """Chemin du supplément : dossier des modèles (``.db`` ou ``.db.xz``), sinon ``data/`` du paquet ; None sinon."""
    if dossier is not None and ((dossier / FICHIER).exists() or (dossier / f"{FICHIER}.xz").exists()):
        from .moteur import fichier

        return fichier(dossier, FICHIER)
    local = Path(__file__).parent / "data" / FICHIER
    return local if local.exists() else None


class Supplement:
    """Accès SQLite aux entrées du supplément (formes et clés phonétiques)."""

    def __init__(self, chemin: str | Path):
        self._db = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True, check_same_thread=False)
        self.par_ortho = lru_cache(maxsize=1 << 16)(self._par_ortho)
        self.par_phone = lru_cache(maxsize=1 << 16)(self._par_phone)
        self.zipf_cle = lru_cache(maxsize=1 << 16)(self._zipf_cle)

    @staticmethod
    def _entree(ortho, upos, traits, lemme, phone_enrichi, phone, zipf) -> Entree:
        # lemme et phonétique enrichie vides : égaux à la graphie et à la phonétique syllabée (place gagnée)
        feats = dict(t.split("=", 1) for t in (traits or "").split("|") if "=" in t)
        return Entree(ortho, upos, feats, lemme or ortho, phone_enrichi or phone, (), float(zipf or 0))

    def _par_ortho(self, ortho: str) -> tuple[Entree, ...]:
        lignes = self._db.execute(
            "select * from formes where ortho = ? order by rowid", (ortho,))
        return tuple(self._entree(*l) for l in lignes)

    def _par_phone(self, phone: str) -> tuple[Entree, ...]:
        lignes = self._db.execute(
            "select * from formes where phone = ? order by rowid", (phone,))
        return tuple(self._entree(*l) for l in lignes)

    def _zipf_cle(self, cle: str) -> float | None:
        return self._db.execute("select max(zipf) from cles where cle = ?", (cle,)).fetchone()[0]

    def phones(self, cle: str, neutre: bool = False) -> list[str]:
        """Écritures syllabées (colonne ``phone``) des entrées qui ont cette clé (voyelles moyennes confondues si ``neutre``)."""
        colonne = "neutre" if neutre else "cle"
        lignes = self._db.execute(f"select phone from cles where {colonne} = ? order by rowid",
                                  (neutraliser(cle) if neutre else cle,))
        return list(dict.fromkeys(p for p, in lignes))

    def remplace(self, e: Entree) -> bool:
        return any(c.upos == e.upos for c in self.par_ortho(e.ortho))


class LexiqueSupplement:
    """Un lexique (interface ``Lexique``) complété par le supplément pendant l'écriture seulement."""

    def __init__(self, lexique, supplement: Supplement):
        self._lexique = lexique
        self._supplement = supplement

    def lectures(self, forme: str) -> list[Entree]:
        base = self._lexique.lectures(forme)
        if not ECRITURE.get():
            return base
        s = self._supplement
        propres = list(s.par_ortho(forme))
        if forme != forme.lower():
            propres += s.par_ortho(forme.lower())
        return propres + [e for e in base if not s.remplace(e)] if propres else base

    def graphies(self, phones: list[str]) -> list[Entree]:
        base = self._lexique.graphies(phones)
        if not ECRITURE.get():
            return base
        s = self._supplement
        propres = [e for p in phones for e in s.par_phone(p)]
        return propres + [e for e in base if not s.remplace(e)]

    def aligner(self, entree: Entree) -> Entree:
        return self._lexique.aligner(entree)

    def __getattr__(self, nom):
        return getattr(self._lexique, nom)


class IndexSupplement:
    """Un index phonétique (interface ``IndexPhone``) qui connaît, pendant l'écriture, les clés du supplément."""

    def __init__(self, index, supplement: Supplement):
        self._index = index
        self._supplement = supplement

    def lectures(self, cle: str) -> dict[str, Lecture]:
        lectures = self._index.lectures(cle)
        if not ECRITURE.get():
            return lectures
        zipf = self._supplement.zipf_cle(cle)
        if zipf is not None and (MOT not in lectures or lectures[MOT].zipf < zipf):
            lectures = dict(lectures)
            lectures[MOT] = Lecture(MOT, cle, zipf)
        return lectures

    def composes(self, cle: str):
        return self._index.composes(cle)

    def prononciations(self, cle: str, neutre: bool = False) -> list[str]:
        resultat = list(self._index.prononciations(cle, neutre))
        if ECRITURE.get():
            resultat += [p for p in self._supplement.phones(cle, neutre) if p not in resultat]
        return resultat

    def __getattr__(self, nom):
        return getattr(self._index, nom)


def appliquer(lexique, index, dossier: Path | None = None):
    """(lexique, index) complétés par le supplément d'écriture ; inchangés s'il n'est pas installé."""
    chemin = trouver(dossier)
    if chemin is None:
        return lexique, index
    s = Supplement(chemin)
    return LexiqueSupplement(lexique, s), (IndexSupplement(index, s) if index is not None else None)


def construire(sources: list[str | Path], chemin: str | Path) -> int:
    """Construit ``supplement_ecriture.db`` depuis des fichiers au format de ``data/correctifs.tsv`` ; rend le nombre
    d'entrées. Une graphie déjà vue (même graphie, même catégorie) dans un fichier précédent est ignorée."""
    from .correctifs import _brute, charger

    chemin = Path(chemin)
    chemin.unlink(missing_ok=True)
    db = sqlite3.connect(chemin)
    db.execute("create table formes (ortho text, upos text, traits text, lemme text, phone_enrichi text, phone text, zipf real)")
    db.execute("create table cles (cle text, neutre text, phone text, zipf real)")
    vues: set[tuple[str, str]] = set()
    cles: dict[tuple[str, str], float] = {}         # (clé, phone) → zipf le plus haut, dans l'ordre d'arrivée
    n = 0
    for source in sources:
        entrees = [e for e in charger(source) if (e.ortho, e.upos) not in vues]   # plusieurs analyses par fichier
        vues |= {(e.ortho, e.upos) for e in entrees}
        for e in entrees:
            phone = _brute(e.phone_enrichi)
            traits = "|".join(f"{k}={v}" for k, v in e.feats.items())
            db.execute("insert into formes values (?, ?, ?, ?, ?, ?, ?)",
                       (e.ortho, e.upos, traits, "" if e.lemme == e.ortho else e.lemme,
                        "" if e.phone_enrichi == phone else e.phone_enrichi, phone, e.frequence))
            if " " not in e.ortho:
                for cle in alternatives(e.phone_enrichi):
                    if (cle, phone) in cles:
                        cles[cle, phone] = max(cles[cle, phone], e.frequence)
                    else:
                        cles[cle, phone] = e.frequence
            n += 1
    db.executemany("insert into cles values (?, ?, ?, ?)", ((c, neutraliser(c), p, z) for (c, p), z in cles.items()))
    db.execute("create index formes_ortho on formes (ortho)")
    db.execute("create index formes_phone on formes (phone)")
    db.execute("create index cles_cle on cles (cle)")
    db.execute("create index cles_neutre on cles (neutre)")
    db.commit()
    db.execute("vacuum")
    db.close()
    return n
