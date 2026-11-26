# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Les quatre modes : local (jamais de réseau), dégradé, API, auto (qui le dit). Les tests qui demandent les modèles
sont sautés s'ils manquent (``LECTURA_NLP_EN_DIR``, ``LECTURA_CORRECTEUR_EN_DIR``, ``LECTURA_LEXICON_EN_DATA``)."""

from __future__ import annotations

import importlib.util
import warnings

import pytest

from conftest import avec_modeles
from lectura_nlp_en import (AvertissementNLP, FonctionIndisponible, Indisponible, LexiqueIndisponible, ModelesAbsents,
                            creer_moteur)

# ── Sans modèles ──────────────────────────────────────────────────────────────


def test_local_sans_modeles_erreur_claire(sans_modeles, sans_reseau):
    with pytest.raises(ModelesAbsents, match="introuvables.*aucun modèle"):
        creer_moteur("local")
    with pytest.raises(ModelesAbsents):
        creer_moteur("degrade")
    assert sans_reseau == []


def test_auto_sans_modeles_passe_a_l_api_et_le_dit(sans_modeles, sans_reseau):
    with pytest.warns(AvertissementNLP, match="API publique"):
        nlp = creer_moteur()
    assert nlp.mode == "api" and nlp.demande == "auto"
    assert nlp.lexique.mode == "api" and nlp.etat()["correcteur"]["mode"] == "api"
    assert sans_reseau == []                                  # aucune connexion avant le premier appel


def test_ancienne_entree_de_l_analyseur(sans_modeles, sans_reseau):
    from lectura_nlp_en.analyseur import creer_moteur as ancien

    with pytest.raises(ModelesAbsents):
        ancien("local")
    with pytest.warns(AvertissementNLP):
        assert ancien().mode == "api"
    with pytest.raises(ValueError):
        ancien("dev")                                         # mode de développement retiré


def test_decouper_sans_modele(sans_modeles, sans_reseau):
    from lectura_nlp_en.analyseur import decouper

    assert [m.forme for m in decouper("Mr. Smith paid $5.")[0]] == ["Mr.", "Smith", "paid", "$5", "."]


def test_mode_inconnu():
    with pytest.raises(ValueError, match="mode"):
        creer_moteur("hors_ligne")


def test_lexique_indisponible():
    lex = LexiqueIndisponible("essai")
    assert not lex and lex.disponible is False
    with pytest.warns(AvertissementNLP, match="lexique indisponible"):
        r = lex.homophones("ðɛɹ")
    assert isinstance(r, Indisponible) and not r and list(r) == [] and len(r) == 0
    assert str(r).startswith("lexique indisponible : installer une base ou autoriser l'API")
    with warnings.catch_warnings():
        warnings.simplefilter("error")                        # un seul avertissement
        lex.frequence("cat")


# ── Avec les modèles de l'Analyseur ───────────────────────────────────────────


@avec_modeles
def test_local_hors_reseau(sans_reseau, base_en):
    nlp = creer_moteur("local", lexique=base_en)
    assert nlp.mode == "local" and nlp.lexique.mode == "local" and nlp.ecriture_lexique
    p = nlp.lire("I read the book.")[0]
    assert p["phone"].startswith("aɪ ")
    assert nlp.ecrire(p["phone"])[0]["ortho"] == "I read the book."
    mots = nlp.analyser("She left.")[0]
    assert [m["upos"] for m in mots] == ["PRON", "VERB", "PUNCT"]
    assert nlp.lexique.homophones("ðɛɹ")
    # mot inventé, inconnu de l'embarqué : écrit grâce à la base Lexicon branchée sur l'écriture
    assert nlp.ecrire("ðə ˈzɔɹ.bɛks")[0]["ortho"].lower() == "the zorbex"
    assert sans_reseau == []


@avec_modeles
def test_local_sans_base_jamais_d_api(monkeypatch, sans_reseau, maison_vide):
    monkeypatch.delenv("LECTURA_LEXICON_EN_DATA", raising=False)
    monkeypatch.delenv("LECTURA_LEXICON_MODE", raising=False)
    with pytest.warns(AvertissementNLP, match="jamais d'API"):
        nlp = creer_moteur("local")
    assert isinstance(nlp.lexique, LexiqueIndisponible) and not nlp.ecriture_lexique
    with pytest.warns(AvertissementNLP):
        assert not nlp.lexique.rimes("cat")
    assert nlp.lire("Hello there.")[0]["phone"]
    with pytest.raises(FonctionIndisponible):
        nlp.corriger("He go home.")
    assert nlp.etat()["correcteur"]["mode"] == "indisponible"
    assert sans_reseau == []


@avec_modeles
def test_degrade(sans_reseau, base_en):
    nlp = creer_moteur("degrade")
    assert nlp.mode == "degrade" and isinstance(nlp.lexique, LexiqueIndisponible) and not nlp.ecriture_lexique
    assert nlp.lire("I read the book.")[0]["phone"].startswith("aɪ ")
    with pytest.raises(FonctionIndisponible, match="dégradé"):
        nlp.corriger("He go home.")
    # en dégradé, une base donnée n'est pas lue
    assert creer_moteur("degrade", lexique=base_en).lexique.mode == "indisponible"
    assert sans_reseau == []


@avec_modeles
def test_auto_avec_modeles_sans_base_lexique_par_l_api(monkeypatch, maison_vide, sans_reseau):
    monkeypatch.delenv("LECTURA_LEXICON_EN_DATA", raising=False)
    monkeypatch.delenv("LECTURA_LEXICON_MODE", raising=False)
    with pytest.warns(AvertissementNLP, match="Lexicon anglais"):
        nlp = creer_moteur("auto")
    assert nlp.mode == "local" and nlp.lexique.mode == "api" and not nlp.ecriture_lexique
    assert nlp.etat()["correcteur"]["mode"] == "api"
    assert sans_reseau == []


@avec_modeles
def test_etat_local(base_en):
    e = creer_moteur("local", lexique=base_en).etat()
    assert e["langue"] == "en" and e["version"] == "1.0.0" and e["mode"] == "local"
    assert e["analyseur"]["mode"] == "local" and e["analyseur"]["dossier"]
    assert e["lexique"]["mode"] == "local" and e["lexique"]["base"] and e["ecriture_lexique"] is True


@avec_modeles
def test_api_egale_local(serveur_local, base_en):
    """Contrôle d'identité : le client API, servi par l'Analyseur local, rend exactement la sortie locale."""
    local = creer_moteur("local", lexique=False)
    api = creer_moteur("api", api=serveur_local, lexique=False)
    for texte in ("The children arrived at school on March 5, 2020.", "Their house is over there."):
        assert api.lire(texte) == local.lire(texte)
        assert api.ecrire(local.lire(texte)[0]["phone"]) == local.ecrire(local.lire(texte)[0]["phone"])


# ── Correcteur local (modèles du Correcteur et base Lexicon standard) ─────────


def _correcteur_present() -> bool:
    from lectura_nlp_en.correcteur import dossier_modeles

    return importlib.util.find_spec("kenlm") is not None and dossier_modeles() is not None


@avec_modeles
@pytest.mark.skipif(not _correcteur_present(), reason="modèles du Correcteur ou kenlm absents")
def test_correcteur_local_hors_reseau(sans_reseau):
    try:
        nlp = creer_moteur("local")
    except Exception as e:                                    # pragma: no cover
        pytest.skip(str(e))
    if nlp.lexique.mode != "local":
        pytest.skip("base Lexicon anglaise absente (LECTURA_LEXICON_EN_DATA)")
    r = nlp.corriger("i dont think he go to school.", mode="automatique")
    assert r.texte == "I don't think he goes to school."
    assert nlp.correcteur.chaine is nlp.chaine                # la chaîne de l'Analyseur est réutilisée
    r = nlp.corriger("He go to school.", explications="en")
    assert "third person" in r.corrections[0].explication
    assert sans_reseau == []
