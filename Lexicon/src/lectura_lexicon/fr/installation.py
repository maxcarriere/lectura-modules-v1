# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Données livrées compressées (``lexicon.tsv.xz``) et installées au premier usage en ``lexicon.db``.

La taille ``mini`` est livrée sous forme de source : une ligne JSON de métadonnées, puis une ligne par forme
(triées), séparées par des tabulations :

    ortho  zipf×100  zipf_lemme×100  drapeaux  clés phonétiques (espaces)  graphie usuelle (variantes)

Une clé précédée de « ~ » ne vient que de lectures masquées (lettre épelée, abréviation) : ``phones.masquee``.

``installer`` en tire la base sqlite (schéma ``donnees.SCHEMA``, sans analyses) et recalcule les index des voisins
(suppressions de lettres et de phonèmes), qui font l'essentiel de la taille : quelques Mo livrés au lieu de 90.
La base installée va dans le cache (``LECTURA_CACHE_DIR`` ou ``~/.lectura/cache``), sous ``lexicon/<empreinte>/``.
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
    """``formes`` : (ortho, zipf, zipf_lemme, drapeaux, clés phonétiques, usuelle), triées par graphie."""
    with lzma.open(chemin, "wt", encoding="utf-8", preset=9 | lzma.PRESET_EXTREME) as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for ortho, zipf, zl, drapeaux, cles, usuelle in formes:
            f.write(f"{ortho}\t{round(zipf * 100)}\t{round(zl * 100)}\t{drapeaux}\t{' '.join(cles)}\t{usuelle}\n")


def lire_source(chemin: Path) -> tuple[dict, list[tuple]]:
    with lzma.open(chemin, "rt", encoding="utf-8") as f:
        meta = json.loads(f.readline())
        formes = []
        for ligne in f:
            ortho, zipf, zl, drapeaux, cles, usuelle = ligne.rstrip("\n").split("\t")
            formes.append((ortho, int(zipf) / 100, int(zl) / 100, int(drapeaux), cles.split() if cles else [], usuelle))
    return meta, formes


_BITS, _DECALAGE = 24, 1 << 31      # numéros < 16 M ; empreintes signées 32 bits ramenées en positif


def _couples(codes: set[int]):
    """Couples (empreinte, numéro) triés, depuis leurs codes entiers."""
    masque = (1 << _BITS) - 1
    return (((c >> _BITS) - _DECALAGE, c & masque) for c in sorted(codes))


def installer(source: Path, cible: Path) -> Path:
    """Construit ``cible`` (sqlite) depuis la source compressée ; écrit à côté puis renomme (installation sûre)."""
    meta, formes = lire_source(source)
    if len(formes) >= 1 << _BITS:
        raise ValueError("trop de formes pour le codage des voisins")
    zipf_voisins, n_suppr = float(meta["zipf_voisins"]), int(meta["suppressions"])
    cible.parent.mkdir(parents=True, exist_ok=True)
    provisoire = cible.with_name(f"{cible.name}.{os.getpid()}.tmp")
    provisoire.unlink(missing_ok=True)
    db = sqlite3.connect(provisoire)
    db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA)
    ids_cles: dict[str, int] = {}
    rangs_formes, rangs_phones, usuelles = [], [], []
    cles_voisines: set[int] = set()
    # couples (empreinte, numéro) codés en un entier (tri et ensemble bien plus rapides que sur des tuples)
    voisins: set[int] = set()
    for i, (ortho, zipf, zl, drapeaux, cles, usuelle) in enumerate(formes):
        numeros = []
        for c in cles:
            masquee = c.startswith("~")
            k = ids_cles.setdefault(c[1:] if masquee else c, len(ids_cles))
            rangs_phones.append((k, i, int(masquee)))
            if masquee:
                continue
            numeros.append(k)
            if zipf >= zipf_voisins and not drapeaux & NON_VALIDE:
                cles_voisines.add(k)
        mini = minuscule(ortho)
        rangs_formes.append((i, ortho, mini, zipf, zl, drapeaux, " ".join(map(str, numeros)), None))
        if usuelle:
            usuelles.append((i, usuelle))
        if (zipf >= zipf_voisins and " " not in mini and len(mini) >= 2
                and not drapeaux & (SPECIAL | NON_VALIDE)):
            voisins.update(((empreinte(s) + _DECALAGE) << _BITS) | i for s in suppressions(mini, n_suppr))
    db.executemany("INSERT INTO formes VALUES (?,?,?,?,?,?,?,?)", rangs_formes)
    db.executemany("INSERT INTO usuelles VALUES (?,?)", usuelles)
    db.executemany("INSERT INTO cles_phone VALUES (?,?,?)", [(k, c, inverse(c)) for c, k in ids_cles.items()])
    db.executemany("INSERT INTO phones VALUES (?,?,?)", sorted(set(rangs_phones)))
    db.executemany("INSERT INTO voisins VALUES (?,?)", _couples(voisins))
    voisins = {((empreinte(s) + _DECALAGE) << _BITS) | k for c, k in ids_cles.items() if k in cles_voisines
               for s in suppressions(phonemes(c), n_suppr)}
    db.executemany("INSERT INTO voisins_phones VALUES (?,?)", _couples(voisins))
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
    cible = cache / "lexicon" / f"{source.parent.name}-{crc:08x}" / "lexicon.db"
    return cible if cible.exists() else installer(source, cible)
