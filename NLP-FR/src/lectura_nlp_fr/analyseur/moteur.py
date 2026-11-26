# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Point d'entrée de l'Analyseur : ``creer_moteur()`` (chaîne texte ⇄ phonétique, analyse grammaticale).

L'entrée publique du module est ``lectura_nlp_fr.creer_moteur`` (modes local, API, dégradé) ; celle-ci reste pour
les programmes qui importaient ``lectura_transducer`` (serveur, voix).

Dossier des modèles (jamais dans le paquet), dans l'ordre : ``models_dir``, ``LECTURA_NLP_FR_DIR``,
``LECTURA_MODELS_DIR``/transducer, ``~/.lectura/models/transducer``.

Le lexique embarqué peut être livré compressé (``lexique.db.xz``, ``index_phone.db.xz``) : il est décompressé au
premier usage dans ``~/.lectura/cache/transducer`` (ou ``LECTURA_CACHE_DIR``).

Le découpage (``decouper``) et les formules ne demandent aucun modèle et fonctionnent toujours en local.
"""

from __future__ import annotations

import hashlib
import lzma
import os
import shutil
import warnings
from pathlib import Path

from .decoupage_texte import decouper

FICHIERS = ("analyseur.onnx", "analyseur_vocabs.json", "modele_mot_preparation.onnx", "modele_mot_pas.onnx",
            "modele_mot_vocabs.json", "lexique.db", "index_phone.db")
LANGUE = "langue.npz"


def _present(dossier: Path, nom: str) -> bool:
    return (dossier / nom).exists() or (dossier / f"{nom}.xz").exists()


def fichier(dossier: Path, nom: str) -> Path:
    """Chemin utilisable d'un fichier des modèles ; un ``.xz`` est décompressé une fois dans le cache."""
    if (dossier / nom).exists():
        return dossier / nom
    archive = dossier / f"{nom}.xz"
    empreinte = hashlib.sha1(f"{archive.resolve()}:{archive.stat().st_size}:{archive.stat().st_mtime_ns}".encode()).hexdigest()[:12]
    cache = Path(os.environ.get("LECTURA_CACHE_DIR") or Path.home() / ".lectura" / "cache") / "transducer" / empreinte
    cible = cache / nom
    if not cible.exists():
        cache.mkdir(parents=True, exist_ok=True)
        provisoire = cible.with_suffix(cible.suffix + ".part")
        with lzma.open(archive) as source, provisoire.open("wb") as sortie:
            shutil.copyfileobj(source, sortie, 1 << 20)
        provisoire.replace(cible)
    return cible


def dossier_modeles(models_dir: str | Path | None = None) -> Path | None:
    candidats = []
    if models_dir:
        candidats.append(Path(models_dir))
    if os.environ.get("LECTURA_NLP_FR_DIR"):
        candidats.append(Path(os.environ["LECTURA_NLP_FR_DIR"]))
    if os.environ.get("LECTURA_MODELS_DIR"):
        candidats.append(Path(os.environ["LECTURA_MODELS_DIR"]) / "transducer")
    candidats.append(Path.home() / ".lectura" / "models" / "transducer")
    return next((d for d in candidats if all(_present(d, f) for f in FICHIERS)), None)


def fichiers_manquants(dossier: str | Path) -> list[str]:
    """Fichiers des modèles de l'Analyseur absents de ``dossier`` (pour un message d'erreur clair)."""
    return [f for f in FICHIERS if not _present(Path(dossier), f)]


_FORMAT = ("x_entier", "doubles")


def _options_format(options: dict) -> dict:
    """Retire de ``options`` celles du format linéaire (``PhraseAlignee.lineaire``) et les rend à part."""
    return {k: options.pop(k) for k in _FORMAT if k in options}


# Ressources lourdes (modèles ONNX, lexique, index) chargées une fois par dossier et partagées par tous les moteurs :
# un serveur qui garde un moteur par jeu d'options ne les recharge pas (≈ 120 Mo chacun).
_RESSOURCES: dict[Path, tuple] = {}


def _ressources(dossier: Path) -> tuple:
    cle = dossier.resolve()
    if cle not in _RESSOURCES:
        from . import correctifs
        from .adaptateurs.analyseur_onnx import AnalyseurOnnx
        from .index_phone import IndexSqlite
        from .lexique_embarque import LexiqueEmbarque
        from .modele_mot import ModeleDeMotOnnx

        langue = None
        if (dossier / LANGUE).exists():
            from .modele_langue import ModeleLangue

            langue = ModeleLangue(dossier / LANGUE)
        lexique = fichier(dossier, "lexique.db")
        # Correctifs manuels (data/correctifs.tsv) prioritaires sur le lexique embarqué.
        lexique, index = correctifs.appliquer(LexiqueEmbarque(lexique.parent), IndexSqlite(fichier(dossier, "index_phone.db")))
        # Supplément d'écriture (mots rares, noms propres), consulté seulement dans le sens phonétique → orthographe.
        from . import supplement

        lexique, index = supplement.appliquer(lexique, index, dossier)
        _RESSOURCES[cle] = (AnalyseurOnnx(dossier), lexique, ModeleDeMotOnnx(dossier), index, langue)
    return _RESSOURCES[cle]


# Modèle de langue écrit de la relecture (``relecture.py``), chargé une fois par dossier ; None si absent ou sans kenlm.
_ECRIT: dict[Path, object] = {}


def _langue_ecrite(dossier: Path):
    cle = dossier.resolve()
    if cle not in _ECRIT:
        from . import relecture

        _ECRIT[cle] = relecture.charger(dossier / relecture.FICHIER) if (dossier / relecture.FICHIER).exists() else None
    return _ECRIT[cle]


# Juge des homophones (``juge.py``, facultatif, livré à part), chargé une fois par dossier de modèles ; None s'il
# n'est pas installé.
_JUGES: dict[Path, object] = {}


def _juge(dossier: Path):
    cle = dossier.resolve()
    if cle not in _JUGES:
        from . import juge

        trouve = juge.trouver(dossier)
        _JUGES[cle] = juge.Juge.charger(trouve) if trouve is not None else None
    return _JUGES[cle]


class MoteurLocal:
    """Toute la chaîne sur la machine : modèles ONNX, lexique embarqué, modèle de langue (s'il est présent)."""

    def __init__(self, dossier: Path, relecture: bool = True, poids_relecture: float | None = None,
                 juge: bool = True, poids_juge: float | None = None, ecriture: bool = True, **options):
        """``ecriture=False`` : Analyseur pour la lecture seule (``lire``, ``analyser``) ; le juge et le supplément
        d'écriture ne sont ni cherchés ni signalés, et ``ecrire`` lève ``FonctionIndisponible``."""
        from .chaine import Chaine
        from . import supplement

        self.ecriture = ecriture
        if not ecriture:
            juge = relecture = False
        elif supplement.trouver(dossier) is None:
            from . import AvertissementNLP

            warnings.warn(f"Analyseur : supplément d'écriture ({supplement.FICHIER}[.xz]) absent de {dossier} : "
                          "l'écriture des mots rares et des noms propres est moins bonne.", AvertissementNLP, stacklevel=3)

        analyseur, lexique, modele_mot, index, langue = _ressources(dossier)
        if langue is not None:
            # Modèle de langue des homophones facultatif (non livré avec l'analyseur v3) : poids faible, 0,2 au plus
            # d'après les mesures du 9/10.
            options.setdefault("poids_langue", 0.2)
        self.chaine = Chaine(analyseur, lexique, modele_mot, index=index, langue=langue, **options)
        # Relecture de l'écriture (phonétique → orthographe) par le modèle de langue écrit, s'il est livré.
        ecrit = _langue_ecrite(dossier) if relecture else None
        if ecrit is not None:
            from .relecture import POIDS, Relecture

            Relecture(ecrit, POIDS if poids_relecture is None else poids_relecture).brancher(self.chaine)
        # Juge des homophones (``juge.py``), s'il est livré : il remplace la relecture (mesuré meilleur).
        juge_homophones = _juge(dossier) if juge else None
        self.juge = juge_homophones
        if juge and juge_homophones is None:
            from . import AvertissementNLP

            warnings.warn("Analyseur : juge des homophones introuvable (LECTURA_JUGE_DIR, <modèles>/juge, "
                          "$LECTURA_MODELS_DIR/juge, ~/.lectura/models/juge) : l'écriture se fait SANS juge, "
                          "nettement moins bonne sur les homophones (a / à, ces / ses…).", AvertissementNLP, stacklevel=3)
        if juge_homophones is not None:
            from .juge import POIDS as POIDS_JUGE

            juge_homophones.poids = POIDS_JUGE if poids_juge is None else poids_juge
            juge_homophones.brancher(self.chaine)

    def lire(self, texte: str, **options) -> list[dict]:
        """Texte → phrases alignées (orthographe, phonétique, alignement linéaire, analyse de chaque mot).
        Options de la chaîne, et du format linéaire (``x_entier``, ``doubles`` : syllabation orthographique)."""
        format_ = _options_format(options)
        return [p.vers_dict(**format_) for p in self.chaine.lire(texte, **options)]

    def ecrire(self, phone: str, **options) -> list[dict]:
        """Phonétique (mots séparés par des espaces, « . » et « ‿ » facultatifs) → phrases alignées."""
        if not self.ecriture:
            from ..erreurs import FonctionIndisponible

            raise FonctionIndisponible("Analyseur créé pour la lecture seule (ecriture=False) : ecrire indisponible.")
        format_ = _options_format(options)
        return [p.vers_dict(**format_) for p in self.chaine.ecrire(phone, **options)]

    @staticmethod
    def decouper(texte: str) -> list[list[dict]]:
        return [[vars(m) for m in p] for p in decouper(texte)]


def creer_moteur(mode: str = "auto", models_dir: str | Path | None = None, **options):
    """``mode`` : ``auto`` (local si les modèles sont présents, sinon API, avec un avertissement), ``local`` (jamais de
    réseau ; erreur claire si les modèles manquent) ou ``api`` (``POST /v1/lire`` et ``/v1/ecrire``).
    ``options`` (local) : celles de la chaîne — ``e_caduc``, ``schwas_finaux``, ``liaisons``, ``enchainements``,
    ``elisions``, ``politique`` ; ``relecture`` (défaut True : relecture de l'écriture par le modèle de langue écrit,
    si ``langue_ecrite.bin`` est livré et ``kenlm`` installé), ``poids_relecture`` ; ``juge`` (défaut True : juge des
    homophones, s'il est installé — ``juge.trouver`` ; il remplace alors la relecture ; absent, un avertissement le
    dit), ``poids_juge``."""
    if mode not in ("auto", "local", "api"):
        raise ValueError(f"mode « {mode} » : attendu auto, local ou api")
    if mode == "api":
        from ..api import AnalyseurAPI

        options.pop("ecriture", None)
        return AnalyseurAPI(**options)
    dossier = dossier_modeles(models_dir)
    if dossier is None and mode == "local":
        from . import ModelesAbsents

        raise ModelesAbsents(message_modeles_absents(models_dir))
    if dossier is None:
        from ..api import AnalyseurAPI
        from . import AvertissementNLP

        warnings.warn("Analyseur : modèles locaux introuvables, passage à l'API publique de Lectura (les textes sont "
                      "envoyés au serveur). Pour rester sur la machine : mode=\"local\" avec les modèles installés.",
                      AvertissementNLP, stacklevel=2)
        return AnalyseurAPI()
    return MoteurLocal(dossier, **options)


def message_modeles_absents(models_dir: str | Path | None = None) -> str:
    ou = f"{models_dir} (manquent : {', '.join(fichiers_manquants(models_dir))}), " if models_dir else ""
    return ("Modèles de l'Analyseur introuvables : " + ou + "LECTURA_NLP_FR_DIR, $LECTURA_MODELS_DIR/transducer, "
            "~/.lectura/models/transducer. Le paquet ne contient aucun modèle : ils sont servis par l'API publique "
            "(mode=\"api\") ou livrés avec la licence commerciale (contact via https://www.lectura.world).")
