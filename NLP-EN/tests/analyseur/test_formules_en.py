# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Formules anglaises : lecture (texte → mots), reconnaissance (mots → formule), aller-retour, alignement, contextes."""

import random

import pytest

from lectura_nlp_en.analyseur import tokeniser
from lectura_nlp_en.analyseur.formules import (
    TYPES,
    TYPES_CROCHET,
    TYPES_LETTRES,
    analyser,
    ecrire,
    plages_par_composant,
    reconnaitre,
)
from lectura_nlp_en.analyseur.formules.detection import detecter_formules
from lectura_nlp_en.analyseur.formules.nombres import (
    annee,
    ecrire_entier,
    elements,
    entier_depuis_elements,
    lire_chiffres,
    lire_paires,
)
from lectura_nlp_en.analyseur.structures import TypeMot

TOUS = TYPES + TYPES_CROCHET + TYPES_LETTRES


def lecture(texte: str) -> tuple[str, str]:
    f = analyser(texte, 0, TOUS)
    assert f is not None and f.fin == len(texte), texte
    return f.type, " ".join(m.texte for m in f.lecture)


# ── Nombres ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n, attendu", [
    (0, "zero"), (13, "thirteen"), (21, "twenty one"), (40, "forty"), (105, "one hundred five"),
    (1000, "one thousand"), (1905, "one thousand nine hundred five"), (12000, "twelve thousand"),
    (1000000, "one million"), (2500000000, "two billion five hundred million"),
])
def test_ecriture_des_entiers(n, attendu):
    assert " ".join(ecrire_entier(n)) == attendu


def test_aller_retour_des_entiers():
    alea = random.Random(0)
    for n in list(range(5000)) + [alea.randrange(10**15) for _ in range(5000)]:
        assert entier_depuis_elements(elements(ecrire_entier(n))) == n


@pytest.mark.parametrize("mots, n", [("one hundred and five", 105), ("a hundred", 100), ("twenty-one", 21),
                                     ("a thousand two hundred", 1200)])
def test_variantes_admises_en_sens_inverse(mots, n):
    assert entier_depuis_elements(elements(mots.split())) == n


@pytest.mark.parametrize("mots", ["twenty thousand hundred hundred", "one two three", "thousand thousand", "two one",
                                  "and five"])
def test_suites_qui_ne_sont_pas_des_entiers(mots):
    assert entier_depuis_elements(elements(mots.split())) is None


@pytest.mark.parametrize("n, attendu", [
    (1905, "nineteen oh five"), (1900, "nineteen hundred"), (1990, "nineteen ninety"), (2005, "two thousand five"),
    (2024, "twenty twenty four"), (1066, "ten sixty six"), (2000, "two thousand"), (1000, "one thousand"),
])
def test_annees(n, attendu):
    assert " ".join(annee(n)) == attendu


@pytest.mark.parametrize("chiffres, attendu", [
    ("405", "four oh five"), ("128", "one twenty eight"), ("1600", "sixteen hundred"), ("747", "seven forty seven"),
    ("100", "one hundred"), ("2000", "two thousand"),
])
def test_paires(chiffres, attendu):
    assert " ".join(m.texte for m in lire_paires(chiffres)) == attendu


def test_alignement_fin_des_chiffres():
    """twenty → chiffre des dizaines, five → unités ; thousand → la virgule ; zéros intérieurs muets."""
    mots = lire_chiffres("1025")
    assert [(m.texte, m.debut, m.fin) for m in mots] == [
        ("one", 0, 1), ("thousand", 0, 1), ("twenty", 2, 3), ("five", 3, 4)]
    f = analyser("12,345")
    assert [(m.texte, m.debut, m.fin) for m in f.lecture] == [
        ("twelve", 0, 2), ("thousand", 2, 3), ("three", 3, 4), ("hundred", 3, 4), ("forty", 4, 5), ("five", 5, 6)]
    f = analyser("2000")
    assert {(m.debut, m.fin) for m in f.lecture} == {(0, 4)}
    f = analyser("21st")
    assert [(m.texte, m.debut, m.fin) for m in f.lecture] == [("twenty", 0, 1), ("first", 1, 4)]


# ── Lectures ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ecrit, type_, lu", [
    ("42", "nombre", "forty two"),
    ("1,905", "nombre", "one thousand nine hundred five"),
    ("-3.5", "nombre", "minus three point five"),
    ("3.14159", "nombre", "three point one four one five nine"),
    ("007", "nombre", "zero zero seven"),
    ("103rd", "ordinal", "one hundred third"),
    ("12.5%", "pourcentage", "twelve point five percent"),
    ("5–10%", "pourcentage", "five to ten percent"),
    ("7:05", "heure", "seven oh five"),
    ("7:00", "heure", "seven o'clock"),
    ("7:30 p.m.", "heure", "seven thirty p m"),
    ("23:45", "heure", "twenty three forty five"),
    ("13:00", "heure", "thirteen hundred"),
    ("12:42:55", "heure", "twelve forty two and fifty five seconds"),
    ("1990s", "date", "nineteen nineties"),
    ("1800s", "date", "eighteen hundreds"),
    ("'90s", "date", "nineties"),
    ("80's", "date", "eighties"),
    ("20s", "date", "twenties"),
    ("'05", "date", "oh five"),
    ("March 5, 2020", "date", "March fifth twenty twenty"),
    ("5 March 2020", "date", "the fifth of March twenty twenty"),
    ("2020-03-05", "date", "March fifth twenty twenty"),
    ("3/5/2020", "date", "March fifth twenty twenty"),
    ("26/09/2000", "date", "September twenty sixth two thousand"),
    ("January 10–13, 2020", "date", "January tenth to thirteenth twenty twenty"),
    ("10–13 January", "date", "the tenth to the thirteenth of January"),
    ("$3.50", "monnaie", "three dollars fifty"),
    ("$3.05", "monnaie", "three dollars and five cents"),
    ("$0.50", "monnaie", "fifty cents"),
    ("$1", "monnaie", "one dollar"),
    ("$1.2 billion", "monnaie", "one point two billion dollars"),
    ("€3.5m", "monnaie", "three point five million euros"),
    ("£20", "monnaie", "twenty pounds"),
    ("99¢", "monnaie", "ninety nine cents"),
    ("10 km", "mesure", "ten kilometers"),
    ("1 km", "mesure", "one kilometer"),
    ("5 m", "mesure", "five meters"),
    ("8 hrs", "mesure", "eight hours"),
    ("100 mph", "mesure", "one hundred miles per hour"),
    ("-5 °C", "mesure", "minus five degrees Celsius"),
    ("5'10\"", "mesure", "five foot ten"),
    ("45°", "mesure", "forty five degrees"),
    ("2,000 m²", "mesure", "two thousand square meters"),
    ("30–35 °C", "mesure", "thirty to thirty five degrees Celsius"),
    ("40°42′46″N", "angle", "forty degrees forty two minutes forty six seconds north"),
    ("3/4", "fraction", "three quarters"),
    ("2/3", "fraction", "two thirds"),
    ("2 1/2", "fraction", "two and a half"),
    ("17/32", "fraction", "seventeen thirty seconds"),
    ("½", "fraction", "one half"),
    ("24/7", "fraction", "twenty four seven"),
    ("1990–95", "plage", "nineteen ninety to ninety five"),
    ("3–1", "plage", "three to one"),
    ("16:9", "plage", "sixteen to nine"),
    ("v2.0", "version", "version two point oh"),
    ("192.168.1.1", "version", "one ninety two dot one sixty eight dot one dot one"),
    ("2:03:45", "duree", "two hours three minutes forty five seconds"),
    ("1h30", "duree", "one hour thirty minutes"),
    ("[0, 1]", "intervalle", "from zero to one"),
    ("(555) 123-4567", "telephone", "five five five one two three four five six seven"),
    ("1-800-238-5355", "telephone", "one eight hundred two three eight five three five five"),
    ("x+1=3", "maths", "x plus one equals three"),
    ("f(x)=2x^2+3", "maths", "f of x equals two x squared plus three"),
    ("x^4", "maths", "x to the fourth"),
    ("10^-3", "maths", "ten to the minus three"),
    ("x_1", "maths", "x sub one"),
    ("sin(x)", "maths", "sine of x"),
    ("√2 ≈ 1.414", "maths", "the square root of two is approximately equal to one point four one four"),
    ("a ≤ b", "maths", "a is less than or equal to b"),
    ("(a+b)²", "maths", "open parenthesis a plus b close parenthesis squared"),
    ("2x4", "maths", "two by four"),
    ("6.02×10^23", "maths", "six point zero two times ten to the twenty third"),
    ("1.5e-3", "scientifique", "one point five times ten to the minus three"),
    ("Q1", "sigle", "Q one"),
])
def test_lectures(ecrit, type_, lu):
    assert lecture(ecrit) == (type_, lu)


# ── Aller-retour : texte → lecture → formule ───────────────────────────────────


@pytest.mark.parametrize("ecrit, canonique", [
    ("42", "42"), ("1,905", "1,905"), ("-3.5", "-3.5"), ("0.5", "0.5"), ("21st", "21st"), ("5%", "5%"),
    ("5–10%", "5–10%"), ("1990", "1990"), ("1905", "1905"), ("2005", "2005"), ("1066", "1066"), ("1990s", "1990s"),
    ("March 5, 2020", "March 5, 2020"), ("5 March 2020", "5 March 2020"), ("10–13 January", "10–13 January"), ("2020-03-05", "March 5, 2020"),
    ("January 1915", "January 1915"), ("January 10–13, 2020", "January 10–13, 2020"),
    ("$3.50", "$3.50"), ("$3.05", "$3.05"), ("$0.50", "$0.50"), ("$1", "$1"), ("$5 million", "$5 million"),
    ("$1.2 billion", "$1.2 billion"), ("99¢", "$0.99"), ("10 km", "10 km"), ("-5 °C", "-5 °C"), ("5'10\"", "5'10\""),
    ("3/4", "3/4"), ("2 1/2", "2 1/2"), ("17/32", "17/32"), ("1990–95", "1990–95"), ("3–1", "3–1"),
    ("v2.0", "v2.0"), ("6.2.1", "6.2.1"), ("2:03:45", "2:03:45"), ("1h30", "1 h 30 min"),
    ("(555) 123-4567", "555-123-4567"), ("1-800-238-5355", "1-800-238-5355"), ("+1 202-555-0143", "+1 202-555-0143"),
    ("x+1=3", "x + 1 = 3"), ("f(x)=2x^2+3", "f(x) = 2x² + 3"), ("x^4", "x^4"), ("10^-3", "10^-3"), ("x_1", "x_1"),
    ("sin(x)", "sin(x)"), ("6.02×10^23", "6.02×10^23"), ("1.5e-3", "1.5×10^-3"), ("2x4", "2x4"),
])
def test_aller_retour(ecrit, canonique):
    f = analyser(ecrit, 0, TOUS)
    mots = [m.texte for m in f.lecture]
    r = reconnaitre(mots)
    assert len(r) == 1 and (r[0].debut, r[0].fin) == (0, len(mots)), (ecrit, mots, r)
    assert r[0].ecriture == canonique
    assert ecrire(f.valeur) == canonique


@pytest.mark.parametrize("phrase, attendu", [
    ("we meet at seven thirty tonight", "7:30"),
    ("at thirteen hundred", "13:00"),
    ("it ends at eleven fifteen and eleven seconds a m", "11:15:11 a.m."),
    ("born on the fifth of March nineteen ninety", "5 March 1990"),
    ("September twentieth two thousand four eighteen p m", "September 20, 2000|4:18 p.m."),
    ("they won three to one", "3–1"),
    ("take Route four oh five", "405"),
    ("call one eight hundred two three eight five three five five", "1-800-238-5355"),
    ("version two point oh is out", "v2.0"),
])
def test_reconnaissance_en_contexte(phrase, attendu):
    assert "|".join(r.ecriture for r in reconnaitre(phrase.split())) == attendu


@pytest.mark.parametrize("phrase", [
    "one of the best", "the first time", "a second chance", "in nineteen forty eight",
    "from ten to twenty", "one half of them",
])
def test_reconnaissance_prudente(phrase):
    """Mots seuls ambigus, années, « from … to » : pas d'heure, pas de plage, pas de conversion d'un « one » seul."""
    types = {r.type for r in reconnaitre(phrase.split())}
    assert not types & {"heure", "plage", "fraction"}
    assert all(r.ecriture not in ("1", "1st", "2nd") for r in reconnaitre(phrase.split()))


# ── Détection en contexte ──────────────────────────────────────────────────────


def formules(texte: str) -> dict[str, tuple[str, str]]:
    doc = detecter_formules(tokeniser(texte))
    return {m.forme: (m.type_formule, " ".join(x.forme for x in m.lecture))
            for p in doc.phrases for m in p.mots if m.type is TypeMot.FORMULE}


@pytest.mark.parametrize("texte, forme, attendu", [
    ("From 10 to 13 January 2020 it rained.", "10", ("nombre", "the tenth")),
    ("From 10 to 13 January 2020 it rained.", "13 January 2020", ("date", "the thirteenth of January twenty twenty")),
    ("Pope John Paul II visited Poland.", "II", ("romain", "the second")),
    ("Chapter IV begins.", "IV", ("romain", "four")),
    ("He lives at 123 Main Street.", "123", ("nombre", "one twenty three")),
    ("He took Interstate 405 north.", "405", ("nombre", "four oh five")),
    ("The pole is 5 m long.", "5 m", ("mesure", "five meters")),
    ("In 1993, the corps moved.", "1993", ("date", "nineteen ninety three")),
    ("By the mid-1880s, it grew.", "mid-1880s", ("date", "mid eighteen eighties")),
    ("Call (555) 123-4567 now.", "(555) 123-4567", ("telephone", "five five five one two three four five six seven")),
    ("Solve 2 + 2 = 4 now.", "2 + 2 = 4", ("maths", "two plus two equals four")),
    ("The interval [0, 1] is closed.", "[0, 1]", ("intervalle", "from zero to one")),
    ("Born on 8 April 1990 here.", "8 April 1990", ("date", "the eighth of April nineteen ninety")),
    ("Tom & Jerry won.", "&", ("symbole", "and")),
    ("Meet @ noon.", "@", ("symbole", "at")),
    ("Room # 21 is free.", "#", ("symbole", "number")),
    ("Paris + London trip.", "+", ("symbole", "plus")),
    ("My 2k bucks.", "2k", ("nombre", "two thousand")),
    ("A 50K salary.", "50K", ("nombre", "fifty thousand")),
    ("A 4K TV.", "4K", ("nombre", "four K")),
    ("He ran a 5K race.", "5K", ("nombre", "five K")),
    ("It is 3x faster.", "3x", ("nombre", "three times")),
    ("Over 6,000+ people.", "6,000+", ("nombre", "six thousand plus")),
    ("Solve 2x + 1 = 5 now.", "2x + 1 = 5", ("maths", "two x plus one equals five")),
])
def test_detection(texte, forme, attendu):
    assert formules(texte).get(forme) == attendu, formules(texte)


@pytest.mark.parametrize("texte, forme", [
    ("The F-16 flew.", "F-16"), ("COVID-19 spread.", "COVID-19"), ("A 3-D film.", "3-D"), ("I/O w/o it.", "I/O"),
    ("I got 3!", "3!"), ("He wrote 978-3-16-148410-0.", "978-3-16-148410-0"), ("I <3 you.", "<3"),
])
def test_prose_qui_n_est_pas_des_maths(texte, forme):
    assert formules(texte).get(forme, ("", ""))[0] != "maths"


def test_unite_d_une_lettre_douteuse():
    """« 74 W 10th Street » : W n'est pas des watts devant un mot en capitale ou un nombre."""
    assert formules("He lives at 74 W 10th Street.").get("74 W") is None


def test_composants():
    f = analyser("March 5, 2020", 0, TOUS)
    assert plages_par_composant(f.lecture) == [(6, 7), (0, 5), (9, 13)]
    f = analyser("$3.50", 0, TOUS)
    assert [m.composant for m in f.lecture] == [0, 1, 2]




@pytest.mark.parametrize("texte", ["Mail john@example.com now.", "Tag #MeToo today.", "Ping @john now.", "I <3 you."])
def test_symboles_proteges(texte):
    assert all(t != "symbole" for t, _ in formules(texte).values())
