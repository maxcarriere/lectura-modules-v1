"""Relecture de l'écriture par le modèle de langue écrit (``relecture.py``)."""

import pytest

from lectura_nlp_fr.analyseur.moteur import dossier_modeles
from lectura_nlp_fr.analyseur.relecture import FICHIER, Relecture, mots_ecrits


def test_mots_ecrits():
    assert mots_ecrits("L’œuf qu'il a vu, à 800 000 km : arc-en-ciel !") == [
        "l'", "oeuf", "qu'", "il", "a", "vu", "à", "<nombre>", "km", "arc-en-ciel"]


def _dossier_avec_relecture():
    dossier = dossier_modeles()
    if dossier is None or not (dossier / FICHIER).exists():
        return None
    try:
        import kenlm  # noqa: F401
    except ImportError:
        return None
    return dossier


@pytest.mark.skipif(_dossier_avec_relecture() is None, reason="modèles, langue_ecrite.bin ou kenlm absents")
def test_branchee_par_defaut():
    from lectura_nlp_fr.analyseur import creer_moteur

    moteur = creer_moteur("local")
    assert isinstance(moteur.chaine.recherche, Relecture)
    assert creer_moteur("local", relecture=False).chaine.recherche is None
    ecrit = " ".join(m["ortho"] for m in moteur.ecrire("il a ɑ̃.vwa.je se le.tʁ a sɔ̃ fʁɛʁ"))
    assert ecrit.lower() == "il a envoyé ses lettres à son frère"
