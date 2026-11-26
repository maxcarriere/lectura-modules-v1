# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Modes local, dégradé et auto : jamais d'appel réseau en local ni en dégradé ; jamais de repli ni de juge absent en
silence. Les tests marqués « modèles » demandent les modèles de l'Analyseur (``LECTURA_NLP_FR_DIR``…)."""

from __future__ import annotations

import os
import warnings

import pytest

from lectura_nlp_fr import (
    AvertissementNLP, FonctionIndisponible, Indisponible, LexiqueIndisponible, ModelesAbsents, MoteurNLPAPI,
    creer_moteur,
)
from lectura_nlp_fr.analyseur.moteur import dossier_modeles

MODELES = dossier_modeles()
avec_modeles = pytest.mark.skipif(MODELES is None, reason="modèles de l'Analyseur absents")


def _avec_base() -> bool:
    try:
        from lectura_lexicon import Lexicon

        Lexicon(mode="local")
        return True
    except FileNotFoundError:
        return False


# ── sans modèles ────────────────────────────────────────────────────────────────────────────────────────────────

def test_local_sans_modeles_erreur_claire(sans_modeles, sans_reseau):
    with pytest.raises(ModelesAbsents, match="Modèles de l'Analyseur introuvables"):
        creer_moteur("local")
    with pytest.raises(ModelesAbsents, match="manquent : analyseur.onnx"):
        creer_moteur("local", models_dir=sans_modeles)
    with pytest.raises(ModelesAbsents):
        creer_moteur("degrade")
    assert sans_reseau == []


def test_auto_sans_modeles_passe_a_l_api_et_le_dit(sans_modeles, sans_reseau):
    with pytest.warns(AvertissementNLP, match="passage à l'API"):
        nlp = creer_moteur()                                       # aucune requête à la création
    assert isinstance(nlp, MoteurNLPAPI) and nlp.mode == "api"
    assert sans_reseau == []


def test_ancienne_entree_de_l_analyseur(sans_modeles, sans_reseau):
    from lectura_nlp_fr.analyseur import creer_moteur as ancien

    with pytest.raises(ModelesAbsents):
        ancien("local")
    with pytest.warns(AvertissementNLP, match="passage à l'API"):
        assert ancien("auto").mode == "api"


def test_decouper_sans_modele(sans_modeles, sans_reseau):
    nlp = creer_moteur("api")
    phrases = nlp.decouper("Le 14 juillet, il a payé 12,50 €. Puis il est parti.")
    assert len(phrases) == 2 and sans_reseau == []


def test_mode_inconnu():
    with pytest.raises(ValueError, match="mode"):
        creer_moteur("hors_ligne")


def test_lexique_indisponible():
    lex = LexiqueIndisponible("test")
    with pytest.warns(AvertissementNLP, match="lexique indisponible"):
        r = lex.homophones("vɛʁ")
    assert isinstance(r, Indisponible) and not r and len(r) == 0 and list(r) == []
    assert str(r).startswith("lexique indisponible : installer une base ou autoriser l'API")
    assert not lex and lex.disponible is False
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        lex.rimes("chat")                                         # un seul avertissement


# ── avec les modèles ────────────────────────────────────────────────────────────────────────────────────────────

@avec_modeles
def test_local_hors_reseau(sans_reseau):
    nlp = creer_moteur("local")
    assert nlp.mode == "local"
    p = nlp.lire("Les petits enfants sont arrivés.")[0]
    assert p["phone"] == "le pə.ti.z‿ɑ̃.fɑ̃ sɔ̃.t‿a.ʁi.ve."
    assert nlp.ecrire("le pə.ti.z‿ɑ̃.fɑ̃")[0]["ortho"] == "Les petits enfants"
    mots = nlp.analyser("Il mange une pomme.")[0]
    assert (mots[1]["forme"], mots[1]["upos"], mots[1]["lemme"]) == ("mange", "VERB", "manger")
    nlp.lexique.validite("chat")
    assert sans_reseau == []


@avec_modeles
def test_local_sans_base_jamais_d_api(monkeypatch, sans_reseau, maison_vide):
    monkeypatch.delenv("LECTURA_LEXICON_DATA", raising=False)
    monkeypatch.setenv("LECTURA_LEXICON_MODE", "api")              # même forcé ailleurs : le local choisi l'emporte
    with pytest.warns(AvertissementNLP, match="jamais d'API"):
        nlp = creer_moteur("local", models_dir=MODELES)
    assert isinstance(nlp.lexique, LexiqueIndisponible)
    with pytest.warns(AvertissementNLP):
        assert not nlp.lexique.homophones("vɛʁ")
    with pytest.raises(FonctionIndisponible):
        nlp.corriger("Les enfant dorment.")
    assert sans_reseau == []


@avec_modeles
def test_degrade(sans_reseau):
    nlp = creer_moteur("degrade")
    assert nlp.mode == "degrade" and isinstance(nlp.lexique, LexiqueIndisponible)
    assert nlp.ecriture_lexique is False
    assert nlp.ecrire("le pə.ti.z‿ɑ̃.fɑ̃")[0]["ortho"] == "Les petits enfants"
    assert nlp.lire("Il dort.")[0]["phone"] == "il dɔʁ."
    with pytest.warns(AvertissementNLP):
        r = nlp.lexique.rimes("chat")
    assert not r
    with pytest.raises(FonctionIndisponible, match="dégradé"):
        nlp.corriger("Les enfant dorment.")
    with pytest.raises(FonctionIndisponible):
        creer_moteur("degrade", ecriture_lexique=True)
    assert sans_reseau == []


@avec_modeles
def test_juge_absent_jamais_en_silence(monkeypatch, maison_vide):
    from lectura_nlp_fr.analyseur import moteur

    monkeypatch.delenv("LECTURA_JUGE_DIR", raising=False)
    monkeypatch.setattr(moteur, "_JUGES", {})
    if (MODELES / "juge").exists():
        pytest.skip("un juge est posé dans le dossier des modèles")
    with pytest.warns(AvertissementNLP, match="SANS juge"):
        nlp = creer_moteur("degrade", models_dir=MODELES)
    assert nlp.etat()["juge_ecriture_sha256"] is None


@avec_modeles
@pytest.mark.skipif(not os.environ.get("LECTURA_JUGE_DIR"), reason="LECTURA_JUGE_DIR non posé")
def test_juge_de_l_ecriture_charge():
    nlp = creer_moteur("degrade")
    print(f"\njuge de l'écriture : sha256 {nlp.etat()['juge_ecriture_sha256']}")
    assert nlp.etat()["juge_ecriture_sha256"]


@avec_modeles
def test_auto_avec_modeles_sans_base_lexique_par_l_api(monkeypatch, maison_vide, sans_reseau):
    monkeypatch.delenv("LECTURA_LEXICON_DATA", raising=False)
    monkeypatch.delenv("LECTURA_LEXICON_MODE", raising=False)
    with pytest.warns(AvertissementNLP, match="passent par l'API"):
        nlp = creer_moteur("auto", models_dir=MODELES)
    assert nlp.mode == "local" and nlp.lexique.mode == "api"
    assert sans_reseau == []                                       # rien n'est parti à la création


@avec_modeles
@pytest.mark.skipif(not _avec_base(), reason="base Lexicon locale absente")
def test_etat_local():
    nlp = creer_moteur("local")
    e = nlp.etat()
    assert e["mode"] == "local" and e["lexique"]["mode"] == "local" and e["ecriture_lexique"] is False
    assert creer_moteur("local", ecriture_lexique="auto").etat()["ecriture_lexique"] is True
    assert e["version"] == "2.0.0"


@avec_modeles
def test_lecture_seule_sans_avertissement_d_ecriture(sans_reseau):
    from lectura_nlp_fr.analyseur import moteur

    with warnings.catch_warnings():
        warnings.simplefilter("error", AvertissementNLP)
        nlp = creer_moteur("degrade", ecriture=False)
        ancien = moteur.creer_moteur("local", ecriture=False)
    assert nlp.lire("Il dort.")[0]["phone"] == "il dɔʁ."
    assert ancien.lire("Il dort.")[0]["phone"] == "il dɔʁ."
    assert nlp.etat()["juge_ecriture_sha256"] is None
    with pytest.raises(FonctionIndisponible, match="lecture seule"):
        nlp.ecrire("il dɔʁ")
    assert sans_reseau == []
