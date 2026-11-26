# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""``creer_moteur`` : une seule entrée pour l'Analyseur, le Correcteur et le lexique, en mode local, API ou dégradé.

Spécification complète : ``docs/INTERFACE.md``. En résumé :

- ``"local"`` : tout sur la machine, **aucun appel réseau, jamais** ; erreur claire si les modèles manquent ;
- ``"degrade"`` : l'Analyseur sur ses seuls modèles, sans base Lexicon ; fonctions lexicales « indisponibles » ;
- ``"api"`` : tout par l'API publique de Lectura (les textes partent vers le serveur) ;
- ``"auto"`` : local si les modèles sont là, sinon API, et un avertissement le dit.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from .erreurs import AvertissementNLP, FonctionIndisponible, ModelesAbsents
from .lexique_indisponible import LexiqueIndisponible

LANGUE = "fr"
MODES = ("auto", "local", "api", "degrade")

# Fonctions de Lexicon exposées par l'ancien ``lectura-nlp-fr`` 1.2.0 (routes du serveur) ; toutes celles de
# ``lectura_lexicon.FONCTIONS["fr"]`` restent accessibles par ``moteur.lexique``.
FONCTIONS_LEXIQUE = (
    "validite", "existe", "usuelle", "frequence", "forme", "lectures", "phones", "homophones",
    "voisins_orthographiques", "voisins_phonetiques", "formes_de", "variante", "lemmes_de", "rimes",
    "contient_son", "syllabes", "mots_par_syllabes", "anagrammes", "conjuguer", "autre_genre", "rectifiee",
    "rechercher", "filtrer",
)

BriqueAbsente = FonctionIndisponible           # nom de la version 1.2.0


def _avertir(message: str) -> None:
    warnings.warn(message, AvertissementNLP, stacklevel=4)


def analyser_phrases(phrases: list[dict]) -> list[list[dict]]:
    """Phrases alignées (sortie de ``lire``) → analyse grammaticale, mot par mot : ``forme``, ``debut``, ``fin``,
    ``upos``, ``traits``, ``lemme``, ``tete``, ``relation``, ``phone``."""
    resultat = []
    for p in phrases:
        mots = []
        for m in p.get("mots", []):
            a = m.get("analyse") or {}
            mots.append({"forme": m.get("forme"), "debut": m.get("debut"), "fin": m.get("fin"),
                         "upos": a.get("upos"), "traits": a.get("traits"), "lemme": a.get("lemme"),
                         "tete": a.get("tete"), "relation": a.get("relation"), "phone": m.get("phone")})
        resultat.append(mots)
    return resultat



def _simple(valeur):
    """Valeur sérialisable en JSON pour ``etat()`` : chaîne, nombre ou None (jamais une fonction, ex. en mode dégradé)."""
    if valeur is None or isinstance(valeur, (bool, int, float)):
        return valeur
    if callable(valeur):
        return None
    return str(valeur) or None

class _Commun:
    langue = LANGUE
    mode = ""

    def analyser(self, texte: str, **options) -> list[list[dict]]:
        """Texte → analyse grammaticale de chaque mot, par phrase (catégorie UD, traits, lemme, tête, relation)."""
        return analyser_phrases(self.lire(texte, **options))

    @staticmethod
    def decouper(texte: str) -> list[list[dict]]:
        """Découpage en phrases et mots (types, formules, abrègements, lectures) : toujours local, sans modèle."""
        from .analyseur.decoupage_texte import decouper

        return [[vars(m) for m in p] for p in decouper(texte)]

    def fonction_lexique(self, nom: str, *args, **kwargs):
        """Appelle une fonction lexicale par son nom (routes du serveur)."""
        return getattr(self.lexique, nom)(*args, **kwargs)

    @staticmethod
    def briques() -> dict[str, bool]:
        """Fonctions installées (sans les charger) : analyseur toujours ; correcteur si kenlm, onnxruntime et numpy
        sont importables ; lexicon si lectura-lexicon l'est."""
        import importlib.util

        def present(*modules):
            return all(importlib.util.find_spec(m) is not None for m in modules)

        return {"analyseur": True, "transducer": True, "lexicon": present("lectura_lexicon"),
                "correcteur": present("kenlm", "onnxruntime", "numpy"),
                "corrector": present("kenlm", "onnxruntime", "numpy")}


class MoteurNLP(_Commun):
    """Moteur local (``mode`` « local » ou « degrade »). ``analyseur`` : un ``MoteurLocal`` de l'Analyseur (ou de
    l'ancien ``lectura_transducer``). Signature compatible avec la version 1.2.0 :
    ``MoteurNLP(transducer, taille_lexique=None, ecriture_lexique="auto")``."""

    def __init__(self, analyseur, taille_lexique: str | None = None, ecriture_lexique: bool | str = "auto", *,
                 mode: str = "local", lexique=None, correcteur_dir=None, juge_correcteur=None,
                 auto: bool = False, api: str | None = None, cle: str | None = None, delai: float = 30.0):
        if mode not in ("local", "degrade"):
            raise ValueError(f"MoteurNLP : mode local ou degrade, pas « {mode} »")
        self.mode = mode
        self.analyseur = self.transducer = analyseur
        self._auto = auto                         # repli vers l'API permis (mode auto) ; jamais en local choisi
        self._api = (api, cle, delai)
        self._taille_lexique = taille_lexique
        self._lexique_donne = lexique is not None and lexique is not False
        self._correcteur = None
        self._correcteur_dir = correcteur_dir
        self._juge_correcteur = juge_correcteur
        self.lexique = self._ouvrir_lexique(lexique)
        self.ecriture_lexique = False
        if not getattr(analyseur, "ecriture", True):          # lecture seule : rien à brancher sur l'écriture
            if ecriture_lexique is True:
                raise FonctionIndisponible("ecriture=False : pas d'écriture élargie.")
            ecriture_lexique = False
        if mode == "degrade":
            if ecriture_lexique is True:
                raise FonctionIndisponible("mode dégradé : pas de base Lexicon, donc pas d'écriture élargie.")
        elif ecriture_lexique == "auto":
            if getattr(self.lexique, "mode", "") == "local":
                self._brancher_lexique()
        elif ecriture_lexique:
            self._brancher_lexique()

    def __repr__(self) -> str:
        return f"MoteurNLP(mode={self.mode!r}, lexique={self.lexique!r})"

    # --- Analyseur ------------------------------------------------------------------------------------------------

    @property
    def chaine(self):
        return getattr(self.analyseur, "chaine", None)

    def lire(self, texte: str, **options) -> list[dict]:
        """Texte → phrases alignées (``ortho``, ``phone``, ``phone_sep``, ``lineaire``, ``mots`` avec leur analyse)."""
        return self.analyseur.lire(texte, **options)

    def ecrire(self, phone: str, **options) -> list[dict]:
        """Phonétique (mots séparés par des espaces, « . » et « ‿ » facultatifs) → phrases alignées."""
        return self.analyseur.ecrire(phone, **options)

    # --- Lexique --------------------------------------------------------------------------------------------------

    def _ouvrir_lexique(self, lexique):
        if lexique is False:
            return LexiqueIndisponible("lexique désactivé (lexique=False)")
        if self.mode == "degrade":
            if lexique is not None:
                raise ValueError("mode dégradé : sans base Lexicon (ne pas passer lexique=)")
            return LexiqueIndisponible("mode dégradé")
        if lexique is not None and not isinstance(lexique, (str, Path)):
            return lexique                         # objet Lexicon donné
        try:
            from lectura_lexicon import Lexicon
        except ImportError:
            _avertir("lectura-lexicon n'est pas installé : fonctions lexicales indisponibles.")
            return LexiqueIndisponible("lectura-lexicon absent")
        try:
            if lexique is not None:
                return Lexicon(lexique, langue=LANGUE, mode="local")
            return Lexicon(langue=LANGUE, mode="local", taille=self._taille_lexique)
        except FileNotFoundError as e:
            if self._auto:
                from lectura_lexicon import LexiconAPI

                api, cle, delai = self._api
                _avertir("Lexique : aucune base Lexicon locale, les fonctions lexicales passent par l'API publique de "
                         "Lectura (les mots sont envoyés au serveur).")
                return LexiconAPI(langue=LANGUE, api=api or _adresse(), cle=cle, delai=min(delai, 10.0))
            _avertir(f"Lexique : aucune base Lexicon locale ({str(e)[:80]}…) ; en mode local, jamais d'API : fonctions "
                     "lexicales indisponibles.")
            return LexiqueIndisponible("aucune base Lexicon locale")

    def _brancher_lexique(self) -> None:
        """Élargit l'écriture (phonétique → texte) aux formes de la base Lexicon locale ; le lexique embarqué de
        l'Analyseur reste prioritaire (gain net jugé sur FLEURS test et dev2, 15/10)."""
        if self.chaine is None:
            raise FonctionIndisponible("écriture élargie : Analyseur local seulement.")
        if getattr(self.lexique, "mode", "") != "local":
            raise FonctionIndisponible("écriture élargie : il faut une base Lexicon locale.")
        from lectura_lexicon.fr.transducer import brancher

        brancher(self.chaine, getattr(self.lexique, "moteur", self.lexique))
        self.ecriture_lexique = True

    # --- Correcteur -----------------------------------------------------------------------------------------------

    @property
    def correcteur(self):
        """Le Correcteur, chargé au premier usage ; il réutilise la chaîne de l'Analyseur local."""
        if self._correcteur is None:
            self._correcteur = self._charger_correcteur()
        return self._correcteur

    def _charger_correcteur(self):
        if self.mode == "degrade":
            raise FonctionIndisponible("Correcteur indisponible en mode dégradé : il lui faut une base Lexicon "
                                       "(mode local avec une base, ou mode API).")
        try:
            from . import correcteur as module
        except ImportError as e:
            if self._auto:
                return self._correcteur_api(f"dépendances absentes ({e})")
            raise FonctionIndisponible("Correcteur : dépendances absentes, pip install \"lectura-nlp-fr[correcteur]\" "
                                       f"({e}).") from e
        try:
            # base donnée par l'utilisateur, sinon la « standard » locale (réglages du Correcteur) ; jamais l'API
            if self._lexique_donne and getattr(self.lexique, "mode", "") == "local":
                lexique = self.lexique
            else:
                lexique = module.lexique_local()
            return module.charger(self._correcteur_dir, lexique=lexique, chaine=self.chaine,
                                  juge_homophones=self._juge_correcteur)
        except (FileNotFoundError, ImportError) as e:
            if self._auto:
                return self._correcteur_api(str(e)[:160])
            raise FonctionIndisponible(f"Correcteur indisponible en mode local : {e}") from e

    def _correcteur_api(self, raison: str):
        from .api import ClientAPI, CorrecteurAPI

        _avertir(f"Correcteur : pas de correction locale ({raison}) ; passage à l'API publique de Lectura (les "
                 "textes sont envoyés au serveur).")
        return CorrecteurAPI(ClientAPI(*self._api))

    def corriger(self, texte: str, mode: str = "suggestions", explications: str = "fr", **options):
        """Texte → ``Resultat`` (``texte`` corrigé, ``corrections``) ; ``mode`` : ``suggestions`` ou ``automatique``.
        ``explications`` : le Correcteur français explique en français (argument transmis à l'API)."""
        c = self.correcteur
        if hasattr(c, "client"):
            return c.corriger(texte, mode=mode, explications=explications)
        return c.corriger(texte, mode=mode, **options)

    # --- État -----------------------------------------------------------------------------------------------------

    def etat(self) -> dict:
        """Ce qui est chargé : mode, dossier des modèles, empreinte des juges, supplément, base lexicale."""
        from . import __version__

        chaine = self.chaine
        juge = getattr(chaine, "recherche", None) if chaine is not None else None
        juge_ecriture = juge.empreinte() if hasattr(juge, "empreinte") else None
        correcteur = None
        if self._correcteur is not None:
            jh = getattr(self._correcteur, "juge_homophones", None)
            correcteur = {"mode": "api" if hasattr(self._correcteur, "client") else "local",
                          "juge_sha256": jh.empreinte() if hasattr(jh, "empreinte") else None}
        return {"version": __version__, "mode": self.mode,
                "analyseur": str(getattr(self.analyseur, "dossier", "")) or None,
                "juge_ecriture_sha256": juge_ecriture,
                "lexique": {"mode": _simple(getattr(self.lexique, "mode", None)),
                            "base": _simple(getattr(self.lexique, "chemin", None)),
                            "taille": _simple(getattr(self.lexique, "taille", None))},
                "ecriture_lexique": self.ecriture_lexique, "correcteur": correcteur}


class MoteurNLPAPI(_Commun):
    """Tout par l'API publique de Lectura (``mode="api"``) : ``lire``, ``ecrire``, ``analyser``, ``corriger``, et
    ``lexique`` (``LexiconAPI``). Les textes, prononciations et mots sont envoyés au serveur."""

    mode = "api"

    def __init__(self, api: str | None = None, cle: str | None = None, delai: float = 30.0, lexique=None,
                 **options):
        from .api import AnalyseurAPI, ClientAPI, CorrecteurAPI

        options.pop("ecriture", None)                         # sans objet en mode API (rien n'est chargé)
        self.client = ClientAPI(api, cle, delai)
        self.analyseur = self.transducer = AnalyseurAPI(client=self.client, **options)
        self._correcteur = CorrecteurAPI(self.client)
        if lexique is False:
            self.lexique = LexiqueIndisponible("lexique désactivé (lexique=False)")
        elif lexique is not None and not isinstance(lexique, (str, Path)):
            self.lexique = lexique
        else:
            if lexique is not None:
                raise ValueError("mode API : pas de base locale (lexique= choisit une base locale : mode local)")
            try:
                from lectura_lexicon import LexiconAPI
            except ImportError:
                self.lexique = LexiqueIndisponible("lectura-lexicon absent")
            else:
                self.lexique = LexiconAPI(langue=LANGUE, api=self.client.api, cle=cle, delai=min(delai, 10.0))
        self.ecriture_lexique = False

    def __repr__(self) -> str:
        return f"MoteurNLPAPI(api={self.client.api!r})"

    def lire(self, texte: str, **options) -> list[dict]:
        return self.analyseur.lire(texte, **options)

    def ecrire(self, phone: str, **options) -> list[dict]:
        return self.analyseur.ecrire(phone, **options)

    @property
    def correcteur(self):
        return self._correcteur

    def corriger(self, texte: str, mode: str = "suggestions", explications: str = "fr"):
        return self._correcteur.corriger(texte, mode=mode, explications=explications)

    def etat(self) -> dict:
        from . import __version__

        return {"version": __version__, "mode": "api", "api": self.client.api,
                "lexique": {"mode": getattr(self.lexique, "mode", None)}}


def _adresse() -> str:
    from .api import adresse_api

    return adresse_api()


def creer_moteur(mode: str = "auto", *, models_dir: str | Path | None = None, api: str | None = None,
                 cle: str | None = None, delai: float = 30.0, lexique=None, taille_lexique: str | None = None,
                 ecriture_lexique: bool | str = False, correcteur_dir: str | Path | None = None,
                 juge_correcteur: str | Path | bool | None = None, **options):
    """Moteur NLP du français. ``mode`` : ``auto`` (défaut), ``local``, ``api`` ou ``degrade`` (voir le module).

    - ``models_dir`` : dossier des modèles de l'Analyseur (sinon ``LECTURA_NLP_FR_DIR``, ``$LECTURA_MODELS_DIR/
      transducer``, ``~/.lectura/models/transducer``) ;
    - ``api``, ``cle``, ``delai`` : adresse de l'API (``LECTURA_API_URL``), clé facultative, délai en secondes ;
    - ``lexique`` : chemin d'une base Lexicon, objet ``Lexicon``, ou ``False`` (sans lexique) ; ``taille_lexique`` :
      ``mini``, ``standard`` ou ``complet`` ; ``ecriture_lexique`` : élargir l'écriture aux formes de la base locale
      (``False`` par défaut : le banc CSF18 du 25/11 n'y voit aucun gain ; ``True``, ou ``"auto"`` : si une base
      locale est ouverte) ;
    - ``correcteur_dir``, ``juge_correcteur`` : modèles du Correcteur et son juge (v2b ; ``False`` : sans juge) ;
    - ``options`` : options de la chaîne (``e_caduc``, ``schwas_finaux``, ``liaisons``, ``enchainements``,
      ``elisions``, ``juge``, ``poids_juge``…) ; ``ecriture=False`` : lecture seule (``lire``, ``analyser``,
      ``corriger``) — ni juge ni supplément d'écriture cherchés ni signalés, ``ecrire`` lève ``FonctionIndisponible``."""
    if mode not in MODES:
        raise ValueError(f"mode « {mode} » : attendu {', '.join(MODES)}")
    if mode == "api":
        return MoteurNLPAPI(api, cle, delai, lexique=lexique, **options)
    from .analyseur.moteur import MoteurLocal, dossier_modeles, message_modeles_absents

    dossier = dossier_modeles(models_dir)
    if dossier is None:
        if mode in ("local", "degrade"):
            raise ModelesAbsents(message_modeles_absents(models_dir))
        warnings.warn("Analyseur : modèles locaux introuvables, passage à l'API publique de Lectura (les textes sont "
                      "envoyés au serveur). Pour rester sur la machine : mode=\"local\" avec les modèles installés.",
                      AvertissementNLP, stacklevel=2)
        return MoteurNLPAPI(api, cle, delai, lexique=lexique, **options)
    analyseur = MoteurLocal(dossier, **options)
    analyseur.dossier = dossier
    return MoteurNLP(analyseur, taille_lexique, ecriture_lexique, mode="degrade" if mode == "degrade" else "local",
                     lexique=lexique, correcteur_dir=correcteur_dir, juge_correcteur=juge_correcteur,
                     auto=(mode == "auto"), api=api, cle=cle, delai=delai)
