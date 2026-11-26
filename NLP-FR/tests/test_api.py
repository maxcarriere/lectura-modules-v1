# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Mode API contre un faux serveur local (jamais le vrai) : routes, corps envoyés, lecture des réponses, erreurs."""

from __future__ import annotations

import pytest

import serveur_factice
from lectura_nlp_fr import ErreurAPI, QuotaDepasse, Resultat, creer_moteur
from lectura_nlp_fr.api import ClientAPI


def test_lire_ecrire_analyser(serveur):
    nlp = creer_moteur("api", api=serveur, liaisons=True)
    assert nlp.mode == "api"
    p = nlp.lire("Les enfants jouent", x_entier=True)
    assert p[0]["ortho"] == "Les enfants jouent"
    chemin, corps, entetes = serveur_factice.APPELS[-1]
    assert chemin == "/v1/lire"
    assert corps == {"texte": "Les enfants jouent", "langue": "fr", "options": {"liaisons": True, "x_entier": True}}
    assert entetes["User-Agent"].startswith("lectura-nlp-fr/")
    assert "Authorization" not in entetes
    assert nlp.ecrire("le.z‿ɑ̃.fɑ̃", formules=False)[0]["phone"] == "le.z‿ɑ̃.fɑ̃"
    assert serveur_factice.APPELS[-1][0] == "/v1/ecrire"
    assert serveur_factice.APPELS[-1][1]["options"] == {"liaisons": True, "formules": False}
    mots = nlp.analyser("Il dort")[0]
    assert [m["forme"] for m in mots] == ["Il", "dort"] and mots[0]["lemme"] == "il"


def test_corriger(serveur):
    nlp = creer_moteur("api", api=serveur)
    r = nlp.corriger("Les enfant dorment", mode="automatique")
    assert isinstance(r, Resultat) and r.texte == "Les enfants dorment"
    c = r.corrections[0]
    assert (c.original, c.proposition, c.type, c.explication) == ("enfant", "enfants", "accord", "Après « Les », pluriel.")
    assert serveur_factice.APPELS[-1][:2] == ("/v1/corriger", {"texte": "Les enfant dorment", "langue": "fr",
                                                                "mode": "automatique", "explications": "fr"})
    with pytest.raises(ValueError):
        nlp.corriger("x", mode="inconnu")


def test_lexique_par_l_api(serveur):
    nlp = creer_moteur("api", api=serveur)
    assert nlp.lexique.mode == "api"
    assert nlp.lexique.frequence("chat") == 4.5
    assert serveur_factice.APPELS[-1][0] == "/v1/lexique/frequence?langue=fr"


def test_decouper_reste_local(serveur):
    nlp = creer_moteur("api", api=serveur)
    n = len(serveur_factice.APPELS)
    assert [m["forme"] for m in nlp.decouper("Il est 8 h.")[0]][:3] == ["Il", "est", "8 h"]
    assert len(serveur_factice.APPELS) == n


def test_erreurs(serveur):
    nlp = creer_moteur("api", api=serveur)
    with pytest.raises(QuotaDepasse) as e:
        nlp.lire("__429__")
    assert e.value.statut == 429 and e.value.attente == 120 and "quota" in str(e.value)
    assert isinstance(e.value, ErreurAPI)
    with pytest.raises(ValueError, match="422"):
        nlp.lire("__422__")
    with pytest.raises(ErreurAPI) as e:
        nlp.ecrire("__503__")
    assert e.value.statut == 503
    with pytest.raises(ValueError, match="options non prises en charge"):
        nlp.lire("bonjour", inconnue=True)


def test_injoignable():
    client = ClientAPI("http://127.0.0.1:9", delai=2)          # port fermé
    with pytest.raises(ErreurAPI, match="injoignable"):
        client.appeler("lire", {"texte": "a", "langue": "fr", "options": {}})


def test_adresse_et_cle(monkeypatch, serveur):
    monkeypatch.setenv("LECTURA_API_URL", serveur + "/")
    monkeypatch.setenv("LECTURA_API_KEY", "cle-de-test")
    nlp = creer_moteur("api")
    assert nlp.client.api == serveur
    nlp.lire("a")
    assert serveur_factice.APPELS[-1][2]["Authorization"] == "Bearer cle-de-test"


def test_erreurs_communes_avec_lexicon():
    import lectura_lexicon

    assert QuotaDepasse is lectura_lexicon.QuotaDepasse and ErreurAPI is lectura_lexicon.ErreurAPI
