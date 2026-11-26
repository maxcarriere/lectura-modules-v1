# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Abrègements anglais connus du lexique : sigles (FBI, U.S.), acronymes (NASA), abréviations (Mr., etc., e.g.),
unités (km, ft : abrègements seulement après un nombre).

Table ``data/abregements.tsv`` (``outils/construire_abregements.py``, depuis `NLP_EN/Lexique/dist/speciaux.tsv`). Le
tokeniseur s'en sert pour reconnaître un abrègement et donner sa nature ; le module des formules le lit selon cette
nature.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib import resources

SIGLE, ACRONYME, ABREVIATION, INITIALE = "sigle", "acronyme", "abreviation", "initiale"
# Titres devant un nom : ils ne finissent jamais une phrase (« Mr. Smith », « St. Louis »).
TITRES = frozenset(
    "Mr. Mrs. Ms. Messrs. Dr. Prof. St. Sts. Gen. Gens. Gov. Sen. Rep. Capt. Lt. Col. Sgt. Rev. Hon. Pres. Mt. Ft. "
    "Adm. Maj. Cmdr. Fr. Mme. Mlle. Brig. Cpl. Pvt. Supt. Insp. Det.".split()
)
# Les mêmes sans point (« Mr Smith », « St Louis ») : une forme ambiguë de cette liste reste un titre devant un nom.
TITRES_SANS_POINT = frozenset(t.rstrip(".") for t in TITRES)
# Abréviations qui peuvent finir une phrase : la phrase ne s'y arrête que devant un mot-outil à majuscule.
FINALES = frozenset("etc. Inc. Ltd. Co. Corp. Bros. Jr. Sr. a.m. p.m. A.M. P.M. e.g. i.e. al. Esq. approx. est. "
                    "U.S. U.K. U.N. D.C. B.C. A.D. U.S.A. Ph.D.".split())


@dataclass(frozen=True)
class Abregement:
    forme: str
    nature: str
    developpement: str
    phone: str
    ambigu: str = ""                 # « mot » (aussi un mot courant), « unite » (après un nombre seulement), ou vide
    mot_a_mot: bool = False          # abréviation de plusieurs mots lue par son développement (« et cetera »)


@cache
def table() -> dict[str, Abregement]:
    texte = resources.files("lectura_nlp_en.analyseur.data").joinpath("abregements.tsv").read_text(encoding="utf-8")
    resultat = {}
    for ligne in texte.splitlines():
        if ligne and not ligne.startswith("#"):
            forme, nature, developpement, phone, ambigu, mot_a_mot = (ligne.split("\t") + ["", "", "", "", ""])[:6]
            resultat[forme] = Abregement(forme, nature, developpement, phone, ambigu, mot_a_mot == "1")
    return resultat


@cache
def a_points() -> dict[str, list[str]]:
    """Abrègements écrits avec un point (« Mr. », « etc. », « e.g. »), par première lettre, du plus long au plus
    court."""
    resultat: dict[str, list[str]] = {}
    for f in sorted((f for f in table() if "." in f), key=len, reverse=True):
        resultat.setdefault(f[0], []).append(f)
    return resultat
