"""Analyseur à porte (graphe du Correcteur) : porte fermée par défaut, phrase à canal mixte (``analyser_mixte``)."""

import pytest

from lectura_nlp_fr.analyseur.moteur import dossier_modeles


def _analyseur():
    dossier = dossier_modeles()
    if dossier is None:
        pytest.skip("modèles absents")
    from lectura_nlp_fr.analyseur.adaptateurs.analyseur_onnx import AnalyseurOnnx

    a = AnalyseurOnnx(dossier)
    if not a.porte:
        pytest.skip("analyseur sans porte")
    return a


def test_porte_fermee_par_defaut():
    a = _analyseur()
    assert a.correction == 0.0
    formes = ["Les", "enfants", "mangent", "."]
    mixte, _ = a.analyser_mixte(formes, [""] * 4, ["ortho"] * 4)
    assert [x.upos for x in mixte] == [x.upos for x in a.analyser(formes)]


def test_mot_donne_par_sa_prononciation():
    a = _analyseur()
    formes, phones = ["Les", "enfants", "mangent", "."], ["le", "ɑ̃fɑ̃", "mɑ̃ʒ", "."]
    canaux, cles = ["ortho", "ortho", "phone", "ortho"], ["", "", "mɑ̃ʒ", ""]
    analyses, details = a.analyser_mixte(formes, phones, canaux, cles=cles, correction=1.0)
    assert analyses[2].upos == "VERB" and analyses[2].feats.get("Number") == "Plur"
    assert "mangent" in details[2].graphies and details[2].traits["Number"]["Plur"] > 0.5
