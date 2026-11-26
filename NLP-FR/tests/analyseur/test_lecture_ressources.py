"""Remarques de l'instance Ressources sur la lecture (28/10/2026, 1 059 mots d'enfant) : alignement lettres ⇄ phonèmes
(h muet en tête de syllabe, « qu|i|ll », « oî » = /wa/), mots lus seuls, lemmes inventés par l'analyseur."""

import pytest

from lectura_nlp_fr.analyseur.analyse import Couple, redresser
from lectura_nlp_fr.analyseur.moteur import dossier_modeles

S = Couple(".", ".")


def test_redresser():
    c = lambda *x: tuple(Couple(p, g) for p, g in x)
    assert redresser(c(("k", "c"), ("a", "a"), ("", "h"), (".", "."), ("j", "i"), ("e", "er"))) \
        == c(("k", "c"), ("a", "a"), (".", "."), ("", "h"), ("j", "i"), ("e", "er"))
    assert redresser(c(("k", "q"), ("i", "u"), (".", "."), ("j", "ill"), ("a", "a"))) \
        == c(("k", "qu"), ("i", "i"), (".", "."), ("j", "ll"), ("a", "a"))
    assert redresser(c(("b", "b"), ("w", "o"), ("a", "î"), ("t", "t"))) == c(("b", "b"), ("wa", "oî"), ("t", "t"))
    assert redresser(c(("ɛ", "ai"), (".", "."), ("ɡ", "g"), ("ɥi", "ui"), ("j", "ll"))) \
        == c(("ɛ", "ai"), (".", "."), ("ɡ", "g"), ("ɥi", "ui"), ("j", "ll"))       # aiguille : inchangé


@pytest.fixture(scope="module")
def moteur():
    from lectura_nlp_fr.analyseur import creer_moteur

    return creer_moteur("local", juge=False, schwas_finaux=True)


def _syllabes(phrase):
    return "".join(("." if coupure == "SYL" else "") + (o if o != "_D" else "") for o, _, coupure in phrase["lineaire"])


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
@pytest.mark.parametrize("mot, attendu", [
    ("cahier", "ca.hier"), ("dehors", "de.hors"), ("cacahuète", "ca.ca.huè.te"), ("boîte", "boî.te"),
    ("jonquille", "jon.qui.lle"), ("table", "ta.ble"), ("piano", "pia.no"),
])
def test_syllabes_ecrites(moteur, mot, attendu):
    assert _syllabes(moteur.lire(mot)[0]) == attendu


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
@pytest.mark.parametrize("mot, phone, upos", [("mon", "mɔ̃", "DET"), ("fit", "fi", "VERB"), ("zèbre", "zɛ.bʁə", "NOUN")])
def test_mot_seul(moteur, mot, phone, upos):
    p = moteur.lire(mot)[0]
    assert p["phone"] == phone and p["mots"][0]["analyse"]["upos"] == upos


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
def test_lemme_du_lexique(moteur):
    mots = moteur.lire("Ces tomates sont mûres.")[0]["mots"]
    assert mots[3]["analyse"]["lemme"] == "mûr"
