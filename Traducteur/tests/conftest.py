# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Fixtures communes : environnement sans modèles, réseau coupé, faux serveur d'API local.

Les phrases des tests sont écrites à la main pour les tests ; elles ne viennent d'aucun corpus. Les tests qui
demandent les modèles (traduction réelle, alignement, glossaire) sont sautés s'ils manquent : on les fournit par
``LECTURA_MODELS_DIR`` (sous-dossier ``traducteur`` ou ``translator``) ou ``~/.lectura/models/traducteur``.
"""

from __future__ import annotations

import socket
import threading

import pytest

VARIABLES = ("LECTURA_MODELS_DIR", "LECTURA_TRADUCTEUR_MODE", "LECTURA_TRADUCTEUR_API", "LECTURA_API_URL",
             "LECTURA_API_KEY")


@pytest.fixture()
def sans_modeles(monkeypatch, tmp_path):
    """Environnement propre : aucune variable Lectura, HOME vide (aucun modèle installé)."""
    for v in VARIABLES:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture()
def reseau_coupe(monkeypatch):
    """Toute tentative de connexion ou de résolution de nom échoue et est notée."""
    tentatives = []

    def refuse(*a, **k):
        tentatives.append(a[1:] if a else k)
        raise AssertionError(f"appel réseau interdit : {a[1:] if a else k}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    return tentatives


def lancer(traducteurs=None):
    from serveur_factice import demarrer

    srv, url = demarrer(traducteurs)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, url


@pytest.fixture(scope="session")
def serveur():
    """Faux serveur d'API sur 127.0.0.1 (port libre), qui suit la spécification des routes ``/v1/traduire``."""
    srv, url = lancer()
    yield url
    srv.shutdown()


def traducteur_local(source, cible, **options):
    """Traducteur local avec les modèles installés, ou saut du test."""
    from lectura_traducteur import ModelesAbsents, Traducteur

    try:
        return Traducteur(source, cible, mode="local", **options)
    except (ModelesAbsents, ImportError) as e:
        pytest.skip(str(e))
