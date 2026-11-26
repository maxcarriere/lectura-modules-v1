# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Modes local, API et auto : local sans aucun appel réseau, API contre le faux serveur, avertissement en auto."""
import warnings

import pytest

import serveur_factice
from conftest import lancer, traducteur_local
from lectura_traducteur import (ErreurAPI, ModelesAbsents, QuotaDepasse, Traducteur, TraducteurAPI, choisir_mode,
                                creer_moteur)
from lectura_traducteur.api import morceaux

# ── Choix du mode ────────────────────────────────────────────────────────────────────────────────────────────


def test_choix_du_mode_sans_modeles(sans_modeles, reseau_coupe):
    assert choisir_mode("en", "fr")[0] == "api"
    assert choisir_mode("en", "fr", models_dir=sans_modeles)[0] == "local"
    assert choisir_mode("en", "fr", api="http://127.0.0.1:9")[0] == "api"
    assert choisir_mode("en", "fr", mode="local")[0] == "local"
    assert reseau_coupe == []


def test_mode_par_variable(sans_modeles, monkeypatch):
    monkeypatch.setenv("LECTURA_TRADUCTEUR_MODE", "local")
    assert choisir_mode("fr", "en")[0] == "local"
    with pytest.raises(ModelesAbsents):
        Traducteur("fr", "en")
    monkeypatch.setenv("LECTURA_TRADUCTEUR_MODE", "nimporte")
    with pytest.raises(ValueError):
        Traducteur("fr", "en")


def test_paire_inconnue(sans_modeles):
    with pytest.raises(ValueError):
        Traducteur("fr", "fr", mode="api")
    with pytest.raises(ValueError):
        Traducteur("de", "en", mode="api")


def test_auto_sans_modeles_passe_a_l_api_avec_avertissement(sans_modeles, reseau_coupe):
    with pytest.warns(UserWarning, match="envoyés"):
        t = Traducteur("en", "fr")
    assert isinstance(t, TraducteurAPI) and t.mode == "api"
    assert "absents" in t.raison_mode
    assert reseau_coupe == []          # aucune connexion avant le premier appel


def test_api_explicite_sans_avertissement(sans_modeles):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        t = Traducteur("en", "fr", mode="api")
    assert t.mode == "api"


# ── Mode local : jamais de réseau ────────────────────────────────────────────────────────────────────────────


def test_local_sans_modeles_erreur_claire_sans_reseau(sans_modeles, reseau_coupe):
    with pytest.raises(ModelesAbsents, match="mode=\"api\""):
        Traducteur("en", "fr", mode="local")
    with pytest.raises(ModelesAbsents):
        Traducteur("en", "fr", models_dir=sans_modeles)
    assert reseau_coupe == []


def test_local_refuse_une_adresse_d_api(sans_modeles):
    with pytest.raises(ValueError):
        Traducteur("en", "fr", mode="local", api="http://127.0.0.1:9")


def test_local_avec_modeles_hors_reseau(reseau_coupe):
    """Traduire, aligner et gloser en local, toute connexion interdite (modèles requis, sinon sauté)."""
    t = traducteur_local("en", "fr")
    r = t.traduire("She left the bank at 5 p.m.", aligner=True)
    assert r["phrases"][0]["liens"]
    assert t.aligner(["She", "left"], ["Elle", "est", "partie"])
    try:
        t.gloser("He gave up smoking.")
    except (FileNotFoundError, ImportError) as e:
        pytest.skip(str(e))
    assert reseau_coupe == []


# ── Mode API, contre le faux serveur ─────────────────────────────────────────────────────────────────────────


def test_api_traduire(serveur):
    t = Traducteur("en", "fr", mode="api", api=serveur)
    texte = "She left. He stayed!"
    r = t.traduire(texte)
    assert r["texte"] == "[fr] She left. [fr] He stayed!"
    assert [texte[p["debut"]:p["fin"]] for p in r["phrases"]] == ["She left.", "He stayed!"]
    chemin, corps = serveur_factice.APPELS[-1]
    assert chemin == "/v1/traduire"
    assert corps == {"texte": texte, "source": "en", "cible": "fr", "options": {"aligner": False, "formules": True}}


def test_api_traduire_aligne(serveur):
    r = Traducteur("fr", "en", mode="api", api=serveur).traduire("Il pleut fort.", aligner=True)
    p = r["phrases"][0]
    assert p["liens"] == [(0, 0), (1, 1), (2, 2)] and all(isinstance(l, tuple) for l in p["liens"])
    assert serveur_factice.UNITES[-1] == 2 * len("Il pleut fort.")


def test_api_aligner_et_gloser(serveur):
    t = Traducteur("en", "fr", mode="api", api=serveur)
    assert t.aligner(["She", "left"], ["Elle", "est", "partie"]) == {(0, 0), (1, 1)}
    assert serveur_factice.APPELS[-1][0] == "/v1/traduire/aligner"
    g = t.gloser("He gave up smoking.")
    assert g[0]["traduction"].startswith("[fr]") and [m["forme"] for m in g[0]["mots"]][:2] == ["He", "gave"]
    assert serveur_factice.APPELS[-1] == ("/v1/traduire/gloser", {"texte": "He gave up smoking.", "source": "en"})


def test_api_infos(serveur):
    i = Traducteur("en", "fr", mode="api", api=serveur).infos()
    assert i["mode"] == "api" and i["limites"]["texte_max"] == 2000 and "en-fr" in i["paires"]


def test_api_texte_vide_ne_part_pas(serveur):
    n = len(serveur_factice.APPELS)
    t = Traducteur("en", "fr", mode="api", api=serveur)
    assert t.traduire("   ") == {"texte": "", "phrases": []}
    assert t.gloser("") == [] and t.aligner([], ["x"]) == set()
    assert len(serveur_factice.APPELS) == n


def test_api_texte_long_decoupe(serveur):
    """Un texte plus long que la limite part en plusieurs requêtes ; les positions restent celles du texte entier."""
    texte = " ".join(f"Sentence number {i} is here." for i in range(150))      # ≈ 4 300 caractères
    n = len(serveur_factice.APPELS)
    r = Traducteur("en", "fr", mode="api", api=serveur).traduire(texte)
    envois = serveur_factice.APPELS[n:]
    assert len(envois) >= 3 and all(len(c["texte"]) <= 2000 for _, c in envois)
    assert len(r["phrases"]) == 150
    assert all(texte[p["debut"]:p["fin"]] == p["source"] for p in r["phrases"])


def test_morceaux_couvrent_le_texte():
    texte = "Un. " * 700 + "x" * 2500
    m = morceaux(texte, 2000)
    assert "".join(t for _, t in m) == texte and all(len(t) <= 2000 for _, t in m)
    assert all(texte[d:d + len(t)] == t for d, t in m)


def test_api_erreurs(serveur, monkeypatch):
    t = Traducteur("en", "fr", mode="api", api=serveur, taille="big")
    with pytest.raises(ValueError, match="422"):
        t.traduire("Hello.")
    t = Traducteur("en", "fr", mode="api", api=serveur)
    with pytest.raises(ValueError, match="422"):
        t.aligner(["a"] * 10, ["b" * 300])          # mot de plus de 200 caractères
    with pytest.raises(ValueError, match="200 mots"):
        t.aligner(["a"] * 201, ["b"])               # refusé avant l'envoi
    import urllib.request
    ouvrir = urllib.request.urlopen

    def avec_quota(requete, *a, **k):
        requete.add_header("X-Test-Quota", "1")
        return ouvrir(requete, *a, **k)

    monkeypatch.setattr(urllib.request, "urlopen", avec_quota)
    with pytest.raises(QuotaDepasse) as e:
        t.traduire("Hello.")
    assert e.value.statut == 429 and e.value.attente == 3600


def test_memes_erreurs_que_lexicon():
    """Une seule classe à attraper pour tous les modules v1 (si lectura-lexicon est installé)."""
    lexicon = pytest.importorskip("lectura_lexicon.api")
    if not hasattr(lexicon, "QuotaDepasse"):
        pytest.skip("ancien lectura-lexicon (0.x)")
    assert QuotaDepasse is lexicon.QuotaDepasse and ErreurAPI is lexicon.ErreurAPI


def test_api_injoignable(sans_modeles):
    t = Traducteur("en", "fr", mode="api", api="http://127.0.0.1:9", delai=2)
    with pytest.raises(ErreurAPI, match="injoignable"):
        t.traduire("Hello.")


@pytest.mark.parametrize("variable", ["LECTURA_TRADUCTEUR_API", "LECTURA_API_URL"])
def test_adresse_par_variable(sans_modeles, monkeypatch, serveur, variable):
    monkeypatch.setenv(variable, serveur)
    t = Traducteur("en", "fr", mode="api")
    assert t.api == serveur and t.traduire("Hi.")["texte"] == "[fr] Hi."


def test_creer_moteur_ancien_nom(sans_modeles, serveur):
    t = creer_moteur("en", "fr", mode="api", api=serveur)
    assert isinstance(t, TraducteurAPI) and t.taille == "base"


# ── API = local (contrôle d'identité, modèles requis) ────────────────────────────────────────────────────────


def test_api_egale_local():
    en_fr, fr_en = traducteur_local("en", "fr"), traducteur_local("fr", "en")
    srv, url = lancer({("en", "fr"): en_fr, ("fr", "en"): fr_en})
    try:
        api = Traducteur("en", "fr", mode="api", api=url)
        texte = "She left the bank at 5 p.m. on March 3, 2024. He paid $3.50."
        assert api.traduire(texte, aligner=True) == en_fr.traduire(texte, aligner=True)
        assert api.aligner(["She", "left"], ["Elle", "est", "partie"]) == en_fr.aligner(["She", "left"],
                                                                                         ["Elle", "est", "partie"])
        assert Traducteur("fr", "en", mode="api", api=url).traduire("Il pleut. Elle chante !") == \
            fr_en.traduire("Il pleut. Elle chante !")
    finally:
        srv.shutdown()
