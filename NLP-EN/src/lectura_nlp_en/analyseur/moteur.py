# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Moteurs de l'Analyseur anglais : ``MoteurLocal`` (modèles ONNX sur la machine) et ``MoteurAPI`` (API publique
de Lectura). Mêmes méthodes : ``lire``, ``ecrire``, ``decouper`` ; ``chaine`` (la chaîne locale, ou ``None``).

- ``local`` : modèle de phrase et tête de sélection, modèle de mot et lexique embarqué, dans un dossier de modèles
  (``models_dir``, ``LECTURA_NLP_EN_DIR``, ``LECTURA_MODELS_DIR``/transducer_en, ``~/.lectura/models/transducer_en``) ; **aucun appel
  réseau** ; erreur ``ModelesAbsents`` si les modèles manquent ;
- ``api`` : ``POST /v1/lire`` et ``/v1/ecrire`` (le texte part sur le serveur de Lectura) ;
- ``auto`` : local si les modèles sont là, sinon API, avec un ``AvertissementNLP``.

Le découpage (``decouper``) et les formules ne demandent aucun modèle et restent toujours locaux. Le paquet ne
contient aucun modèle : ils sont servis par l'API ou remis avec la licence commerciale.
"""

from __future__ import annotations

import hashlib
import lzma
import os
import shutil
import warnings
from pathlib import Path

from ..erreurs import AvertissementNLP, ModelesAbsents
from .decoupage_texte import decouper

LANGUE_CODE = "en"
FICHIERS = ("analyseur.onnx", "analyseur_vocabs.json", "selection.onnx", "modele_mot_preparation.onnx",
            "modele_mot_pas.onnx", "modele_mot_vocabs.json", "lexique.db")
MODES = ("auto", "local", "api")


def _present(dossier: Path, nom: str) -> bool:
    return (dossier / nom).exists() or (dossier / f"{nom}.xz").exists()


def fichier(dossier: Path, nom: str) -> Path:
    """Chemin utilisable d'un fichier des modèles ; un ``.xz`` est décompressé une fois dans le cache."""
    if (dossier / nom).exists():
        return dossier / nom
    archive = dossier / f"{nom}.xz"
    empreinte = hashlib.sha1(f"{archive.resolve()}:{archive.stat().st_size}:{archive.stat().st_mtime_ns}".encode()).hexdigest()[:12]
    cache = Path(os.environ.get("LECTURA_CACHE_DIR") or Path.home() / ".lectura" / "cache") / "transducer_en" / empreinte
    cible = cache / nom
    if not cible.exists():
        cache.mkdir(parents=True, exist_ok=True)
        provisoire = cible.with_suffix(cible.suffix + ".part")
        with lzma.open(archive) as source, provisoire.open("wb") as sortie:
            shutil.copyfileobj(source, sortie, 1 << 20)
        provisoire.replace(cible)
    return cible


def dossier_modeles(models_dir: str | Path | None = None) -> Path | None:
    """Premier dossier qui contient tous les fichiers des modèles, ou ``None``."""
    candidats = []
    if models_dir:
        candidats.append(Path(models_dir))
    if os.environ.get("LECTURA_NLP_EN_DIR"):
        candidats.append(Path(os.environ["LECTURA_NLP_EN_DIR"]))
    if os.environ.get("LECTURA_MODELS_DIR"):
        candidats.append(Path(os.environ["LECTURA_MODELS_DIR"]) / "transducer_en")
    candidats.append(Path.home() / ".lectura" / "models" / "transducer_en")
    return next((d for d in candidats if all(_present(d, f) for f in FICHIERS)), None)


_FORMAT = ("x_entier", "doubles")


def _options_format(options: dict) -> dict:
    """Retire de ``options`` celles du format linéaire (``PhraseAlignee.lineaire``) et les rend à part."""
    return {k: options.pop(k) for k in _FORMAT if k in options}


class _MoteurChaine:
    chaine = None

    def lire(self, texte: str, **options) -> list[dict]:
        """Texte → phrases alignées (orthographe, phonétique, alignement linéaire, analyse de chaque mot).
        Option du format linéaire : ``doubles`` (coupe des lettres doubles ``hap.p°y``, désactivée par défaut)."""
        format_ = _options_format(options)
        return [p.vers_dict(**format_) for p in self.chaine.lire(texte, **options)]

    def ecrire(self, phone: str, **options) -> list[dict]:
        """Phonétique (mots séparés par des espaces, « . » « ˈ » « ˌ » « ‿ » facultatifs) → phrases alignées."""
        format_ = _options_format(options)
        return [p.vers_dict(**format_) for p in self.chaine.ecrire(phone, **options)]

    @staticmethod
    def decouper(texte: str) -> list[list[dict]]:
        return [[vars(m) for m in p] for p in decouper(texte)]


class MoteurLocal(_MoteurChaine):
    """Toute la chaîne sur la machine, sans torch : modèle de phrase et tête de sélection (``analyseur.onnx``,
    ``selection.onnx``), modèle de mot (``modele_mot_*.onnx``) et lexique embarqué (``lexique.db``) du dossier."""

    mode = "local"

    def __init__(self, dossier: Path, fils: int = 1, **options):
        from .adaptateurs.analyseur_onnx import AnalyseurOnnx
        from .chaine import Chaine
        from .correctifs import appliquer as avec_correctifs
        from .lexique_embarque import LexiqueEmbarque
        from .modele_mot import ModeleDeMotOnnx

        dossier = Path(dossier)
        self.dossier = dossier
        lex = avec_correctifs(LexiqueEmbarque(fichier(dossier, "lexique.db")))
        self.lexique = lex
        self.chaine = Chaine(AnalyseurOnnx(lex, dossier, fils=fils), lex, ModeleDeMotOnnx(dossier, fils=fils), **options)


def MoteurAPI(api: str | None = None, cle: str | None = None, delai: float = 30.0, client=None, **options):
    """Analyseur calculé par l'API (``/v1/lire``, ``/v1/ecrire``) : ``lectura_nlp_en.api.AnalyseurAPI``."""
    from ..api import AnalyseurAPI

    return AnalyseurAPI(api, cle, delai, client=client, **options)


def message_modeles_absents(models_dir=None) -> str:
    return ("Modèles de l'Analyseur anglais introuvables (models_dir"
            f"{f' = {models_dir}' if models_dir else ''}, LECTURA_NLP_EN_DIR, LECTURA_MODELS_DIR/transducer_en, "
            "~/.lectura/models/transducer_en). Le paquet ne contient aucun modèle : utilisez l'API (mode « api » "
            "ou « auto ») ou les modèles remis avec la licence commerciale (contact via https://www.lectura.world).")


def creer_moteur(mode: str = "auto", models_dir: str | Path | None = None, api: str | None = None,
                 cle: str | None = None, fils: int = 1, delai: float = 30.0, **options):
    """``mode`` : ``auto``, ``local`` ou ``api`` (voir le module). ``options`` : celles de la chaîne,
    ``enchainements`` (vrai), ``formes_fortes`` (vrai). ``api`` / ``cle`` : adresse et clé de l'API
    (``LECTURA_API_URL``, ``LECTURA_API_KEY``) ; ``fils`` : fils d'exécution d'onnxruntime (local)."""
    if mode not in MODES:
        raise ValueError(f"mode « {mode} » : attendu {', '.join(MODES)}")
    if mode == "api":
        return MoteurAPI(api, cle, delai, **options)
    dossier = dossier_modeles(models_dir)
    if dossier is not None:
        return MoteurLocal(dossier, fils=fils, **options)
    if mode == "local":
        raise ModelesAbsents(message_modeles_absents(models_dir))
    warnings.warn("Analyseur anglais : modèles absents en local, calcul par l'API publique de Lectura (le texte part "
                  "sur le serveur). mode=\"local\" pour l'interdire.", AvertissementNLP, stacklevel=2)
    return MoteurAPI(api, cle, delai, **options)
