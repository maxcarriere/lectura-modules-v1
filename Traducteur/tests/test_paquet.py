# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Le paquet ne contient ni modèle ni donnée, ne touche pas à ``sys.path``, ne se connecte pas à l'import et ne porte
aucun chemin absolu."""

import importlib
import pkgutil
import re
import sys
from pathlib import Path

import lectura_traducteur

PAQUET = Path(lectura_traducteur.__file__).parent


def test_aucune_donnee_dans_le_paquet():
    interdits = [p for p in PAQUET.rglob("*") if p.is_file() and p.suffix not in (".py", ".typed", ".pyc")]
    assert interdits == []


def test_aucun_chemin_absolu_ni_espace_de_developpement():
    motif = re.compile(r"/data/|/home/|C:\\\\|sys\.path|Modules/|workspace")
    fautifs = [(p.name, m.group(0)) for p in PAQUET.glob("*.py") for m in motif.finditer(p.read_text("utf-8"))]
    assert fautifs == []


def test_en_tete_agpl_partout():
    for p in PAQUET.glob("*.py"):
        assert "AGPL-3.0-or-later" in p.read_text("utf-8").splitlines()[1], p.name


def test_import_de_tous_les_modules_sans_toucher_sys_path():
    avant = list(sys.path)
    for m in pkgutil.iter_modules([str(PAQUET)]):
        importlib.import_module(f"lectura_traducteur.{m.name}")
    assert sys.path == avant


def test_aucun_reseau_a_l_import(monkeypatch, sans_modeles):
    import socket

    def refuse(*a, **k):
        raise AssertionError("connexion réseau à l'import")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    importlib.reload(lectura_traducteur)
    lectura_traducteur.Traducteur("en", "fr", mode="api")      # aucune connexion avant le premier appel


def test_version():
    from importlib import metadata

    try:
        assert metadata.version("lectura-traducteur") == lectura_traducteur.__version__
    except metadata.PackageNotFoundError:
        assert lectura_traducteur.__version__ == "1.0.0"
