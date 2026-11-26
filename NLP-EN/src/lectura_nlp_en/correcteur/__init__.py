# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Correcteur de l'anglais (fonction Correcteur de ``lectura-nlp-en``, extra ``[correcteur]``) : orthographe et
grammaire, pédagogique (chaque correction a son explication, en français ou en anglais).

    from lectura_nlp_en import creer_moteur
    nlp = creer_moteur()
    r = nlp.corriger("He go to school and their happy.", mode="suggestions")     # ou « automatique »
    r.texte                                                # « He goes to school and they're happy. »

En local, ``charger`` assemble : la chaîne de l'Analyseur anglais (découpage, analyse UD, prononciation), Lexicon
anglais en local (``lectura-lexicon``, base de taille standard) et un modèle de langue écrit (``langue.bin``, KenLM
4-grammes, livrable en ``langue.bin.xz``, décompressé une fois dans le cache). Dossier des modèles du correcteur, dans
l'ordre : ``models_dir``, ``LECTURA_CORRECTEUR_EN_DIR``, ``LECTURA_MODELS_DIR``/corrector_en, ``~/.lectura/models/corrector_en``. La tête de graphie
(``tete/``, livrée à part) est cherchée dans les mêmes dossiers ; sans elle, KenLM seul juge les homophones. Le paquet
ne contient aucun modèle : ils sont servis par l'API publique de Lectura ou remis avec la licence commerciale.
"""

from __future__ import annotations

import lzma
import os
import shutil
from pathlib import Path

from .coeur import Correcteur, Correction, Resultat

__version__ = "1.0.0"
__all__ = ["Correcteur", "Correction", "Resultat", "charger", "dossier_modeles", "dossier_tete", "__version__"]

FICHIERS = ("langue.bin",)


def _present(dossier: Path, nom: str) -> bool:
    return (dossier / nom).exists() or (dossier / f"{nom}.xz").exists()


def _candidats(models_dir: str | Path | None = None) -> list[Path]:
    candidats = []
    if models_dir:
        candidats.append(Path(models_dir))
    if os.environ.get("LECTURA_CORRECTEUR_EN_DIR"):
        candidats.append(Path(os.environ["LECTURA_CORRECTEUR_EN_DIR"]))
    if os.environ.get("LECTURA_MODELS_DIR"):
        candidats.append(Path(os.environ["LECTURA_MODELS_DIR"]) / "corrector_en")
    candidats.append(Path.home() / ".lectura" / "models" / "corrector_en")
    return candidats


def dossier_modeles(models_dir: str | Path | None = None) -> Path | None:
    return next((d for d in _candidats(models_dir) if all(_present(d, f) for f in FICHIERS)), None)


def dossier_tete(models_dir: str | Path | None = None) -> Path | None:
    """Premier dossier ``tete/`` (graphe à canal par mot + vocabulaires) des dossiers de modèles."""
    return next((d / "tete" for d in _candidats(models_dir) if (d / "tete" / "analyseur.onnx").exists()), None)


def fichier(dossier: Path, nom: str) -> Path:
    """Le fichier, décompressé une fois dans le cache s'il n'est livré qu'en ``.xz``."""
    if (dossier / nom).exists():
        return dossier / nom
    cache = Path(os.environ.get("LECTURA_CACHE_DIR") or Path.home() / ".lectura" / "cache") / "corrector_en"
    cible = cache / nom
    if not cible.exists():
        cache.mkdir(parents=True, exist_ok=True)
        provisoire = cible.with_suffix(".tmp")
        with lzma.open(dossier / f"{nom}.xz") as src, provisoire.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        provisoire.replace(cible)
    return cible


def charger(models_dir: str | Path | None = None, transducer_dir: str | Path | None = None, lexique=None,
            chaine=None, tete=None, **options) -> Correcteur:
    """Assemble le correcteur, tout en local (aucun appel réseau) : chaîne de l'Analyseur anglais (locale, ou celle
    donnée), Lexicon anglais local (taille standard, ou l'objet donné), modèle de langue écrit, et tête de graphie
    (``tete/`` d'un dossier des modèles, s'il y est, ou le dossier donné ; ``tete=False`` : sans, KenLM seul juge les
    homophones)."""
    from ..analyseur.moteur import creer_moteur

    from .langue import Juge

    dossier = dossier_modeles(models_dir)
    if dossier is None:
        raise FileNotFoundError("Modèle de langue du correcteur anglais introuvable (models_dir, LECTURA_CORRECTEUR_EN_DIR, "
                                "LECTURA_MODELS_DIR/corrector_en, ~/.lectura/models/corrector_en). Le paquet ne "
                                "contient aucun modèle : utilisez l'API (mode « api ») ou les modèles remis avec la "
                                "licence commerciale.")
    if chaine is None:
        chaine = creer_moteur("local", models_dir=transducer_dir).chaine
    if lexique is None:
        from lectura_lexicon import Lexicon

        lexique = Lexicon(langue="en", mode="local", taille="standard")
    if tete is None or isinstance(tete, (str, Path)):
        tete = Path(tete) if tete is not None else dossier_tete(models_dir)
    if isinstance(tete, Path):
        from .tete import TeteGraphie

        tete = TeteGraphie(tete, correction=0.0, fils=int(os.environ.get("LECTURA_CORRECTEUR_FILS", "1")))
    return Correcteur(chaine, _Cache(lexique), Juge(fichier(dossier, "langue.bin")), tete=tete or None, **options)


class _Cache:
    """Mémoïsation des appels au lexique (les mêmes formes reviennent sans cesse) ; le reste est délégué."""

    def __init__(self, lexique, taille: int = 50_000):
        from functools import lru_cache

        self._lex = lexique
        for nom in ("lectures", "validite", "frequence", "usuelle", "homophones", "conjuguer", "americaine",
                    "voisins_orthographiques", "formes_de"):
            setattr(self, nom, lru_cache(maxsize=taille)(getattr(lexique, nom)))

    def variante(self, forme: str, toutes: bool = False, **traits):
        return self._variante(forme, toutes, tuple(sorted(traits.items())))

    def _variante(self, forme, toutes, traits):
        return self._lex.variante(forme, toutes, **dict(traits))

    def __getattr__(self, nom):
        return getattr(self._lex, nom)
