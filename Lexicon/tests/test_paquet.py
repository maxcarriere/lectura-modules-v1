# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Le code source du paquet ne contient aucune base ni aucun fichier de données."""

from pathlib import Path

import lectura_lexicon

PAQUET = Path(lectura_lexicon.__file__).parent


def test_aucune_donnee_dans_le_paquet():
    interdits = [p for p in PAQUET.rglob("*") if p.is_file() and p.suffix not in (".py", ".typed", ".pyc")]
    assert interdits == []


def test_aucun_reseau_a_l_import(monkeypatch):
    import importlib
    import socket

    def refuse(*a, **k):
        raise AssertionError("connexion réseau à l'import")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    importlib.reload(lectura_lexicon)
    lectura_lexicon.Lexicon()          # mode API : aucune connexion avant le premier appel
