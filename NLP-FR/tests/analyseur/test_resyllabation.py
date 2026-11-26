"""Composés à espace élidés dans la phrase : la consonne élidée ouvre la syllabe du mot suivant."""

import pytest

from lectura_nlp_fr.analyseur.moteur import dossier_modeles


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
@pytest.mark.parametrize("texte, attendu", [
    ("Bien qu'il soit là.", "bjɛ̃.k‿il swa la."),
    ("Alors qu'on dormait.", "a.lɔʁ.k‿ɔ̃ dɔʁ.mɛ."),
    ("Pendant qu'il mange.", "pɑ̃.dɑ̃.k‿il mɑ̃ʒ."),
    ("Parce qu'il pleut.", "paʁs‿k‿il plø."),          # groupe « sk » en attaque : gardé
    ("Il faut qu'il parte.", "il fo k‿il paʁt."),
])
def test_compose_elide(texte, attendu):
    from lectura_nlp_fr.analyseur import creer_moteur

    phrase = creer_moteur("local", relecture=False).lire(texte)[0]
    assert phrase["phone"] == attendu
    assert phrase["ortho"] == texte
