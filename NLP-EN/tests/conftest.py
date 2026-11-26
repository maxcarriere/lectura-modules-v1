# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Outils communs des tests : garde « réseau interdit », faux serveur d'API local, environnement sans modèles."""

from __future__ import annotations

import os
import socket
import threading
from pathlib import Path

import pytest

# Cache de décompression des modèles, relevé avant qu'un test ne change HOME.
CACHE = os.environ.get("LECTURA_CACHE_DIR") or str(Path.home() / ".lectura" / "cache")


class AppelReseau(AssertionError):
    """Un appel réseau a été tenté là où il est interdit."""


@pytest.fixture
def sans_reseau(monkeypatch):
    """Toute connexion, toute résolution de nom lève ``AppelReseau`` (garde du mode local)."""
    tentatives = []

    def interdit(*args, **kwargs):
        tentatives.append(args)
        raise AppelReseau(f"appel réseau interdit : {args[:2]}")

    monkeypatch.setattr(socket.socket, "connect", interdit)
    monkeypatch.setattr(socket.socket, "connect_ex", interdit)
    monkeypatch.setattr(socket, "create_connection", interdit)
    monkeypatch.setattr(socket, "getaddrinfo", interdit)
    return tentatives


@pytest.fixture
def maison_vide(monkeypatch, tmp_path):
    """HOME vide (rien dans ~/.lectura/models), cache des modèles gardé, LECTURA_MODELS_DIR retiré."""
    monkeypatch.delenv("LECTURA_MODELS_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LECTURA_CACHE_DIR", CACHE)
    return tmp_path


@pytest.fixture
def sans_modeles(monkeypatch, tmp_path):
    """Environnement où aucun modèle ni aucune base n'est trouvé (HOME vide, variables retirées)."""
    for v in ("LECTURA_NLP_EN_DIR", "LECTURA_MODELS_DIR", "LECTURA_CORRECTEUR_EN_DIR", "LECTURA_LEXICON_EN_DATA",
              "LECTURA_LEXICON_MODE", "LECTURA_API_URL", "LECTURA_LEXICON_API", "LECTURA_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LECTURA_CACHE_DIR", CACHE)
    return tmp_path


@pytest.fixture
def serveur():
    yield from _serveur(None)


@pytest.fixture(scope="module")
def serveur_local():
    """Faux serveur qui calcule lire / écrire avec l'Analyseur local (modèles requis) : contrôle « API = local »."""
    from lectura_nlp_en.analyseur.moteur import MoteurLocal, dossier_modeles

    dossier = dossier_modeles()
    if dossier is None:
        pytest.skip("modèles de l'Analyseur anglais absents")
    yield from _serveur(MoteurLocal(dossier))


def _serveur(moteur):
    import serveur_factice

    serveur_factice.APPELS.clear()
    srv, url = serveur_factice.demarrer(moteur=moteur)
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    yield url
    srv.shutdown()
    srv.server_close()


# Petite base Lexicon anglaise, écrite pour les tests (mots courants et un mot inventé, « zorbex ») : aucune donnée
# livrée. ortho, phone, lemme, upos, feats, fréquence par million.
MOTS_EN = [
    ("cat", "ˈkæt", "cat", "NOUN", "Number=Sing", 80.0),
    ("cats", "ˈkæts", "cat", "NOUN", "Number=Plur", 20.0),
    ("hat", "ˈhæt", "hat", "NOUN", "Number=Sing", 40.0),
    ("their", "ðɛɹ", "they", "PRON", "Number=Plur|Person=3|Poss=Yes", 900.0),
    ("there", "ðɛɹ", "there", "ADV", "", 1200.0),
    ("eat", "ˈit", "eat", "VERB", "VerbForm=Inf", 90.0),
    ("ate", "ˈeɪt", "eat", "VERB", "Mood=Ind|Tense=Past|VerbForm=Fin", 30.0),
    ("eight", "ˈeɪt", "eight", "NUM", "", 70.0),
    ("zorbex", "ˈzɔɹ.bɛks", "zorbex", "NOUN", "Number=Sing", 5.0),
]


@pytest.fixture(scope="session")
def base_en(tmp_path_factory):
    from lectura_lexicon import convertir

    d = tmp_path_factory.mktemp("lexicon_en")
    tsv = d / "mots.tsv"
    lignes = ["\t".join(("ortho", "phone", "lemme", "upos", "feats", "freq"))]
    lignes += ["\t".join((o, p, l, u, f, str(q))) for o, p, l, u, f, q in MOTS_EN]
    tsv.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return convertir(tsv, d / "base" / "lexicon.db", langue="en")


def modeles_presents() -> bool:
    from lectura_nlp_en.analyseur.moteur import dossier_modeles

    return dossier_modeles() is not None


avec_modeles = pytest.mark.skipif(not modeles_presents(), reason="modèles de l'Analyseur anglais absents")
