# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Correctifs manuels du lexique anglais (``data/correctifs.tsv``), prioritaires sur le lexique (complet ou embarqué),
dans les deux sens, sans reconstruire le lexique. Comme le français : une ligne par analyse, colonnes
``ortho upos traits lemme phone_enrichi zipf note [couples]`` ; elle remplace les analyses de même graphie et de même
catégorie (ou s'y ajoute). ``couples`` (facultatif, 27/10) : alignement fin en JSON, comme dans le lexique embarqué
(``[["ˈ", "."], ["p", "p"], …]``) ; sans lui, la ligne n'a qu'un couple, et les enchaînements perdent ses syllabes
internes. Toute correction est aussi à signaler au lexique (``NLP_EN/Lexique/tables/corrections_phone.tsv``).
"""

from __future__ import annotations

import json
from pathlib import Path

from .analyse import Couple, Entree
from .lexique import traits
from .phonetique import sans_marques

FICHIER = Path(__file__).parent / "data" / "correctifs.tsv"


def charger(chemin: str | Path = FICHIER) -> list[Entree]:
    entrees = []
    chemin = Path(chemin)
    if not chemin.exists():
        return entrees
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        if not ligne.strip() or ligne.startswith("#"):
            continue
        ortho, upos, feats, lemme, phone, zipf, _note, alignement = (ligne.split("\t") + [""] * 8)[:8]
        if alignement:
            couples = tuple(Couple(p, g) for p, g in json.loads(alignement))
        else:
            couples = ((Couple("ˈ", "."),) if phone.startswith("ˈ") else ()) + (Couple(phone.lstrip("ˈ"), ortho),)
        entrees.append(Entree(ortho, upos, traits(feats), lemme or ortho, phone, couples, float(zipf or 0)))
    return entrees


class AvecCorrectifs:
    """Le lexique, avec les correctifs devant."""

    def __init__(self, lexique, correctifs: list[Entree]):
        self._lexique = lexique
        self._par_forme: dict[str, list[Entree]] = {}
        self._par_cle: dict[str, list[Entree]] = {}
        for e in correctifs:
            self._par_forme.setdefault(e.ortho.lower(), []).append(e)
            self._par_cle.setdefault(sans_marques(e.phone_enrichi), []).append(e)

    def __getattr__(self, nom):
        return getattr(self._lexique, nom)

    def lectures(self, forme: str) -> list[Entree]:
        propres = self._par_forme.get(forme.lower(), [])
        if not propres:
            return self._lexique.lectures(forme)
        categories = {e.upos for e in propres}
        return propres + [e for e in self._lexique.lectures(forme) if e.upos not in categories]

    def homophones(self, phone: str) -> list[Entree]:
        propres = self._par_cle.get(sans_marques(phone), [])
        corriges = {(e.ortho.lower(), e.upos) for es in self._par_forme.values() for e in es}
        return propres + [e for e in self._lexique.homophones(phone) if (e.ortho.lower(), e.upos) not in corriges]


def appliquer(lexique, chemin: str | Path = FICHIER):
    correctifs = charger(chemin)
    return AvecCorrectifs(lexique, correctifs) if correctifs else lexique
