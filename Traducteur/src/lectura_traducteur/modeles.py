# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Dossier des modèles du Traducteur (mode local). **Le paquet ne contient aucun modèle.**

Ordre de recherche : ``models_dir`` donné, ``LECTURA_MODELS_DIR/traducteur``, ``LECTURA_MODELS_DIR/translator``,
``~/.lectura/models/traducteur``, ``~/.lectura/models/translator`` (nom des versions 0.1, gardé pour les serveurs
déjà installés). Un dossier compte s'il contient au moins un modèle de traduction ``opus-mt-*-int8``.

Contenu attendu ::

    traducteur/
      opus-mt-en-fr-int8/        CTranslate2 int8 + source.spm, target.spm   (Apache 2.0)
      opus-mt-fr-en-int8/
      opus-mt-tc-big-en-fr-int8/ (facultatif, taille="big", CC BY 4.0)
      opus-mt-tc-big-fr-en-int8/
      mbert8/                    mbert8_int8.onnx + tokenizer.json          (aligneur précis, Apache 2.0)
      glossaire.db               (facultatif, gloser ; Wiktionnaires, CC BY-SA 4.0)
"""
from __future__ import annotations

import os
from pathlib import Path

NOMS = {
    ("fr", "en"): {"base": "opus-mt-fr-en", "big": "opus-mt-tc-big-fr-en"},
    ("en", "fr"): {"base": "opus-mt-en-fr", "big": "opus-mt-tc-big-en-fr"},
}
PAIRES = tuple(NOMS)
TAILLES = ("base", "big")


class ModelesAbsents(FileNotFoundError):
    """Modèles du Traducteur introuvables en mode local (aucun appel réseau n'est tenté)."""


def candidats(models_dir: str | Path | None = None) -> list[Path]:
    liste = []
    if models_dir:
        liste.append(Path(models_dir))
    env = os.environ.get("LECTURA_MODELS_DIR")
    if env:
        liste += [Path(env) / "traducteur", Path(env) / "translator"]
    maison = Path.home() / ".lectura" / "models"
    liste += [maison / "traducteur", maison / "translator"]
    return liste


def trouver_modeles(models_dir: str | Path | None = None) -> Path | None:
    """Premier dossier qui contient un modèle de traduction, ou ``None``. Si ``models_dir`` est donné, lui seul."""
    for c in (candidats(models_dir)[:1] if models_dir else candidats()):
        if c.is_dir() and any(c.glob("opus-mt-*-int8")):
            return c
    return None


def dossier_modeles(models_dir: str | Path | None = None) -> Path:
    d = trouver_modeles(models_dir)
    if d is None:
        lieux = ", ".join(str(c) for c in (candidats(models_dir)[:1] if models_dir else candidats()))
        raise ModelesAbsents(
            f"Modèles du Traducteur introuvables ({lieux}). Le paquet n'en contient aucun : ils sont fournis avec la "
            "licence commerciale. Sans modèles, utilisez l'API publique de Lectura : Traducteur(..., mode=\"api\").")
    return d


def dossier_traduction(source: str, cible: str, taille: str = "base", models_dir: str | Path | None = None) -> Path:
    if (source, cible) not in NOMS:
        raise ValueError(f"paire non prise en charge : {source} → {cible} (fr → en, en → fr)")
    if taille not in TAILLES:
        raise ValueError(f"taille « {taille} » : base ou big")
    d = dossier_modeles(models_dir) / f"{NOMS[(source, cible)][taille]}-int8"
    if not d.is_dir():
        raise ModelesAbsents(f"{d} absent (sens {source} → {cible}, taille « {taille} » non installée)")
    return d


def modeles_presents(source: str, cible: str, taille: str = "base", models_dir: str | Path | None = None) -> bool:
    try:
        dossier_traduction(source, cible, taille, models_dir)
        return True
    except (ModelesAbsents, ValueError):
        return False
