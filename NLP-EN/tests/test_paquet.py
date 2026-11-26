# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Le paquet installé : version, alias des anciens noms, aucun modèle ni donnée lourde, en-têtes, chemins."""

from __future__ import annotations

import re
from pathlib import Path

import lectura_nlp_en

RACINE = Path(lectura_nlp_en.__file__).parent
TABLES = {"__init__.py", "abregements.tsv", "briques_formules.tsv", "correctifs.tsv", "formes_fortes.tsv",
          "formules_phone.tsv", "maths_signes.tsv", "mots_lexicalises.txt", "mots_lexicalises_phone.txt"}
ADRESSE = re.compile(r"[\w.%+-]+@[\w-]+\.[\w.-]+")


def test_version():
    assert lectura_nlp_en.__version__ == "1.0.0"


def test_alias_memes_modules():
    import lectura_corrector_en
    import lectura_corrector_en.coeur
    import lectura_transducer_en
    import lectura_transducer_en.chaine
    import lectura_transducer_en.moteur

    import lectura_nlp_en.analyseur.chaine
    import lectura_nlp_en.correcteur.coeur

    assert lectura_transducer_en is lectura_nlp_en.analyseur
    assert lectura_transducer_en.chaine is lectura_nlp_en.analyseur.chaine
    assert lectura_transducer_en.moteur.creer_moteur is lectura_nlp_en.analyseur.moteur.creer_moteur
    assert lectura_corrector_en.coeur is lectura_nlp_en.correcteur.coeur
    assert lectura_corrector_en.Correcteur is lectura_nlp_en.correcteur.Correcteur
    # ce qu'importent le serveur (routers/nlp.py) et lectura-lexicon 1.0.0 (lectura_lexicon.en.transducer)
    from lectura_transducer_en import creer_moteur, decouper  # noqa: F401
    from lectura_transducer_en.analyse import Entree  # noqa: F401
    from lectura_transducer_en.lexique import traits  # noqa: F401
    from lectura_transducer_en.phonetique import sans_marques  # noqa: F401


def test_alias_module_absent():
    import importlib

    import pytest

    for nom in ("lectura_transducer_en.adaptateurs.etalon", "lectura_transducer_en.adaptateurs.gpa",
                "lectura_transducer_en.modele_langue"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(nom)


def test_aucun_modele_ni_donnee_lourde():
    fichiers = [p for p in RACINE.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    interdits = [p for p in fichiers if p.suffix in (".onnx", ".db", ".xz", ".bin", ".npz", ".json", ".pt", ".gz")]
    assert interdits == []
    assert not (RACINE / "analyseur" / "modeles").exists() and not (RACINE / "correcteur" / "modeles").exists()
    assert sum(p.stat().st_size for p in fichiers) < 1_500_000
    assert {p.name for p in (RACINE / "analyseur" / "data").iterdir() if p.is_file()} == TABLES


def test_en_tetes_chemins_adresses():
    for p in RACINE.rglob("*.py"):
        texte = p.read_text(encoding="utf-8")
        assert texte.startswith("# Copyright (C) 2025-2026 Maxime Carrière (Lectura)\n# Licence : AGPL-3.0-or-later"), p
        assert "sys.path" not in texte, p
        assert "import torch" not in texte, p
        assert not re.search(r"/(data|home)/\w", texte), p
        assert "LICENCE-COMMERCIALE" not in texte, p
    for p in (RACINE / "analyseur" / "data").iterdir():
        if p.is_file() and p.suffix in (".tsv", ".txt"):
            assert not ADRESSE.search(p.read_text(encoding="utf-8")), p


def test_tables_lues_depuis_le_paquet():
    from lectura_nlp_en.analyseur.abregements import table

    assert len(table()) > 1000


def test_aucun_reseau_a_l_import(sans_reseau, sans_modeles):
    import importlib

    importlib.reload(lectura_nlp_en)
    assert sans_reseau == []
