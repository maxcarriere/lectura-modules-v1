# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Correctifs manuels (data/correctifs.tsv) : chaque ligne alignée redonne sa graphie et sa prononciation."""

from lectura_nlp_en.analyseur import correctifs


def test_couples_coherents():
    entrees = correctifs.charger()
    assert entrees
    for e in entrees:
        assert "".join(c.phone for c in e.couples) == e.phone_enrichi, e.ortho
        assert "".join(c.graphe for c in e.couples if not c.frontiere).lower() == e.ortho.lower(), e.ortho


def test_correctif_prioritaire():
    class Vide:
        def lectures(self, forme):
            return []

        def homophones(self, phone):
            return []

    lex = correctifs.appliquer(Vide())
    assert [e.phone_enrichi for e in lex.lectures("neat")] == ["ˈnit"]
    assert {e.upos for e in lex.lectures("printed")} == {"VERB", "ADJ"}
