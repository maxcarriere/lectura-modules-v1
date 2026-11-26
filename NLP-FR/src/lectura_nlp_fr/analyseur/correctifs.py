# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Correctifs manuels : quelques entrées du lexique corrigées ou ajoutées à la main, prioritaires sur le lexique et
l'index phonétique, sans reconstruire le lexique embarqué.

Fichier ``data/correctifs.tsv`` (tenu à la main) : une ligne par analyse, colonnes ``ortho upos traits lemme
phone_enrichi zipf note``. Une ligne remplace les analyses du lexique de même graphie et de même catégorie (ou s'y
ajoute s'il n'y en a pas) ; elle est lue dans les deux sens (texte → phonétique et phonétique → texte). Les erreurs
du lexique y trouvent une correction immédiate, à signaler aussi à LeXiK pour qu'elles disparaissent à la source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .analyse import Entree
from .index_phone import MOT, Lecture, alternatives, cle_de, neutraliser

FICHIER = Path(__file__).parent / "data" / "correctifs.tsv"


def charger(chemin: str | Path = FICHIER) -> list[Entree]:
    entrees = []
    chemin = Path(chemin)
    if not chemin.exists():
        return entrees
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if not ligne.strip() or ligne.startswith("#"):
            continue
        colonnes = (ligne.split("\t") + [""] * 7)[:7]
        ortho, upos, traits, lemme, phone_enrichi, zipf, _note = colonnes
        if ortho == "ortho" or not ortho or not phone_enrichi:
            continue                                     # en-tête, ligne incomplète
        feats = dict(t.split("=", 1) for t in traits.split("|") if "=" in t)
        entrees.append(Entree(ortho, upos, feats, lemme or ortho, phone_enrichi, (), float(zipf or 0)))
    return entrees


def _brute(phone_enrichi: str) -> str:
    from .modele_mot import projeter

    return projeter(phone_enrichi)


@dataclass
class _Table:
    par_ortho: dict[str, list[Entree]] = field(default_factory=dict)
    par_phone: dict[str, list[Entree]] = field(default_factory=dict)      # écriture syllabée (colonne phone)
    par_cle: dict[str, list[str]] = field(default_factory=dict)           # clé sans marques → écritures

    @classmethod
    def de(cls, entrees: list[Entree]) -> "_Table":
        t = cls()
        for e in entrees:
            t.par_ortho.setdefault(e.ortho, []).append(e)
            phone = _brute(e.phone_enrichi)
            t.par_phone.setdefault(phone, []).append(e)
            for cle in alternatives(e.phone_enrichi):
                if phone not in t.par_cle.setdefault(cle, []):
                    t.par_cle[cle].append(phone)
        return t

    def remplace(self, e: Entree) -> bool:
        return any(c.upos == e.upos for c in self.par_ortho.get(e.ortho, ()))


class LexiqueCorrige:
    """Un lexique (interface ``Lexique``) dont les correctifs passent devant."""

    def __init__(self, lexique, entrees: list[Entree]):
        self._lexique = lexique
        self._table = _Table.de(entrees)

    def lectures(self, forme: str) -> list[Entree]:
        propres = list(self._table.par_ortho.get(forme, ()))
        if forme != forme.lower():
            propres += self._table.par_ortho.get(forme.lower(), [])
        return propres + [e for e in self._lexique.lectures(forme) if not self._table.remplace(e)]

    def graphies(self, phones: list[str]) -> list[Entree]:
        propres = [e for p in phones for e in self._table.par_phone.get(p, ())]
        return propres + [e for e in self._lexique.graphies(phones) if not self._table.remplace(e)]

    def aligner(self, entree: Entree) -> Entree:
        return self._lexique.aligner(entree)

    def __getattr__(self, nom):
        return getattr(self._lexique, nom)


class IndexCorrige:
    """Un index phonétique (interface ``IndexPhone``) qui connaît aussi les prononciations des correctifs."""

    def __init__(self, index, entrees: list[Entree]):
        self._index = index
        self._table = _Table.de([e for e in entrees if " " not in e.ortho])
        self._neutres = {}                # clé neutralisée → clés, pour ne pas tout parcourir à chaque appel
        for c in self._table.par_cle:
            self._neutres.setdefault(neutraliser(c), []).append(c)
        self._zipf = {}
        for e in entrees:
            for cle in alternatives(e.phone_enrichi):
                self._zipf[cle] = max(self._zipf.get(cle, 0.0), e.frequence)

    def lectures(self, cle: str) -> dict[str, Lecture]:
        lectures = dict(self._index.lectures(cle))
        if cle in self._table.par_cle and (MOT not in lectures or lectures[MOT].zipf < self._zipf[cle]):
            lectures[MOT] = Lecture(MOT, cle, self._zipf[cle])
        return lectures

    def composes(self, cle: str):
        return self._index.composes(cle)

    def prononciations(self, cle: str, neutre: bool = False) -> list[str]:
        resultat = list(self._index.prononciations(cle, neutre))
        cles = self._neutres.get(neutraliser(cle), []) if neutre else [cle]
        for c in cles:
            resultat += [p for p in self._table.par_cle.get(c, ()) if p not in resultat]
        return resultat

    def __getattr__(self, nom):
        return getattr(self._index, nom)


def appliquer(lexique, index, chemin: str | Path = FICHIER):
    """(lexique, index) avec les correctifs du fichier ; inchangés s'il n'y en a aucun."""
    entrees = charger(chemin)
    if not entrees:
        return lexique, index
    return LexiqueCorrige(lexique, entrees), (IndexCorrige(index, entrees) if index is not None else None)
