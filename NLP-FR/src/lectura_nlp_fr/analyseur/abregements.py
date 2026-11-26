# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Abrègements connus du lexique : sigles (SNCF), acronymes (NASA), abréviations (M., av. J.-C., etc.).

Table ``data/abregements.tsv`` (``outils/construire_abregements.py``). Le tokeniseur s'en sert pour reconnaître un
abrègement et donner sa nature ; le module des formules le lit selon cette nature.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib import resources

SIGLE, ACRONYME, ABREVIATION, INITIALE = "sigle", "acronyme", "abreviation", "initiale"
# Titres devant un nom : ils ne finissent jamais une phrase (« M. Dupont », « St. Louis »).
TITRES = frozenset("M. MM. Mme. Mmes. Mlle. Mlles. Me. Mgr. Dr. Pr. St. Ste. Sts. Vve.".split())
# Les mêmes sans point (« St Louis », « Mme Roy ») : une forme ambiguë de cette liste reste un titre devant un nom.
TITRES_SANS_POINT = frozenset(t.rstrip(".") for t in TITRES)


@dataclass(frozen=True)
class Abregement:
    forme: str
    nature: str
    developpement: str
    phone: str
    ambigu: str = ""                 # « mot » (aussi un mot courant : « Son », « pas. »), « romain » (« IV »), ou vide
    mot_a_mot: bool = False          # abréviation de plusieurs mots lue par son développement (« av. J.-C. »)


@cache
def table() -> dict[str, Abregement]:
    texte = resources.files("lectura_nlp_fr.analyseur.data").joinpath("abregements.tsv").read_text(encoding="utf-8")
    resultat = {}
    for ligne in texte.splitlines():
        if ligne and not ligne.startswith("#"):
            forme, nature, developpement, phone, ambigu, mot_a_mot = (ligne.split("\t") + ["", "", "", "", ""])[:6]
            resultat[forme] = Abregement(forme, nature, developpement, phone, ambigu, mot_a_mot == "1")
    return resultat


@cache
def a_points() -> dict[str, list[str]]:
    """Abrègements écrits avec un point (« M. », « etc. », « av. J.-C. »), par première lettre, du plus long au
    plus court."""
    resultat: dict[str, list[str]] = {}
    for f in sorted((f for f in table() if "." in f), key=len, reverse=True):
        resultat.setdefault(f[0], []).append(f)
    return resultat
