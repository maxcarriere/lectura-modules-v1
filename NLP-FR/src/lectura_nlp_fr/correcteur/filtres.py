# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Garde-fous communs au cœur et au réglage hors ligne (banc/balayer.py) : formes qu'on n'examine pas, homophones
qu'on ne propose pas. Relevés sur les fausses corrections d'UD et de prose (14/10)."""

from __future__ import annotations

SEULES = frozenset("aàyô")                 # mots d'une lettre (les autres : élisions « l », lettres « v »)


def mot(forme: str) -> bool:
    """Forme écrite d'un mot : lettres, trait d'union, apostrophe ; pas de nombre ni de locution (« en train »)."""
    return bool(forme) and forme[:1].isalpha() and all(ch.isalpha() or ch in "-'’" for ch in forme) \
        and (len(forme) > 1 or forme.lower() in SEULES)


def _upos(lex, forme: str) -> set[str]:
    return {l.upos for l in lex.lectures(forme.lower())}


def homophone_permis(lex, recue: str, proposition: str) -> bool:
    """Pas d'interjection (un → hein, mais → met ← eh) ni de nombre écrit en lettres (cent → sans, cinq → v)."""
    if not (mot(recue) and mot(proposition)):
        return False
    for forme in (recue, proposition):
        u = _upos(lex, forme)
        if u and u <= {"INTJ", "NUM", "X"}:
            return False
    return "NUM" not in _upos(lex, recue)
