"""Supplément d'écriture (``supplement.py``, piste P2) : consulté dans le sens phonétique → orthographe seulement."""

import pytest

from lectura_nlp_fr.analyseur import supplement
from lectura_nlp_fr.analyseur.analyse import Entree
from lectura_nlp_fr.analyseur.index_phone import MOT, IndexMemoire
from lectura_nlp_fr.analyseur.moteur import dossier_modeles

FORT = Entree("fort", "ADJ", {}, "fort", "fɔʁ[t]", (), 5.0)


class Lexique:
    def __init__(self, entrees):
        self.entrees = entrees

    def lectures(self, forme):
        return [e for e in self.entrees if e.ortho in (forme, forme.lower())]

    def graphies(self, phones):
        return [e for e in self.entrees if e.phone_enrichi in phones]

    def aligner(self, entree):
        return entree


@pytest.fixture
def base(tmp_path):
    source = tmp_path / "s.tsv"
    source.write_text("Tendulkar\tPROPN\t\tTendulkar\ttɑ̃.dyl.kaʁ\t1.66\tessai\n"
                      "skieuses\tNOUN\tGender=Fem|Number=Plur\tskieur\tski.øz\t1.9\tessai\n", encoding="utf-8")
    chemin = tmp_path / supplement.FICHIER
    assert supplement.construire([source], chemin) == 2
    s = supplement.Supplement(chemin)
    return supplement.LexiqueSupplement(Lexique([FORT]), s), supplement.IndexSupplement(IndexMemoire(), s)


def test_hors_ecriture_rien_ne_change(base):
    lexique, index = base
    assert lexique.lectures("Tendulkar") == [] and lexique.graphies(["tɑ̃.dyl.kaʁ"]) == []
    assert MOT not in index.lectures("tɑ̃dylkaʁ") and index.prononciations("tɑ̃dylkaʁ") == []
    assert [e.ortho for e in lexique.lectures("fort")] == ["fort"]


def test_en_ecriture(base):
    lexique, index = base
    with supplement.ecriture():
        assert [e.ortho for e in lexique.lectures("Tendulkar")] == ["Tendulkar"]
        assert [e.ortho for e in lexique.graphies(["tɑ̃.dyl.kaʁ"])] == ["Tendulkar"]
        (skieuses,) = lexique.lectures("skieuses")
        assert skieuses.feats == {"Gender": "Fem", "Number": "Plur"} and skieuses.lemme == "skieur"
        assert index.lectures("tɑ̃dylkaʁ")[MOT].zipf == pytest.approx(1.66)
        assert index.prononciations("tɑ̃dylkaʁ") == ["tɑ̃.dyl.kaʁ"]
        assert [e.ortho for e in lexique.lectures("fort")] == ["fort"]
    assert lexique.lectures("Tendulkar") == []          # le contexte refermé, le supplément ne compte plus


def test_sans_supplement(tmp_path, monkeypatch):
    monkeypatch.setattr(supplement, "trouver", lambda dossier: None)
    lexique, index = Lexique([FORT]), IndexMemoire()
    assert supplement.appliquer(lexique, index, tmp_path) == (lexique, index)


@pytest.mark.skipif(dossier_modeles() is None or supplement.trouver(dossier_modeles()) is None,
                    reason="modèles ou supplément absents")
def test_moteur_lecture_inchangee_ecriture_enrichie():
    """La lecture d'un nom du supplément est celle du modèle de mot (inchangée) ; l'écriture retrouve sa graphie."""
    from lectura_nlp_fr.analyseur import creer_moteur

    moteur = creer_moteur("local", juge=False)
    (lu,) = moteur.lire("Tendulkar")
    assert lu["mots"][0]["origine"] == "modele"
    (ecrit,) = moteur.ecrire(lu["phone"])
    assert ecrit["ortho"].startswith("Tendulkar")


@pytest.mark.skipif(dossier_modeles() is None or supplement.trouver(dossier_modeles()) is None,
                    reason="modèles ou supplément absents")
@pytest.mark.parametrize("nom", ["Plitvice", "Rossby", "Bigflo"])
def test_moteur_noms_wikidata(nom):
    """Noms ajoutés depuis Wikidata (WikiLexik, ``p2/4_noms_wikidata.tsv``) : l'écriture retrouve leur graphie."""
    from lectura_nlp_fr.analyseur import creer_moteur

    moteur = creer_moteur("local", juge=False)
    (lu,) = moteur.lire(nom)
    (ecrit,) = moteur.ecrire(lu["phone"])
    assert ecrit["ortho"] == nom
