# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Données livrées compressées (``lexicon.tsv.xz``) et installées au premier usage en ``lexicon.db``.

Depuis la 0.3, la mini est livrée construite dans le paquet (``donnees/mini/lexicon.db``) ; ce module sert à la
construire et à la variante « source compressée ». La taille ``mini`` peut être livrée sous forme de source : une ligne JSON de métadonnées, puis une ligne par forme
(triées), séparées par des tabulations :

    ortho  zipf×100  zipf_lemme×100  drapeaux  clés phonétiques (espaces)  graphie usuelle  graphie américaine

``installer`` en tire la base sqlite (schéma ``donnees.SCHEMA``, sans analyses) et recalcule les index des voisins
(suppressions de lettres et de phonèmes). La base installée va dans le cache (``LECTURA_CACHE_DIR`` ou
``~/.lectura/cache``), sous ``lexicon_en/<taille>-<empreinte>/``.
"""

from __future__ import annotations

import json
import lzma
import os
import sqlite3
import zlib
from pathlib import Path

from .cles import empreinte, inverse, minuscule, phonemes, suppressions
from .donnees import NON_VALIDE, SCHEMA, SPECIAL

INDEX = ("CREATE INDEX idx_formes_min ON formes (min); CREATE UNIQUE INDEX idx_cles_phone ON cles_phone (cle);"
         "CREATE INDEX idx_cles_inverse ON cles_phone (inverse);")


def ecrire_source(chemin: Path, meta: dict, formes: list[tuple]) -> None:
    """``formes`` : (ortho, zipf, zipf_lemme, drapeaux, clés phonétiques, usuelle, américaine), triées par graphie."""
    with lzma.open(chemin, "wt", encoding="utf-8", preset=9 | lzma.PRESET_EXTREME) as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for ortho, zipf, zl, drapeaux, cles, usuelle, americaine in formes:
            f.write(f"{ortho}\t{round(zipf * 100)}\t{round(zl * 100)}\t{drapeaux}\t{' '.join(cles)}\t{usuelle}\t"
                    f"{americaine}\n")


def lire_source(chemin: Path) -> tuple[dict, list[tuple]]:
    with lzma.open(chemin, "rt", encoding="utf-8") as f:
        meta = json.loads(f.readline())
        formes = []
        for ligne in f:
            ortho, zipf, zl, drapeaux, cles, usuelle, americaine = ligne.rstrip("\n").split("\t")
            formes.append((ortho, int(zipf) / 100, int(zl) / 100, int(drapeaux), cles.split() if cles else [], usuelle,
                           americaine))
    return meta, formes


def installer(source: Path, cible: Path) -> Path:
    """Construit ``cible`` (sqlite) depuis la source compressée ; écrit à côté puis renomme (installation sûre)."""
    meta, formes = lire_source(source)
    zipf_voisins, n_suppr = float(meta["zipf_voisins"]), int(meta["suppressions"])
    cible.parent.mkdir(parents=True, exist_ok=True)
    provisoire = cible.with_name(f"{cible.name}.{os.getpid()}.tmp")
    provisoire.unlink(missing_ok=True)
    db = sqlite3.connect(provisoire)
    db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA)
    ids_cles: dict[str, int] = {}
    rangs_formes, rangs_phones, usuelles, americaines = [], [], [], []
    cles_voisines: set[int] = set()
    voisins: set[tuple[int, int]] = set()
    for i, (ortho, zipf, zl, drapeaux, cles, usuelle, americaine) in enumerate(formes):
        numeros = []
        for c in cles:
            k = ids_cles.setdefault(c, len(ids_cles))
            numeros.append(k)
            rangs_phones.append((k, i))
            if zipf >= zipf_voisins and not drapeaux & NON_VALIDE:
                cles_voisines.add(k)
        mini = minuscule(ortho)
        rangs_formes.append((i, ortho, mini, zipf, zl, drapeaux, " ".join(map(str, numeros)), None))
        if usuelle:
            usuelles.append((i, usuelle))
        if americaine:
            americaines.append((i, americaine))
        if (zipf >= zipf_voisins and " " not in mini and len(mini) >= 2
                and not drapeaux & (SPECIAL | NON_VALIDE)):
            voisins.update((empreinte(s), i) for s in suppressions(mini, n_suppr))
    db.executemany("INSERT INTO formes VALUES (?,?,?,?,?,?,?,?)", rangs_formes)
    db.executemany("INSERT INTO usuelles VALUES (?,?)", usuelles)
    db.executemany("INSERT INTO americaines VALUES (?,?)", americaines)
    db.executemany("INSERT INTO cles_phone VALUES (?,?,?)", [(k, c, inverse(c)) for c, k in ids_cles.items()])
    db.executemany("INSERT INTO phones VALUES (?,?)", sorted(set(rangs_phones)))
    db.executemany("INSERT INTO voisins VALUES (?,?)", sorted(voisins))
    voisins = {(empreinte(s), k) for c, k in ids_cles.items() if k in cles_voisines
               for s in suppressions(phonemes(c), n_suppr)}
    db.executemany("INSERT INTO voisins_phones VALUES (?,?)", sorted(voisins))
    db.executemany("INSERT INTO metadonnees VALUES (?,?)", [(k, str(v)) for k, v in meta.items()])
    db.executescript(INDEX)
    db.commit()
    db.close()
    provisoire.replace(cible)
    return cible


def installee(source: Path) -> Path:
    """Base installée pour ``source`` (installée si besoin) : une par contenu de source (empreinte crc32)."""
    crc = 0
    with open(source, "rb") as f:
        while bloc := f.read(1 << 20):
            crc = zlib.crc32(bloc, crc)
    cache = Path(os.environ.get("LECTURA_CACHE_DIR") or Path.home() / ".lectura" / "cache")
    cible = cache / "lexicon_en" / f"{source.parent.name}-{crc:08x}" / "lexicon.db"
    return cible if cible.exists() else installer(source, cible)
