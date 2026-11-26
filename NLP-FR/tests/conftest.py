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
    for v in ("LECTURA_NLP_FR_DIR", "LECTURA_MODELS_DIR", "LECTURA_JUGE_DIR", "LECTURA_CORRECTEUR_DIR",
              "LECTURA_JUGE_CORRECTEUR_DIR", "LECTURA_LEXICON_DATA", "LECTURA_LEXICON_MODE", "LECTURA_API_URL",
              "LECTURA_LEXICON_API"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LECTURA_CACHE_DIR", CACHE)
    return tmp_path


@pytest.fixture
def serveur():
    import serveur_factice

    serveur_factice.APPELS.clear()
    srv, url = serveur_factice.demarrer()
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    yield url
    srv.shutdown()
    srv.server_close()
