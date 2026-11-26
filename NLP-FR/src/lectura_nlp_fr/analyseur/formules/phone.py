# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Reconnaissance des formules dans une phrase phonétique.

Chaque segment phonétique est ramené au mot du vocabulaire des formules qu'il prononce
(table générée depuis le lexique), puis la reconnaissance orthographique s'applique.
La phrase doit avoir été recomposée : ``vɛ̃t.dø`` y est un mot de deux segments.
"""

from __future__ import annotations

from functools import cache
from importlib import resources

from ..structures import Mot, TypeMot
from . import Reconnue, _SEULS_NON_CONVERTIS, reconnaitre
from .nombres import ELEMENTS

# Homophones de mots courants (« sans », « vin », « cette », « saint », « si », « dit ») :
# seuls, ils ne sont pas convertis.
_SEULS_NON_CONVERTIS_PHONE = _SEULS_NON_CONVERTIS | frozenset("cent vingt sept cinq six dix".split())
_HORS_VOCABULAIRE = "∅"


@cache
def _table() -> dict[str, str]:
    texte = resources.files("lectura_nlp_fr.analyseur.data").joinpath("formules_phone.tsv").read_text(encoding="utf-8")
    table: dict[str, str] = {}
    for ligne in texte.splitlines():
        if ligne and not ligne.startswith("#"):
            cle, mot = ligne.split("\t")
            # Singulier et pluriel se prononcent pareil : on garde le plus court.
            if cle not in table or len(mot) < len(table[cle]):
                table[cle] = mot
    return table


def mot_de(mot: Mot) -> str:
    """Mot du vocabulaire des formules prononcé par ``mot``, ou une marque hors vocabulaire."""
    if mot.type is not TypeMot.MOT:
        return _HORS_VOCABULAIRE
    table = _table()
    elems: list[str] = []
    for segment in mot.segments:
        if segment.forme in table:
            elems.append(table[segment.forme])
        else:
            # Numéral dont les éléments sont restés collés (« vɛ̃diz » : vingt + dix).
            morceaux = _decouper_numeral(segment.forme)
            if morceaux is None:
                return _HORS_VOCABULAIRE
            elems.extend(morceaux)
    return "-".join(elems)


def _decouper_numeral(forme: str) -> list[str] | None:
    """Découpe une suite de phonèmes en éléments de nombre, le plus long d'abord."""
    if not forme:
        return []
    table = _table()
    for k in range(len(forme), 0, -1):
        mot = table.get(forme[:k])
        if mot in ELEMENTS:
            reste = _decouper_numeral(forme[k:])
            if reste is not None:
                return [mot] + reste
    return None


def reconnaitre_phone(mots: list[Mot]) -> list[Reconnue]:
    return reconnaitre([mot_de(m) for m in mots], _SEULS_NON_CONVERTIS_PHONE)
