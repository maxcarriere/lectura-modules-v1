# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Le paquet installé : version, alias des anciens noms, aucun modèle ni donnée lourde, en-têtes, chemins."""

from __future__ import annotations

import re
from pathlib import Path

import lectura_nlp_fr

RACINE = Path(lectura_nlp_fr.__file__).parent
TABLES = {"abregements.tsv", "briques_formules.tsv", "correctifs.tsv", "formules_phone.tsv", "liaisons_contextes.tsv",
          "maths_signes.tsv", "mots_composes_espace.txt", "mots_lexicalises.txt", "mots_lexicalises_phone.txt",
          "sms.tsv"}


def test_version():
    assert lectura_nlp_fr.__version__ == "2.0.0"


def test_alias_memes_modules():
    import lectura_corrector.nettoyage
    import lectura_transducer
    import lectura_transducer.juge
    import lectura_transducer.moteur

    import lectura_nlp_fr.analyseur.juge
    import lectura_nlp_fr.correcteur.nettoyage

    assert lectura_transducer is lectura_nlp_fr.analyseur
    assert lectura_transducer.juge is lectura_nlp_fr.analyseur.juge
    assert lectura_transducer.moteur.creer_moteur is lectura_nlp_fr.analyseur.moteur.creer_moteur
    assert lectura_corrector.nettoyage is lectura_nlp_fr.correcteur.nettoyage
    from lectura_transducer import creer_moteur, decouper  # noqa: F401  (ce qu'importent serveur et voix)


def test_alias_module_absent():
    import importlib

    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("lectura_transducer.enveloppe")


def test_aucun_modele_ni_donnee_lourde():
    fichiers = [p for p in RACINE.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    interdits = [p for p in fichiers if p.suffix in (".onnx", ".db", ".xz", ".bin", ".npz", ".json", ".pt", ".gz")]
    assert interdits == []
    assert not (RACINE / "analyseur" / "modeles").exists()
    assert sum(p.stat().st_size for p in fichiers) < 2_000_000
    assert {p.name for p in (RACINE / "analyseur" / "data").iterdir()} == TABLES


def test_en_tetes_et_chemins():
    for p in RACINE.rglob("*.py"):
        texte = p.read_text(encoding="utf-8")
        assert texte.startswith("# Copyright (C) 2025-2026 Maxime Carrière (Lectura)\n# Licence : AGPL-3.0-or-later"), p
        assert "sys.path" not in texte, p
        assert not re.search(r"/(data|home)/\w", texte), p
        assert "LICENCE-COMMERCIALE" not in texte, p


def test_tables_lues_depuis_le_paquet():
    from lectura_nlp_fr.analyseur.abregements import table

    assert len(table()) > 1000
