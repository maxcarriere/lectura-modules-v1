# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Chaîne complète en mode local (5 tests repris de lectura-translator 0.1.2) : sautés sans modèles."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import traducteur_local

NB = " "


def test_traduction_formules():
    t = traducteur_local("en", "fr")
    r = t.traduire("He paid $3.50 at 5 p.m. on March 3, 2024.")["texte"]
    assert f"3,50{NB}$" in r and f"17{NB}h" in r and "le 3 mars 2024" in r


def test_alignement():
    t = traducteur_local("en", "fr")
    liens = t.aligner(["She", "left", "the", "bank", "."], ["Elle", "a", "quitté", "la", "banque", "."])
    assert (3, 4) in liens and (0, 0) in liens


def test_positions_des_phrases():
    t = traducteur_local("fr", "en")
    texte = "Il pleut. Elle chante !"
    r = t.traduire(texte)
    assert [texte[p["debut"]:p["fin"]] for p in r["phrases"]] == ["Il pleut.", "Elle chante !"]


def _gloser(t, texte):
    try:
        return t.gloser(texte)
    except (FileNotFoundError, ImportError) as e:
        pytest.skip(str(e))


def test_glossaire_formules_et_gloses():
    """Formule : pas de sens (5 p.m. n'est pas « cinq ») ; sens reconnu par sa glose seulement : pas de traductions
    qui contrediraient la phrase."""
    t = traducteur_local("en", "fr")
    mots = {e["forme"]: e for ph in _gloser(t, "She left at 5 p.m. He gave up smoking.") for e in ph["mots"]}
    assert mots["5 p.m."]["choix"] == "formule" and mots["5 p.m."]["sens"] is None
    s = mots["smoking"]
    assert s["choix"] != "glose" or s["sens"]["traductions"] == []


def test_glossaire_autre_fil():
    """Un serveur appelle gloser depuis son pool de fils : le traducteur créé dans un fil doit marcher dans un autre."""
    t = traducteur_local("en", "fr")
    _gloser(t, "He gave up smoking.")
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(t.gloser, "She left the bank.").result()


def test_glossaire_francais():
    """Glossaire fr → en : l'Analyseur français (local) donne lemme et catégorie de chaque mot."""
    t = traducteur_local("fr", "en")
    ph = _gloser(t, "Il a arrêté de fumer.")[0]
    mots = {e["forme"]: e for e in ph["mots"]}
    assert ph["traduction"] and mots["fumer"]["lemme"] == "fumer" and mots["fumer"]["upos"] == "VERB"
    assert mots["arrêté"]["lemme"] == "arrêter"
