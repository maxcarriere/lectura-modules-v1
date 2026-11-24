# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Base **nue** : seulement ce qui ne se calcule pas ; les index se construisent sur la machine de l'utilisateur.

Contenu (même schéma pour toutes les tailles) :

- ``formes``   : graphie, fréquence de la forme (indice Zipf), ``drapeaux`` (forme spéciale : abréviation,
  symbole, sigle… ; en anglais, graphie britannique) ;
- ``lemmes``   : table des lemmes : identifiant ``lemme#UPOS[#n]``, fréquence du lemme (zipf), autre genre des
  noms (``masculin`` / ``feminin``), ``auxiliaire`` (et ``auxiliaire_source`` : « lexik » ou « regle »),
  ``pronominal``, ``groupe`` des verbes, ``ortho_1990`` (« rectifiee », « traditionnelle »). Le h aspiré n'y est
  pas : il se lit dans la prononciation (marque ``*h*``) ;
- ``types``    : analyse (UPOS, traits UD, étiquette MULTEXT en français), numérotée ;
- ``analyses`` : forme, lemme, type, prononciation (alphabet phonétique international, syllabée, avec les marques
  du cadre quand la source en a : latentes, h aspiré, variantes ; la forme brute s'en déduit), fréquence de
  l'analyse (zipf) ;
- ``americaines`` (anglais) : graphie américaine d'une forme britannique.

Les formes non validées (« non classées » de LeXiK, jetons de corpus) ne sont jamais reprises.

Compléments facultatifs (``complements=``) : ``variantes`` (graphies variantes et leur graphie usuelle),
``marque`` (marques du Wiktionnaire sur une flexion), ``confiance``.

Tailles, définies par la fréquence de la forme : ``complet`` (toutes), ``standard`` (zipf > 0), ``mini``
(zipf ≥ ``seuil``).

    python -m lectura_lexicon denuder lexicon.db nue.db [--taille standard|mini] [--seuil 2] [--complements …]
    python -m lectura_lexicon indexer nue.db lexicon.db        # chez l'utilisateur : base au format rapide

``Lexicon(chemin)`` accepte aussi une base nue : elle est indexée une fois, au premier usage, dans le cache
(``LECTURA_CACHE_DIR`` ou ``~/.lectura/cache/lexicon``).
"""

from __future__ import annotations

import os
import sqlite3
import time
import zlib
from pathlib import Path

FORMAT = "lexicon-nue-2"
COMPLEMENTS = ("variantes", "marque", "confiance")
PROPRIETES_LEMMES = ("masculin", "feminin", "auxiliaire", "pronominal", "groupe", "auxiliaire_source", "ortho_1990")
TAILLES_NUES = ("complet", "standard", "mini")
SEUIL_MINI = 2.0
SPECIAL, VARIANTE, BRITANNIQUE, NON_VALIDE = 4, 16, 64, 128

SCHEMA_NUE = """
CREATE TABLE formes (id INTEGER PRIMARY KEY, ortho TEXT NOT NULL, zipf REAL NOT NULL, drapeaux INTEGER NOT NULL);
CREATE TABLE lemmes (id INTEGER PRIMARY KEY, id_lemme TEXT NOT NULL, zipf REAL NOT NULL, masculin TEXT,
                     feminin TEXT, auxiliaire TEXT, pronominal TEXT, groupe INTEGER, auxiliaire_source TEXT,
                     ortho_1990 TEXT);
CREATE TABLE types (id INTEGER PRIMARY KEY, upos TEXT NOT NULL, traits TEXT NOT NULL, multext TEXT NOT NULL);
CREATE TABLE analyses (forme INTEGER NOT NULL, lemme INTEGER NOT NULL, type INTEGER NOT NULL, phone TEXT,
                       zipf REAL NOT NULL);
CREATE TABLE americaines (forme INTEGER PRIMARY KEY, americaine TEXT);
CREATE TABLE metadonnees (cle TEXT PRIMARY KEY, valeur TEXT);
"""


def est_nue(chemin: Path) -> bool:
    try:
        db = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
        return dict(db.execute("SELECT cle, valeur FROM metadonnees")).get("format", "").startswith("lexicon-nue-")
    except sqlite3.Error:
        return False


def denuder(base, sortie, taille: str = "complet", seuil: float = SEUIL_MINI, complements=(),
            afficher=None) -> Path:
    """Base nue tirée d'une base au format rapide (avec analyses) ; rend le chemin écrit."""
    afficher = afficher or (lambda *_: None)
    if taille not in TAILLES_NUES:
        raise ValueError(f"taille « {taille} » : attendu {', '.join(TAILLES_NUES)}")
    inconnus = set(complements) - set(COMPLEMENTS)
    if inconnus:
        raise ValueError(f"compléments inconnus : {sorted(inconnus)} (possibles : {', '.join(COMPLEMENTS)})")
    c = set(complements)
    t0 = time.time()
    base, sortie = Path(base), Path(sortie)
    src = sqlite3.connect(f"file:{base}?mode=ro", uri=True)
    meta = dict(src.execute("SELECT cle, valeur FROM metadonnees"))
    langue = meta.get("langue") or ("en" if src.execute(
        "SELECT 1 FROM sqlite_master WHERE name = 'americaines'").fetchone() else "fr")
    if src.execute("SELECT 1 FROM analyses LIMIT 1").fetchone() is None:
        raise ValueError(f"{base} : base sans analyses : rien à dénuder")
    codes: dict[str, dict[int, str]] = {}
    for e, i, v in src.execute("SELECT espace, id, valeur FROM codes"):
        codes.setdefault(e, {})[i] = v
    col_a = {r[1] for r in src.execute("PRAGMA table_info(analyses)")}
    col_l = {r[1] for r in src.execute("PRAGMA table_info(lemmes)")}

    sortie.parent.mkdir(parents=True, exist_ok=True)
    provisoire = sortie.with_name(sortie.name + ".tmp")
    provisoire.unlink(missing_ok=True)
    db = sqlite3.connect(provisoire)
    db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA_NUE)
    for nom in ("marque", "confiance"):
        if nom in c:
            db.execute(f"ALTER TABLE analyses ADD COLUMN {nom} TEXT")
    if "variantes" in c:
        db.execute("CREATE TABLE usuelles (forme INTEGER PRIMARY KEY, usuelle TEXT)")

    garder = SPECIAL | BRITANNIQUE | (VARIANTE if "variantes" in c else 0)
    condition = {"complet": "", "standard": " AND zipf > 0", "mini": " AND zipf >= ?"}[taille]
    params = (seuil,) if taille == "mini" else ()
    nouveaux: dict[int, int] = {}
    lignes = []
    for ancien, ortho, z, dr in src.execute(
            f"SELECT id, ortho, zipf, drapeaux FROM formes WHERE NOT (drapeaux & {NON_VALIDE}){condition} ORDER BY id",
            params):
        nouveaux[ancien] = len(nouveaux)
        lignes.append((nouveaux[ancien], ortho, z, dr & garder))
    db.executemany("INSERT INTO formes VALUES (?,?,?,?)", lignes)
    del lignes
    types: dict[tuple, int] = {}
    lemmes: dict[int, int] = {}
    extra = [x for x in ("marque", "confiance") if x in c and x in col_a]
    msd = "a.multext" if "multext" in col_a else "NULL"
    requete = (f"SELECT a.forme, a.lemme, a.upos, a.traits, {msd}, COALESCE(a.phone_enrichi, a.phone), a.zipf"
               + "".join(f", a.{x}" for x in extra) + " FROM analyses a ORDER BY a.rowid")
    lot, insertion = [], None
    for forme, lemme, u, tr, m, phone, za, *autres in src.execute(requete):
        if forme not in nouveaux:
            continue
        cle = (codes["upos"][u], codes["traits"][tr], codes.get("multext", {}).get(m, "") if m is not None else "")
        k = types.setdefault(cle, len(types))
        j = lemmes.setdefault(lemme, len(lemmes))
        lot.append((nouveaux[forme], j, k, phone, za or 0.0, *autres))
        if len(lot) >= 50_000:
            insertion = insertion or f"INSERT INTO analyses VALUES ({','.join('?' * len(lot[0]))})"
            db.executemany(insertion, lot)
            lot = []
    if lot:
        db.executemany(insertion or f"INSERT INTO analyses VALUES ({','.join('?' * len(lot[0]))})", lot)
    db.executemany("INSERT INTO types VALUES (?,?,?,?)", [(k, *cle) for cle, k in types.items()])
    cols_l = "id_lemme, zipf" + "".join(f", {x}" if x in col_l else ", NULL" for x in PROPRIETES_LEMMES)
    anciens = {i: r for i, *r in src.execute(f"SELECT id, {cols_l} FROM lemmes")}
    db.executemany(f"INSERT INTO lemmes VALUES ({','.join('?' * (3 + len(PROPRIETES_LEMMES)))})",
                   [(j, *anciens[i]) for i, j in sorted(lemmes.items(), key=lambda x: x[1])])
    if "variantes" in c:
        db.executemany("INSERT INTO usuelles VALUES (?,?)", [(nouveaux[f], u) for f, u in src.execute(
            "SELECT forme, usuelle FROM usuelles") if f in nouveaux])
    if langue == "en":
        db.executemany("INSERT INTO americaines VALUES (?,?)", [(nouveaux[f], u) for f, u in src.execute(
            "SELECT forme, americaine FROM americaines") if f in nouveaux])
    meta_nue = {"format": FORMAT, "langue": langue, "taille": taille, "complements": ",".join(sorted(c)),
                "seuil": seuil if taille == "mini" else "", "source": base.name,
                "licence": meta.get("licence", ""), "construit": time.strftime("%Y-%m-%d %H:%M")}
    db.executemany("INSERT INTO metadonnees VALUES (?,?)", [(k, str(v)) for k, v in meta_nue.items()])
    db.commit()
    db.execute("VACUUM")
    db.close()
    provisoire.replace(sortie)
    afficher(f"{sortie} : {len(nouveaux)} formes, {sortie.stat().st_size / 1e6:.1f} Mo ({time.time() - t0:.0f} s)")
    return sortie


def indexer(nue, sortie, zipf_voisins: float = 1.0, suppressions: int = 1, afficher=None) -> Path:
    """Base au format rapide (avec tous ses index) construite depuis la base nue ``nue``."""
    from .conversion import _ecrire, phone_brut
    afficher = afficher or (lambda *_: None)
    t0 = time.time()
    nue, sortie = Path(nue), Path(sortie)
    src = sqlite3.connect(f"file:{nue}?mode=ro", uri=True)
    meta = dict(src.execute("SELECT cle, valeur FROM metadonnees"))
    if meta.get("format") != FORMAT:
        raise ValueError(f"{nue} : pas une base nue ({FORMAT})")
    langue = meta["langue"]
    c = set(filter(None, meta.get("complements", "").split(",")))

    def fpm(z):
        return 10 ** (z - 3) if z and z > 0 else 0.0

    col_a = {r[1] for r in src.execute("PRAGMA table_info(analyses)")}
    requete = ("SELECT f.ortho, f.zipf, f.drapeaux, l.id_lemme, t.upos, t.traits, t.multext, a.phone, a.zipf, "
               + ("a.confiance" if "confiance" in col_a else "NULL") + ", "
               + ("a.marque" if "marque" in col_a else "NULL")
               + " FROM formes f LEFT JOIN analyses a ON a.forme = f.id LEFT JOIN lemmes l ON l.id = a.lemme"
                 " LEFT JOIN types t ON t.id = a.type ORDER BY f.id, a.rowid")

    def entrees():
        for ortho, z, dr, id_lemme, upos, traits, msd, phone, za, conf, mq in src.execute(requete):
            tbl = "speciaux" if dr & SPECIAL else "mots"
            if id_lemme is None:              # forme sans analyse : la forme seule
                yield (ortho, "", None, None, "", "", "", fpm(z), 0.0, "", tbl, "", None)
                continue
            brut = phone_brut(phone or "") if langue == "fr" else (phone or "")
            yield (ortho, id_lemme.split("#")[0], id_lemme, upos, traits, brut,
                   (phone if phone and phone != brut else ""), fpm(z), fpm(za), msd or "", tbl, conf or "", mq)

    def lemmes_source():
        for id_lemme, z, *props in src.execute(f"SELECT id_lemme, zipf, {', '.join(PROPRIETES_LEMMES)} FROM lemmes"):
            yield (id_lemme, fpm(z), *props)

    retenus = (VARIANTE | BRITANNIQUE) if langue == "en" else VARIANTE
    drapeaux_sup = {o: d & retenus for o, d in src.execute(f"SELECT ortho, drapeaux FROM formes WHERE drapeaux & {retenus}")}
    usuelles = dict(src.execute("SELECT f.ortho, u.usuelle FROM usuelles u JOIN formes f ON f.id = u.forme")) \
        if "variantes" in c else {}
    americaines = dict(src.execute("SELECT f.ortho, a.americaine FROM americaines a JOIN formes f ON f.id = a.forme"))
    meta_index = {"taille": meta.get("taille", "complet"), "langue": langue, "source": nue.name,
                  "format_source": "nue", "zipf_voisins": zipf_voisins, "suppressions": suppressions,
                  "seuil": meta.get("seuil", ""), "complements": ",".join(sorted(c)), "licence": meta.get("licence", "")}
    return _ecrire(sortie, langue, entrees(), lemmes_source(), usuelles, "nue", zipf_voisins, suppressions, afficher,
                   t0, "complet", SEUIL_MINI, 2.0, meta_index, drapeaux_sup=drapeaux_sup, americaines=americaines)


def dossier_modeles(langue: str) -> Path:
    """Dossier où ``Lexicon`` cherche les bases installées : ``LECTURA_MODELS_DIR/lexicon[_en]`` ou
    ``~/.lectura/models/lexicon[_en]``."""
    nom = "lexicon" if langue == "fr" else "lexicon_en"
    if os.environ.get("LECTURA_MODELS_DIR"):
        return Path(os.environ["LECTURA_MODELS_DIR"]) / nom
    return Path.home() / ".lectura" / "models" / nom


def installer(source, dossier=None, sha256: str | None = None, afficher=None) -> Path:
    """Installe une base nue livrée (``.db`` ou ``.db.xz``) : vérifie l'empreinte si elle est donnée, décompresse,
    construit les index et écrit ``<dossier>/<taille>/lexicon.db`` (langue et taille lues dans la base). Aucun
    réseau. Rend le chemin de la base installée."""
    import hashlib
    import lzma
    import shutil
    import tempfile

    afficher = afficher or (lambda *_: None)
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(f"base introuvable : {source}")
    if sha256:
        h = hashlib.sha256()
        with open(source, "rb") as f:
            while bloc := f.read(1 << 20):
                h.update(bloc)
        if h.hexdigest() != sha256.lower():
            raise ValueError(f"empreinte de {source.name} différente de celle attendue ({h.hexdigest()} ≠ {sha256})")
    with tempfile.TemporaryDirectory(prefix="lexicon-installation-") as tmp:
        nue = Path(tmp) / "nue.db"
        if source.suffix == ".xz":
            afficher("décompression…")
            with lzma.open(source, "rb") as entree, open(nue, "wb") as sortie:
                shutil.copyfileobj(entree, sortie, 1 << 20)
        else:
            shutil.copyfile(source, nue)
        if not est_nue(nue):
            raise ValueError(f"{source.name} n'est pas une base Lexicon nue")
        meta = dict(sqlite3.connect(f"file:{nue}?mode=ro", uri=True).execute("SELECT cle, valeur FROM metadonnees"))
        cible = (Path(dossier) if dossier else dossier_modeles(meta["langue"])) / meta.get("taille", "complet") / "lexicon.db"
        afficher(f"construction des index ({meta['langue']}, {meta.get('taille')})…")
        indexer(nue, cible, afficher=afficher)
    afficher(f"installée : {cible}")
    return cible


def indexee(nue: Path) -> Path:
    """Base indexée pour la base nue ``nue`` (construite une fois dans le cache, au premier usage)."""
    crc = 0
    with open(nue, "rb") as f:
        while bloc := f.read(1 << 20):
            crc = zlib.crc32(bloc, crc)
    cache = Path(os.environ.get("LECTURA_CACHE_DIR") or Path.home() / ".lectura" / "cache")
    cible = cache / "lexicon" / f"nue-{nue.stem}-{crc:08x}" / "lexicon.db"
    return cible if cible.exists() else indexer(nue, cible)


__all__ = ["denuder", "indexer", "indexee", "installer", "est_nue", "COMPLEMENTS", "FORMAT", "SEUIL_MINI"]
