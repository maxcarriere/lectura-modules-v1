# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Base nue (sans index) et indexation chez l'utilisateur."""

import sqlite3

import pytest

from conftest import MOTS_EN, MOTS_FR, ecrire_lexik, ecrire_tableau
from lectura_lexicon import Lexicon, LexiconLocal, convertir
from lectura_lexicon.nue import COMPLEMENTS, denuder, est_nue, indexer


def lignes(chemin, sauf=("metadonnees",)):
    db = sqlite3.connect(chemin)
    tables = [n for (n,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name") if n not in sauf]
    return {t: db.execute(f"SELECT rowid, * FROM {t} ORDER BY rowid" if t in ("formes", "analyses", "lemmes", "cles_phone")
                          else f"SELECT * FROM {t} ORDER BY 1, 2").fetchall() for t in tables}


@pytest.mark.parametrize("langue", ["fr", "en"])
def test_aller_retour_identique(tmp_path, langue, sans_reseau):
    """Base nue avec tous les compléments, puis indexée : mêmes tables, mêmes lignes que la base d'origine."""
    if langue == "fr":
        base = convertir(ecrire_lexik(tmp_path / "LeXiK"), tmp_path / "base.db")
    else:
        base = convertir(ecrire_tableau(tmp_path / "w.tsv", MOTS_EN), tmp_path / "base.db", langue="en")
    nue = denuder(base, tmp_path / "nue.db", complements=COMPLEMENTS)
    assert est_nue(nue) and not est_nue(base)
    refaite = indexer(nue, tmp_path / "refaite.db")
    assert lignes(refaite) == lignes(base)


def test_nue_sans_complement(tmp_path, sans_reseau):
    base = convertir(ecrire_tableau(tmp_path / "m.tsv", MOTS_FR), tmp_path / "base.db")
    nue = denuder(base, tmp_path / "nue.db")
    db = sqlite3.connect(nue)
    assert {n for (n,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {
        "formes", "lemmes", "types", "analyses", "americaines", "metadonnees"}
    assert [r[1] for r in db.execute("PRAGMA table_info(formes)")] == ["id", "ortho", "zipf", "drapeaux"]
    assert [r[1] for r in db.execute("PRAGMA table_info(analyses)")] == ["forme", "lemme", "type", "phone", "zipf"]
    a, b = Lexicon(base), Lexicon(nue)          # indexée une fois, dans le cache
    assert isinstance(b, LexiconLocal) and "cache" in str(b.chemin)
    for mot in ("chat", "maison", "mangeons", "Paris", "vair"):
        assert a.validite(mot) == b.validite(mot) and a.frequence(mot) == b.frequence(mot)
        assert a.phones(mot) == b.phones(mot) and a.lemmes_de(mot) == b.lemmes_de(mot)
    assert [f.ortho for f in a.homophones("vɛʁ")] == [f.ortho for f in b.homophones("vɛʁ")]
    assert a.rimes("chanson") == b.rimes("chanson") and a.anagrammes("aimer") == b.anagrammes("aimer")
    assert Lexicon(nue).chemin == b.chemin       # le cache sert la deuxième fois


def test_tailles_nues(tmp_path, sans_reseau):
    base = convertir(ecrire_tableau(tmp_path / "m.tsv", MOTS_FR), tmp_path / "base.db")
    n = {t: sqlite3.connect(denuder(base, tmp_path / f"{t}.db", t, seuil=5.0)).execute(
        "SELECT COUNT(*) FROM formes").fetchone()[0] for t in ("complet", "standard", "mini")}
    assert n["complet"] == len({m[0] for m in MOTS_FR})
    assert n["standard"] == n["complet"] - 1                       # mangeâmes : fréquence nulle
    mini = Lexicon(tmp_path / "mini.db")
    assert mini.existe("maison") and mini.forme("chat") is None    # zipf 5,48 / 4,78 au seuil 5
    assert mini.lectures("maison")[0].lemme == "maison"            # une mini nue garde ses analyses


def test_forme_sans_analyse(tmp_path, sans_reseau):
    """Une forme validée sans analyse survit à l'aller-retour."""
    base = convertir(ecrire_tableau(tmp_path / "w.tsv", MOTS_EN), tmp_path / "base.db", langue="en")
    db = sqlite3.connect(base)
    i = db.execute("SELECT id FROM formes WHERE ortho = 'bat'").fetchone()[0]
    db.execute("DELETE FROM analyses WHERE forme = ?", (i,))
    db.execute("DELETE FROM phones WHERE forme = ?", (i,))
    db.execute("UPDATE formes SET cles = '', zipf_lemme = 0, drapeaux = 1 WHERE id = ?", (i,))
    db.commit()
    db.close()
    refaite = indexer(denuder(base, tmp_path / "nue.db", complements=COMPLEMENTS), tmp_path / "refaite.db")
    req = "SELECT ortho, zipf, zipf_lemme, drapeaux FROM formes ORDER BY id"   # (numéros des clés : renumérotés)
    assert sqlite3.connect(base).execute(req).fetchall() == sqlite3.connect(refaite).execute(req).fetchall()
    x, y = Lexicon(base, langue="en"), Lexicon(refaite, langue="en")
    for mot in ("bat", "cat", "eat", "nation"):
        assert x.forme(mot) == y.forme(mot) and x.lectures(mot) == y.lectures(mot)
    assert y.forme("bat") is not None and y.lectures("bat") == []


def test_non_validees_exclues(tmp_path, sans_reseau):
    base = convertir(ecrire_lexik(tmp_path / "LeXiK"), tmp_path / "base.db", non_classes=True)
    nue = denuder(base, tmp_path / "nue.db")
    assert sqlite3.connect(nue).execute("SELECT COUNT(*) FROM formes WHERE ortho = 'Takada'").fetchone()[0] == 0


def test_installer_base_livree(tmp_path, sans_reseau, monkeypatch):
    """Une base nue livrée en .db.xz s'installe (index compris) là où Lexicon la trouve en mode local."""
    import hashlib
    import lzma

    from lectura_lexicon.__main__ import main

    base = convertir(ecrire_tableau(tmp_path / "m.tsv", MOTS_FR), tmp_path / "base.db")
    nue = denuder(base, tmp_path / "lexicon-fr-standard.db", "standard")
    livree = tmp_path / "lexicon-fr-standard.db.xz"
    livree.write_bytes(lzma.compress(nue.read_bytes()))
    assert main(["installer", str(livree), "--sha256", "0" * 64]) == 1          # empreinte fausse : refus
    assert main(["installer", str(livree), "--sha256", hashlib.sha256(livree.read_bytes()).hexdigest()]) == 0
    installee = sans_reseau / ".lectura" / "models" / "lexicon" / "standard" / "lexicon.db"
    assert installee.exists()
    lex = Lexicon(mode="local")
    assert lex.chemin == installee and lex.existe("maison") and lex.taille == "standard"
