# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Tests du cœur du Correcteur anglais (sautés si l'Analyseur, la base Lexicon ou le modèle de langue manquent).

Toutes les phrases sont écrites pour ces tests (aucune n'est tirée d'un corpus) ; « Twinkle Twinkle little star » est
une comptine du domaine public."""

import pytest

try:
    from lectura_nlp_en.correcteur import Correcteur

    C = Correcteur()
except (FileNotFoundError, ImportError):
    C = None
pytestmark = pytest.mark.skipif(C is None, reason="modèles absents")


def corrige(texte: str, mode: str = "suggestions") -> str:
    return C.corriger(texte, mode=mode).texte


@pytest.mark.parametrize("fautif, attendu", [
    ("i dont think so.", "I don't think so."),
    ("im sure he cant swim.", "I'm sure he can't swim."),
    ("I could of gone with them.", "I could have gone with them."),
    ("It is a apple and an book.", "It is an apple and a book."),
    ("He is an European citizen.", "He is a European citizen."),
    ("They went to the the market.", "They went to the market."),
    ("He go to school every day.", "He goes to school every day."),
    ("She doesn't likes cats.", "She doesn't like cats."),
    ("My friend will goes there.", "My friend will go there."),
    ("They have went home.", "They have gone home."),
    ("I recieve alot of mail.", "I receive a lot of mail."),
    ("This is a very intresting book.", "This is a very interesting book."),
    ("I don't know weather to go.", "I don't know whether to go."),
    ("It is bigger then the other one.", "It is bigger than the other one."),
    ("She borrowed her brothers old bike.", "She borrowed her brother's old bike."),
    ("It was a childrens museum.", "It was a children's museum."),
    ("The old gardener of Hendersons Father who lived alone.",
     "The old gardener of Henderson's Father who lived alone."),
    ("Swedens largest city is Stockholm.", "Sweden's largest city is Stockholm."),
])
def test_corrige(fautif, attendu):
    assert corrige(fautif) == attendu


@pytest.mark.parametrize("juste", [
    "The firm published its yearly report on Friday.",
    "Twinkle Twinkle little star.",
    "She bought a sports bag and the numbers show a steady rise.",
    "It set the tone for the meeting.",
    "I insist that he wait outside.",
    "Laura and Ben are brilliant.",
    "England are close to winning the cup.",
    "The study of glaciers is called glaciology.",
    "This is how an enzyme is made.",
    "He is an honest man and she is an hour late.",
    "Colour and centre are British spellings.",
    "They started a five hour chase.",
    "Roberts said that Evans was late.",
    "The Roberts family lives in Leeds.",
])
def test_ne_touche_pas(juste):
    assert corrige(juste) == juste
    assert corrige(juste, "automatique") == juste


def test_explications():
    r = C.corriger("He go to school.")
    assert "3e personne" in r.corrections[0].explication
    r = C.corriger("He go to school.", langue="en")
    assert "third person" in r.corrections[0].explication


def test_variete():
    c = Correcteur(variete="US")
    assert c.corriger("The colour of the centre.").texte == "The color of the center."
