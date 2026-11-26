# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Mode API contre un faux serveur local (jamais le vrai) : routes, corps envoyés, lecture des réponses, erreurs."""

from __future__ import annotations

import pytest

import serveur_factice
from lectura_nlp_en import ErreurAPI, QuotaDepasse, Resultat, creer_moteur
from lectura_nlp_en.api import ClientAPI


def test_lire_ecrire_analyser(serveur):
    nlp = creer_moteur("api", api=serveur, formes_fortes=False)
    assert nlp.mode == "api" and nlp.chaine is None
    p = nlp.lire("The kids play", doubles=True)
    assert p[0]["ortho"] == "The kids play"
    chemin, corps, entetes = serveur_factice.APPELS[-1]
    assert chemin == "/v1/lire"
    assert corps == {"texte": "The kids play", "langue": "en", "options": {"formes_fortes": False, "doubles": True}}
    assert entetes["User-Agent"].startswith("lectura-nlp-en/")
    assert "Authorization" not in entetes
    assert nlp.ecrire("ðə ˈkɪdz")[0]["phone"] == "ðə ˈkɪdz"
    assert serveur_factice.APPELS[-1][0] == "/v1/ecrire"
    assert serveur_factice.APPELS[-1][1] == {"phone": "ðə ˈkɪdz", "langue": "en", "options": {"formes_fortes": False}}
    mots = nlp.analyser("She sleeps")[0]
    assert [m["forme"] for m in mots] == ["She", "sleeps"] and mots[0]["lemme"] == "she"


def test_corriger(serveur):
    nlp = creer_moteur("api", api=serveur)
    r = nlp.corriger("He go home", mode="automatique", explications="en")
    assert isinstance(r, Resultat) and r.texte == "He goes home"
    c = r.corrections[0]
    assert (c.original, c.proposition, c.type) == ("go", "goes", "accord")
    assert serveur_factice.APPELS[-1][:2] == ("/v1/corriger", {"texte": "He go home", "langue": "en",
                                                                "mode": "automatique", "explications": "en"})
    nlp.corriger("He go home", langue="en")                    # nom de la 0.3
    assert serveur_factice.APPELS[-1][1]["explications"] == "en"
    nlp.corriger("He go home")
    assert serveur_factice.APPELS[-1][1]["explications"] == "fr"
    with pytest.raises(ValueError):
        nlp.corriger("x", mode="inconnu")


def test_lexique_par_l_api(serveur):
    nlp = creer_moteur("api", api=serveur)
    assert nlp.lexique.mode == "api"
    assert nlp.lexique.frequence("cat") == 4.5
    assert serveur_factice.APPELS[-1][0] == "/v1/lexique/frequence?langue=en"


def test_decouper_reste_local(serveur):
    nlp = creer_moteur("api", api=serveur)
    n = len(serveur_factice.APPELS)
    assert [m["forme"] for m in nlp.decouper("I can't pay $3.50.")[0]][:3] == ["I", "ca", "n't"]
    assert len(serveur_factice.APPELS) == n


def test_erreurs(serveur):
    nlp = creer_moteur("api", api=serveur)
    with pytest.raises(QuotaDepasse) as e:
        nlp.lire("__429__")
    assert e.value.statut == 429 and e.value.attente == 120 and "quota" in str(e.value)
    assert isinstance(e.value, ErreurAPI)
    with pytest.raises(ValueError, match="422"):
        nlp.lire("__422__")
    with pytest.raises(ValueError, match="413"):
        nlp.lire("__413__")
    with pytest.raises(ErreurAPI) as e:
        nlp.ecrire("__503__")
    assert e.value.statut == 503
    with pytest.raises(ValueError, match="options non prises en charge"):
        nlp.lire("hello", liaisons=True)


def test_injoignable():
    client = ClientAPI("http://127.0.0.1:9", delai=2)          # port fermé
    with pytest.raises(ErreurAPI, match="injoignable"):
        client.appeler("lire", {"texte": "a", "langue": "en", "options": {}})


def test_adresse_et_cle(monkeypatch, serveur):
    monkeypatch.setenv("LECTURA_API_URL", serveur + "/")
    monkeypatch.setenv("LECTURA_API_KEY", "cle-de-test")
    nlp = creer_moteur("api")
    assert nlp.client.api == serveur
    assert nlp.lexique.api.startswith(serveur)                 # même adresse pour le lexique
    nlp.lire("a")
    assert serveur_factice.APPELS[-1][2]["Authorization"] == "Bearer cle-de-test"


def test_erreurs_communes_avec_lexicon():
    import lectura_lexicon

    assert QuotaDepasse is lectura_lexicon.QuotaDepasse and ErreurAPI is lectura_lexicon.ErreurAPI
