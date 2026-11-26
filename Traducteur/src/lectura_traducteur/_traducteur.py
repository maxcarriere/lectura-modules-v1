# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""``Traducteur`` : choix du mode (local, API, auto) et interface commune.

- ``mode="local"`` : modèles sur la machine ; **aucun appel réseau, jamais**, même en cas d'erreur ;
- ``mode="api"`` : l'API publique de Lectura calcule ; **le texte est envoyé au serveur de Lectura** ;
- ``mode="auto"`` (défaut) : local si les modèles du sens demandé sont installés (et CTranslate2 importable), sinon
  API, avec un avertissement (``UserWarning``) qui le dit. ``traducteur.mode`` donne le mode retenu.

Le mode se fixe aussi par la variable ``LECTURA_TRADUCTEUR_MODE`` (``local``, ``api`` ou ``auto``). ``models_dir=``
impose le mode local ; ``api=`` ou ``cle=`` imposent le mode API.
"""
from __future__ import annotations

import importlib.util
import os
import warnings

from .modeles import PAIRES, modeles_presents

MODES = ("auto", "local", "api")


def verifier_paire(source: str, cible: str) -> tuple[str, str]:
    if (source, cible) not in PAIRES:
        raise ValueError(f"paire non prise en charge : {source} → {cible} (fr → en, en → fr)")
    return source, cible


def _local_importable() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in ("ctranslate2", "sentencepiece"))


def choisir_mode(source: str = "en", cible: str = "fr", mode: str | None = None, taille: str = "base",
                 models_dir=None, api: str | None = None, cle: str | None = None) -> tuple[str, str]:
    """(mode retenu, raison). Ne fait aucun appel réseau."""
    demande = mode or os.environ.get("LECTURA_TRADUCTEUR_MODE") or "auto"
    if demande not in MODES:
        raise ValueError(f"mode « {demande} » : attendu {', '.join(MODES)}")
    if demande != "auto":
        return demande, "demandé"
    if models_dir is not None:
        return "local", "models_dir donné"
    if api is not None or cle is not None:
        return "api", "adresse ou clé d'API donnée"
    if not modeles_presents(source, cible, taille):
        return "api", f"modèles du sens {source} → {cible} (taille {taille}) absents de cette machine"
    if not _local_importable():
        return "api", "CTranslate2 ou sentencepiece absent (pip install \"lectura-traducteur[local]\")"
    return "local", "modèles installés"


class Traducteur:
    """Traducteur français ⇄ anglais de Lectura.

    ``Traducteur(source, cible, mode=None, taille="base", aligneur="precis", fils=4, gpu=False, models_dir=None,
    api=None, cle=None, delai=None)`` rend un ``TraducteurLocal`` ou un ``TraducteurAPI`` (sous-classes de
    ``Traducteur``), qui ont les mêmes fonctions et les mêmes résultats :

    - ``traduire(texte, aligner=False, formules=True)`` → ``{"texte", "phrases": [{"source", "debut", "fin",
      "traduction"}]}`` ; avec ``aligner``, chaque phrase a aussi ``mots_source``, ``mots_cible`` et ``liens``
      (couples (i mot source, j mot cible)) ;
    - ``aligner(mots_source, mots_cible)`` → ensemble de couples (i, j) ;
    - ``gloser(texte)`` → pour chaque phrase, sa traduction et, pour chaque mot, lemme, catégorie, prononciation,
      mots qui le traduisent ici et sens retenu (glossaire en contexte) ;
    - ``infos()`` → version, paires, tailles, limites.
    """

    source: str = "en"
    cible: str = "fr"
    mode: str = ""
    raison_mode: str = ""

    def __new__(cls, source: str = "en", cible: str = "fr", mode: str | None = None, *args, **kwargs):
        if cls is Traducteur:
            choisi, raison = choisir_mode(source, cible, mode, kwargs.get("taille", "base"),
                                          kwargs.get("models_dir"), kwargs.get("api"), kwargs.get("cle"))
            demande = mode or os.environ.get("LECTURA_TRADUCTEUR_MODE") or "auto"
            if demande == "auto" and choisi == "api":
                from .api import adresse_api
                warnings.warn(
                    f"Traducteur : {raison} ; passage à l'API de Lectura : les textes à traduire sont envoyés à "
                    f"{adresse_api(kwargs.get('api'))}. Pour l'éviter : mode=\"local\" (modèles sous licence) ou "
                    "LECTURA_TRADUCTEUR_MODE=local.", UserWarning, stacklevel=2)
            if choisi == "local":
                from .local import TraducteurLocal as cls
            else:
                from .api import TraducteurAPI as cls
            objet = super().__new__(cls)
            objet.raison_mode = raison
            return objet
        return super().__new__(cls)

    def traduire(self, texte: str, aligner: bool = False, formules: bool = True) -> dict:
        raise NotImplementedError

    def aligner(self, mots_source: list[str], mots_cible: list[str]) -> set[tuple[int, int]]:
        raise NotImplementedError

    def gloser(self, texte: str) -> list[dict]:
        raise NotImplementedError

    def infos(self) -> dict:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.source!r} → {self.cible!r}, mode={self.mode!r})"


def creer_moteur(source: str = "en", cible: str = "fr", taille: str = "base", **options) -> Traducteur:
    """Ancien nom (lectura-translator 0.1) : ``Traducteur(source, cible, taille=taille, **options)``."""
    return Traducteur(source, cible, taille=taille, **options)
