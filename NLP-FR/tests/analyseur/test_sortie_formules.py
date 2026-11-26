"""Sortie JSON (``vers_dict``) d'une phrase à formules : têtes ramenées aux indices de ``mots``, analyse et phonétique
de la formule (signalé par Site sur lingua, 15/10)."""

import pytest

from lectura_nlp_fr.analyseur.moteur import dossier_modeles

pytestmark = pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")


def _phrase(texte):
    from lectura_nlp_fr.analyseur import creer_moteur

    return creer_moteur("local", relecture=False).lire(texte)[0]


def test_tetes_dans_mots():
    p = _phrase("Le 14 juillet 1789, il a payé 12,50 € à 8h30 le 03/10/2026.")
    formes = [m["forme"] for m in p["mots"]]
    tetes = [m["analyse"]["tete"] for m in p["mots"]]
    assert all(t == -1 or 0 <= t < len(formes) for t in tetes)
    paye = formes.index("payé")
    assert tetes[paye] == -1
    for forme in ("14 juillet 1789", "il", "a", "12,50 €", "8h30", "03/10/2026"):
        assert tetes[formes.index(forme)] == paye, forme
    assert tetes[formes.index("à")] == formes.index("8h30")


def test_formule_analyse_et_phone():
    p = _phrase("Il a payé 12,50 € le 03/10/2026.")
    prix = next(m for m in p["mots"] if m["forme"] == "12,50 €")
    assert prix["formule"] == "monnaie" and prix["analyse"]["lemme"] == "12,50 €"
    assert prix["phone"].startswith("du.z‿ø.ʁo")
    assert all(m["formule"] == "" for m in p["mots"] if not m["lecture"])


def test_ecrire_sans_formules():
    from lectura_nlp_fr.analyseur import creer_moteur

    moteur = creer_moteur("local", relecture=False)
    assert moteur.ecrire("le.z‿ɑ̃.fɑ̃ ɔ̃ ly dø.z‿is.twaʁ")[0]["ortho"] == "Les enfants ont lu 2 histoires"
    assert moteur.ecrire("le.z‿ɑ̃.fɑ̃ ɔ̃ ly dø.z‿is.twaʁ", formules=False)[0]["ortho"] == "Les enfants ont lu deux histoires"


@pytest.mark.parametrize("texte, attendu", [
    ("bien avant les autres.", "LIA"),        # composé du lexique : liaison interne (signalé par Site, 15/10)
    ("tout à fait", "LIA"),
    ("pour autant", "ENC"),
    ("les amis", "LIA"),                      # deux mots : jonction de la chaîne
])
def test_jonction_interne_des_composes(texte, attendu):
    colonnes = _phrase(texte)["lineaire"]
    assert [c[2] for c in colonnes if c[0] == " " and c[1] == "‿"][0] == attendu
