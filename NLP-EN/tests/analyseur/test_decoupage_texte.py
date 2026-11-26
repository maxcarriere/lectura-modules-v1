# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Découpage anglais « texte → phrases → mots » (interface ``decouper``), conventions UD English-EWT."""

import pytest

from lectura_nlp_en.analyseur import decouper
from lectura_nlp_en.analyseur.decoupage_texte import (ABREGEMENT, FORMULE, MOT, PONCTUATION, TYPES_DE_FORMULE, VERSION,
                                                   MotTexte, tokens_de_surface)


def formes(texte):
    return [[m.forme for m in p] for p in decouper(texte)]


def surface(texte):
    return [["".join(m.forme for m in g) for g in tokens_de_surface(p)] for p in decouper(texte)]


def test_interface():
    assert VERSION.startswith("en-")
    p = decouper("Hello, world.")[0]
    assert all(isinstance(m, MotTexte) for m in p)
    assert [(m.forme, m.type, m.debut, m.fin, m.espace_avant) for m in p] == [
        ("Hello", MOT, 0, 5, False), (",", PONCTUATION, 5, 6, False), ("world", MOT, 7, 12, True), (".", PONCTUATION, 12, 13, False)]
    assert "monnaie" in TYPES_DE_FORMULE and "nombre" in TYPES_DE_FORMULE


@pytest.mark.parametrize("texte, attendu", [
    ("I don't know.", ["I", "do", "n't", "know", "."]),
    ("We can't, won't.", ["We", "ca", "n't", ",", "wo", "n't", "."]),
    ("I'm sure it's Bush's plan.", ["I", "'m", "sure", "it", "'s", "Bush", "'s", "plan", "."]),
    ("The workers' union.", ["The", "workers", "'", "union", "."]),
    ("You cannot go, you're gonna stay.", ["You", "can", "not", "go", ",", "you", "'re", "gon", "na", "stay", "."]),
    ("They'll say we'd have.", ["They", "'ll", "say", "we", "'d", "have", "."]),
    ("Its color is red.", ["Its", "color", "is", "red", "."]),
    ("I don’t know.", ["I", "do", "n't", "know", "."]),
])
def test_contractions(texte, attendu):
    assert formes(texte) == [attendu]


def test_tokens_de_surface():
    assert surface("I don't think Bush's workers' plan is gonna work.") == [
        ["I", "don't", "think", "Bush's", "workers'", "plan", "is", "gonna", "work", "."]]
    p = decouper("He said 'yes' to it.")[0]
    assert [m.forme for m in p] == ["He", "said", "'", "yes", "'", "to", "it", "."]


@pytest.mark.parametrize("texte, attendu", [
    ("Al-Zaman said so.", ["Al", "-", "Zaman", "said", "so", "."]),
    ("A far-left party.", ["A", "far", "-", "left", "party", "."]),
    ("An e-mail from a non-human co-worker.", ["An", "e-mail", "from", "a", "non-human", "co-worker", "."]),
    ("Call 713-853-3989 now.", ["Call", "713-853-3989", "now", "."]),
    ("Peace—at last.", ["Peace", "—", "at", "last", "."]),
    ("Use and/or not.", ["Use", "and", "/", "or", "not", "."]),
])
def test_tirets_et_obliques(texte, attendu):
    assert formes(texte) == [attendu]


def test_abreviations_et_fins_de_phrase():
    assert formes("Mr. Smith met Dr. Jones in St. Louis. They talked.") == [
        ["Mr.", "Smith", "met", "Dr.", "Jones", "in", "St.", "Louis", "."], ["They", "talked", "."]]
    assert formes("He lives in the U.S. The war ended.") == [
        ["He", "lives", "in", "the", "U.S", "."], ["The", "war", "ended", "."]]
    assert formes("The U.S. Army won.") == [["The", "U.S.", "Army", "won", "."]]
    assert formes("Apples, pears, etc. are fruit.") == [["Apples", ",", "pears", ",", "etc.", "are", "fruit", "."]]
    assert formes("J. R. R. Tolkien wrote it.") == [["J.", "R.", "R.", "Tolkien", "wrote", "it", "."]]
    assert formes("He took vitamin C. The end.") == [["He", "took", "vitamin", "C", "."], ["The", "end", "."]]
    assert formes('He said "No." Then he left.') == [["He", "said", '"', "No", ".", '"'], ["Then", "he", "left", "."]]
    assert formes("Really?! Yes... OK.") == [["Really", "?!"], ["Yes", "..."], ["OK", "."]]


def test_types_abregements():
    p = decouper("Mr. Smith of the FBI and NASA, e.g. here.")[0]
    types = {m.forme: (m.type, m.type_formule, m.lecture) for m in p}
    assert types["Mr."] == (ABREGEMENT, "abreviation", ("mister",))
    assert types["FBI"] == (ABREGEMENT, "sigle", ("F", "B", "I"))
    assert types["NASA"] == (ABREGEMENT, "acronyme", ("NASA",))
    assert types["e.g."][:2] == (ABREGEMENT, "abreviation")
    # « in » mot, « IT » mot hors contexte ; « km » abrègement seulement après un nombre
    p = decouper("It is in the box, per km.")[0]
    assert all(m.type != ABREGEMENT for m in p)


@pytest.mark.parametrize("texte, forme, type_formule, lecture", [
    ("It cost $3.50 today.", "$3.50", "monnaie", "three dollars fifty"),
    ("It cost $1 today.", "$1", "monnaie", "one dollar"),
    ("It cost $0.50 today.", "$0.50", "monnaie", "fifty cents"),
    ("They raised $5 million in all.", "$5 million", "monnaie", "five million dollars"),
    ("About 25 people came.", "25", "nombre", "twenty five"),
    ("About 1,905 people came.", "1,905", "nombre", "one thousand nine hundred five"),
    ("Pi is 3.14 roughly.", "3.14", "nombre", "three point one four"),
    ("It grew 5% last year.", "5%", "pourcentage", "five percent"),
    ("Born in 1990 here.", "1990", "date", "nineteen ninety"),
    ("Born in 1905 here.", "1905", "date", "nineteen oh five"),
    ("Born in 2005 here.", "2005", "date", "two thousand five"),
    ("In the 1990s it grew.", "1990s", "date", "nineteen nineties"),
    ("The 21st century began.", "21st", "ordinal", "twenty first"),
    ("We met at 7:30 pm sharp.", "7:30 pm", "heure", "seven thirty p m"),
    ("We met at 7:05 sharp.", "7:05", "heure", "seven oh five"),
    ("We met at 7:00 sharp.", "7:00", "heure", "seven o'clock"),
    ("It is 10 km long.", "10 km", "mesure", "ten kilometers"),
    ("Add 3/4 of it.", "3/4", "fraction", "three quarters"),
    ("He ruled 1509–1547 alone.", "1509–1547", "plage", "fifteen oh nine to fifteen forty seven"),
    ("Henry VIII ruled.", "VIII", "romain", "the eighth"),
    ("World War II ended.", "II", "romain", "two"),
    ("Born on 8 April 1990 here.", "8 April 1990", "date", "the eighth of April nineteen ninety"),
    ("On April 8, 2020, it rained.", "April 8, 2020", "date", "April eighth twenty twenty"),
    ("In January 1915 it began.", "January 1915", "date", "January nineteen fifteen"),
    ("It ended 32–23.", "32–23", "plage", "thirty two to twenty three"),
])
def test_formules(texte, forme, type_formule, lecture):
    mots = {m.forme: m for m in decouper(texte)[0]}
    assert forme in mots, [m.forme for m in decouper(texte)[0]]
    m = mots[forme]
    assert (m.type, m.type_formule, " ".join(m.lecture)) == (FORMULE, type_formule, lecture)


def test_formule_sans_lecture():
    p = decouper("See xk7q-#40213-2.DOC there.")[0]
    assert any(m.type == FORMULE and not m.lecture for m in p)


def test_positions():
    texte = "  I don't  know, Mr. Smith."
    for p in decouper(texte):
        for m in p:
            assert texte[m.debut:m.fin].replace("’", "'") == m.forme or m.type == PONCTUATION
