"""Juge des homophones (``juge.py``) branché sur l'écriture."""

import pytest

from lectura_nlp_fr.analyseur.juge import Juge, trouver
from lectura_nlp_fr.analyseur.moteur import dossier_modeles

pytestmark = pytest.mark.skipif(dossier_modeles() is None or trouver(dossier_modeles()) is None,
                                reason="modèles ou juge (facultatif) absents")


def ecrire(moteur, phone):
    return " ".join(m["ortho"] for m in moteur.ecrire(phone)).lower()


def test_branche_par_defaut():
    from lectura_nlp_fr.analyseur import creer_moteur

    assert isinstance(creer_moteur("local").chaine.recherche, Juge)
    assert not isinstance(creer_moteur("local", juge=False).chaine.recherche, Juge)


# Phrases écrites pour ce test, sur le modèle de cas que l'écriture seule rate (« s'était produits », « quelques brasse »,
# « telles sont »).
@pytest.mark.parametrize("phone, attendu", [
    ("il a ɑ̃.vwa.je se le.tʁ a sɔ̃ fʁɛʁ", "il a envoyé ses lettres à son frère"),
    ("de.z‿ɔ.ʁaʒ a.se vjɔ.lɑ̃ s‿e.tɛ pʁɔ.dɥi.", "des orages assez violents s'étaient produits."),
    ("ɛl na.ʒa d‿a.bɔ.ʁ‿a kɛlk bʁas dy bɔʁ.", "elle nagea d'abord à quelques brasses du bord."),
    ("tɛl sɔ̃ le pə.ti de.fo kə ʒə vwa dɑ̃ sə livʁ.", "tels sont les petits défauts que je vois dans ce livre."),
])
def test_homophones(phone, attendu):
    from lectura_nlp_fr.analyseur import creer_moteur

    assert ecrire(creer_moteur("local"), phone) == attendu


def test_interjections_laissees():
    from lectura_nlp_fr.analyseur import creer_moteur

    assert ecrire(creer_moteur("local"), "il a ø vy sɔ̃ fʁɛʁ").split()[2] == "euh"


# Nombres : le juge les reçoit comme « <nombre> », comme à l'entraînement ; sinon « 53 ans » devenait « 53 en »
# (recherche v2, 27/10/2026).
@pytest.mark.parametrize("phone, attendu", [
    ("maʁ.tɛ̃, ka.ʁɑ̃t.sɛ.t‿ɑ̃, a kɔ.mɑ̃.se sɔ̃ tʁa.vaj.", "martin, 47 ans, a commencé son travail."),
    ("i.l‿a sɛ̃.kɑ̃t.tʁwa.z‿ɑ̃.", "il a 53 ans."),
])
def test_nombre_avant_homophone(phone, attendu):
    from lectura_nlp_fr.analyseur import creer_moteur

    assert ecrire(creer_moteur("local"), phone) == attendu
