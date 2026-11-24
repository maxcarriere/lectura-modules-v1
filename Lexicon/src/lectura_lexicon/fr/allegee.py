# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Tailles standard et complète livrées « allégées » : installation locale depuis un fichier, sans réseau.

Une base allégée est la base SQLite de la taille (``donnees.SCHEMA``) sans ce qui se recalcule : tables ``voisins`` et
``voisins_phones`` vides, aucun index, colonnes ``formes.min``, ``formes.anagramme`` et ``cles_phone.inverse`` à NULL.
Elle est livrée dans une archive ``lexicon-<taille>-<version>.tar.xz`` (membre ``<taille>/lexicon.db``).

``installer`` vérifie l'empreinte SHA-256 de l'archive (empreintes officielles écrites dans ce
module, ``EMPREINTES``, ou empreinte donnée), extrait la base, recalcule voisins, colonnes et index avec les
fonctions de ``cles`` (les mêmes que la construction : la base obtenue répond comme la base construite) et l'écrit dans
``<dossier>/<taille>/lexicon.db`` (par défaut ``LECTURA_MODELS_DIR/lexicon`` ou ``~/.lectura/models/lexicon``, où
``Lexicon(taille=…)`` la trouve). Rien ne passe par le réseau.

    python -m lectura_lexicon installer --taille standard --source lexicon-standard-0.5.0.tar.xz
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path

from .cles import anagramme, empreinte, inverse, minuscule, phonemes, suppressions
from .donnees import NON_VALIDE, SPECIAL

TAILLES_ALLEGEES = ("standard", "complet")
# Empreintes SHA-256 des archives officielles (les bases ne sont jamais dans le paquet ; elles sont remises avec
# la licence commerciale ou une base sur mesure).
EMPREINTES = {'lexicon-complet-0.5.0.tar.xz': 'b8519f0f0bcbd4b2a8ff6664eb59d049b945eb65a860af5ab9967b7b8b64cb10', 'lexicon-standard-0.5.0.tar.xz': '851cb049012900b68028bf7cc3598a76abd549bf6f4cf5ee489df22a5e49cbaa'}
INDEX = ("CREATE INDEX idx_formes_min ON formes (min); CREATE UNIQUE INDEX idx_cles_phone ON cles_phone (cle);"
         "CREATE INDEX idx_cles_inverse ON cles_phone (inverse); CREATE INDEX idx_formes_anagramme ON formes (anagramme);"
         "CREATE INDEX idx_analyses_syllabes ON analyses (syllabes, zipf);"
         "CREATE INDEX idx_analyses_forme ON analyses (forme); CREATE INDEX idx_analyses_lemme ON analyses (lemme);"
         "CREATE INDEX idx_analyses_phone ON analyses (phone);"
         "CREATE INDEX idx_lemmes_lemme ON lemmes (lemme); CREATE INDEX idx_lemmes_id ON lemmes (id_lemme);")


class ErreurInstallation(RuntimeError):
    """Archive absente, empreinte inconnue ou différente, contenu inattendu."""


def dossier_par_defaut() -> Path:
    """Dossier des modèles où ``trouver_donnees`` cherche les tailles installées."""
    if os.environ.get("LECTURA_MODELS_DIR"):
        return Path(os.environ["LECTURA_MODELS_DIR"]) / "lexicon"
    return Path.home() / ".lectura" / "models" / "lexicon"


def sha256(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        while bloc := f.read(1 << 20):
            h.update(bloc)
    return h.hexdigest()


def empreintes_officielles() -> dict[str, str]:
    """Nom de fichier → SHA-256 des archives officielles de cette version du paquet."""
    return dict(EMPREINTES)


# ── Côté livraison ─────────────────────────────────────────────────────────────

def alleger(base: Path, sortie: Path) -> Path:
    """Copie allégée de ``base`` (standard ou complète) : voisins vidés, index retirés, colonnes dérivées à NULL."""
    shutil.copyfile(base, sortie)
    db = sqlite3.connect(sortie)
    for (nom,) in db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'").fetchall():
        db.execute(f"DROP INDEX {nom}")
    db.executescript("DELETE FROM voisins; DELETE FROM voisins_phones; UPDATE formes SET min = NULL, anagramme = NULL;"
                     "UPDATE cles_phone SET inverse = NULL;")
    db.commit()
    db.execute("VACUUM")
    db.close()
    return sortie


def archiver(base_allegee: Path, taille: str, sortie: Path, preset: int = 6) -> Path:
    """Archive ``tar.xz`` livrable (membre ``<taille>/lexicon.db``)."""
    with tarfile.open(sortie, "w:xz", preset=preset) as tar:
        tar.add(base_allegee, arcname=f"{taille}/lexicon.db")
    return sortie


# ── Côté développeur ───────────────────────────────────────────────────────────

def reconstruire(chemin: Path) -> None:
    """Recalcule, en place, ce que l'allègement a retiré (colonnes dérivées, voisins, index)."""
    db = sqlite3.connect(chemin)
    db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
    meta = dict(db.execute("SELECT cle, valeur FROM metadonnees"))
    zv, n = float(meta["zipf_voisins"]), int(meta["suppressions"])
    formes = db.execute("SELECT id, ortho, zipf, drapeaux FROM formes").fetchall()
    db.executemany("UPDATE formes SET min = ?, anagramme = ? WHERE id = ?",
                   ((minuscule(o), anagramme(o) or None, i) for i, o, _, _ in formes))
    cles = db.execute("SELECT id, cle FROM cles_phone").fetchall()
    db.executemany("UPDATE cles_phone SET inverse = ? WHERE id = ?", ((inverse(c), k) for k, c in cles))
    voisins = set()
    for i, o, z, d in formes:
        m = minuscule(o)
        if z >= zv and " " not in m and len(m) >= 2 and not d & (SPECIAL | NON_VALIDE):
            voisins.update((empreinte(s), i) for s in suppressions(m, n))
    db.executemany("INSERT INTO voisins VALUES (?,?)", sorted(voisins))
    del voisins, formes
    voisines = {k for (k,) in db.execute(
        f"SELECT DISTINCT p.cle FROM phones p JOIN formes f ON f.id = p.forme WHERE f.zipf >= ? "
        f"AND NOT (f.drapeaux & {NON_VALIDE})", (zv,))}
    vp = {(empreinte(s), k) for k, c in cles if k in voisines for s in suppressions(phonemes(c), n)}
    db.executemany("INSERT INTO voisins_phones VALUES (?,?)", sorted(vp))
    del vp
    db.executescript(INDEX)
    db.commit()
    db.close()


def installer(source: str | Path, taille: str, dossier: str | Path | None = None, sha: str | None = None,
              afficher=None) -> Path:
    """Installe la taille ``taille`` depuis l'archive locale ``source`` ; rend le chemin de la base installée.

    L'archive doit avoir l'empreinte ``sha`` (si donnée) ou une empreinte officielle du paquet ; sinon
    ``ErreurInstallation``. L'installation est sûre : la base est écrite à côté puis renommée."""
    dire = afficher or (lambda _: None)
    if taille not in TAILLES_ALLEGEES:
        raise ErreurInstallation(f"taille « {taille} » : seules {', '.join(TAILLES_ALLEGEES)} s'installent depuis "
                                 "une archive (la mini est livrée dans le paquet)")
    source = Path(source)
    if not source.is_file():
        raise ErreurInstallation(f"archive introuvable : {source}")
    dire(f"vérification de l'empreinte de {source.name}…")
    reelle = sha256(source)
    attendue = sha.lower() if sha else empreintes_officielles().get(source.name)
    if attendue is None:
        raise ErreurInstallation(f"{source.name} n'est pas une archive connue de ce paquet (empreinte {reelle}) ; "
                                 "renommez-la comme reçue, ou donnez son empreinte (--sha256)")
    if reelle != attendue:
        raise ErreurInstallation(f"empreinte de {source.name} différente de celle attendue : fichier abîmé ou "
                                 f"incomplet ({reelle} ≠ {attendue})")
    cible = Path(dossier) if dossier else dossier_par_defaut()
    finale = cible / taille / "lexicon.db"
    finale.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=finale.parent, prefix=".installation-") as tmp:
        provisoire = Path(tmp) / "lexicon.db"
        dire("décompression…")
        trouve = False
        with tarfile.open(source, "r|xz") as tar:        # lecture en flux : une seule décompression
            for membre in tar:
                if membre.name == f"{taille}/lexicon.db" and membre.isfile():
                    with tar.extractfile(membre) as entree, open(provisoire, "wb") as sortie:
                        shutil.copyfileobj(entree, sortie, 1 << 20)
                    trouve = True
                    break
        if not trouve:
            raise ErreurInstallation(f"{source.name} ne contient pas la taille « {taille} »")
        meta = dict(sqlite3.connect(provisoire).execute("SELECT cle, valeur FROM metadonnees"))
        if meta.get("taille") != taille:
            raise ErreurInstallation(f"{source.name} contient la taille « {meta.get('taille')} », pas « {taille} »")
        dire("reconstruction des index et des voisins (une à deux minutes)…")
        reconstruire(provisoire)
        provisoire.replace(finale)
    dire(f"installée : {finale}")
    return finale


def installees(dossier: str | Path | None = None) -> dict[str, Path]:
    """Tailles présentes dans le dossier des modèles (et la mini du paquet)."""
    cible = Path(dossier) if dossier else dossier_par_defaut()
    res = {t: cible / t / "lexicon.db" for t in ("mini", "standard", "complet") if (cible / t / "lexicon.db").exists()}
    paquet = Path(__file__).resolve().parent / "donnees" / "mini"
    if "mini" not in res and ((paquet / "lexicon.db").exists() or (paquet / "lexicon.tsv.xz").exists()):
        res["mini"] = paquet / ("lexicon.db" if (paquet / "lexicon.db").exists() else "lexicon.tsv.xz")
    return res
