# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""``creer_moteur`` : l'entrée unique de ``lectura-nlp-en`` (Analyseur, Lexicon, Correcteur), en quatre modes.

| ``mode``    | Analyseur                         | Lexique (``nlp.lexique``)               | Correcteur                       |
|-------------|-----------------------------------|-----------------------------------------|----------------------------------|
| ``local``   | modèles locaux, sinon erreur      | base locale ; sans base : indisponible  | modèles et base locaux, sinon erreur |
| ``degrade`` | modèles locaux, sans base Lexicon | indisponible                            | indisponible                     |
| ``api``     | ``/v1/lire``, ``/v1/ecrire``      | ``LexiconAPI`` (``/v1/lexique``)        | ``/v1/corriger``                 |
| ``auto``    | local si les modèles sont là, sinon API (avertissement) ; idem pour le lexique et le Correcteur |

En ``local`` et en ``degrade``, **aucun appel réseau, jamais**, même en repli. Le mode effectif est ``nlp.mode``
(``local``, ``api`` ou ``degrade``) ; ``nlp.etat()`` dit d'où vient chaque pièce.
"""

from __future__ import annotations

import importlib
import importlib.util
import warnings
from pathlib import Path

from .erreurs import AvertissementNLP, FonctionIndisponible, ModelesAbsents
from .lexique_indisponible import LexiqueIndisponible

LANGUE = "en"
MODES = ("auto", "local", "api", "degrade")

# Fonctions de Lexicon pour l'anglais (mêmes noms en local et par l'API)
try:
    from lectura_lexicon import FONCTIONS as _FONCTIONS

    FONCTIONS_LEXIQUE = tuple(_FONCTIONS[LANGUE])
except ImportError:                                         # lectura-lexicon absent
    FONCTIONS_LEXIQUE = ()

# Sous-paquets et dépendances de chaque fonction (``briques``)
BRIQUES = {"analyseur": "lectura_nlp_en.analyseur", "lexicon": "lectura_lexicon", "correcteur": "kenlm",
           "onnx": "onnxruntime"}


class MoteurNLP:
    """Moteur NLP de l'anglais. On l'obtient par ``creer_moteur`` ; ``MoteurNLP(analyseur, taille_lexique,
    ecriture_lexique)`` (forme de ``lectura-nlp-en`` 0.3, utilisée par le serveur) assemble un moteur local autour d'un
    analyseur déjà chargé."""

    langue = LANGUE

    def __init__(self, analyseur, taille_lexique: str | None = None, ecriture_lexique: bool | str = "auto", *,
                 lexique=None, mode: str = "local", demande: str | None = None, client=None,
                 correcteur_dir=None, tete_correcteur=None, _correcteur_mode: str | None = None,
                 _raison_correcteur: str = ""):
        self.analyseur = analyseur
        self.mode = mode
        self.demande = demande or mode
        self._taille_lexique = taille_lexique
        self._client = client
        self._lexique = lexique
        self._correcteur = None
        self._correcteur_dir = correcteur_dir
        self._tete = tete_correcteur
        self._correcteur_mode = _correcteur_mode or ("api" if mode == "api" else
                                                     "indisponible" if mode == "degrade" else "local")
        self._raison_correcteur = _raison_correcteur
        self.ecriture_lexique = False
        if ecriture_lexique and self.chaine is not None and mode != "degrade":
            try:
                self._brancher_lexique()
            except (FonctionIndisponible, ValueError):
                if ecriture_lexique is True:
                    raise

    def __repr__(self) -> str:
        return f"MoteurNLP(langue='en', mode={self.mode!r})"

    @property
    def client(self):
        """Le client de l'API (``ClientAPI``), ou ``None`` en mode local ou dégradé."""
        return self._client

    # --- Analyseur --------------------------------------------------------------------------------------------

    @property
    def chaine(self):
        """La chaîne locale de l'Analyseur (``None`` en mode API)."""
        return getattr(self.analyseur, "chaine", None)

    @property
    def transducer(self):
        """(compatibilité 0.3) L'Analyseur."""
        return self.analyseur

    def lire(self, texte: str, **options) -> list[dict]:
        """Texte → phrases alignées (``ortho``, ``phone``, ``phone_sep``, ``lineaire``, ``mots`` avec leur analyse)."""
        return self.analyseur.lire(texte, **options)

    def ecrire(self, phone: str, **options) -> list[dict]:
        """Phonétique → phrases alignées (même format que ``lire``)."""
        return self.analyseur.ecrire(phone, **options)

    def analyser(self, texte: str, **options) -> list[list[dict]]:
        """Analyse grammaticale, mot par mot (une liste par phrase) : ``forme``, ``debut``, ``fin``, ``upos``,
        ``traits``, ``lemme``, ``tete`` (indice du gouverneur dans la phrase, -1 pour la racine), ``relation``,
        ``phone`` (mêmes clés que ``lectura-nlp-fr``)."""
        phrases = []
        for p in self.lire(texte, **options):
            mots = []
            for m in p.get("mots", []):
                a = m.get("analyse") or {}
                mots.append({"forme": m.get("forme"), "debut": m.get("debut"), "fin": m.get("fin"),
                             "upos": a.get("upos"), "traits": a.get("traits") or {}, "lemme": a.get("lemme"),
                             "tete": a.get("tete"), "relation": a.get("relation"), "phone": m.get("phone")})
            phrases.append(mots)
        return phrases

    def decouper(self, texte: str) -> list[list[dict]]:
        """Découpage en phrases et mots (types, formules, abrègements, lectures) : toujours local, sans modèle."""
        from .analyseur.moteur import _MoteurChaine

        return _MoteurChaine.decouper(texte)

    # --- Lexicon ----------------------------------------------------------------------------------------------

    @property
    def lexique(self):
        """Lexicon anglais (``lectura-lexicon``) : base locale, API, ou ``LexiqueIndisponible``."""
        if self._lexique is None:
            self._lexique = _lexicon_local(None, self._taille_lexique) or LexiqueIndisponible(
                "aucune base Lexicon anglaise en local")
        return self._lexique

    def _brancher_lexique(self) -> None:
        """Élargit l'écriture (phonétique → texte) aux formes de Lexicon que l'embarqué ne connaît pas ; base locale
        seulement. Gain mesuré par NLP-EN le 16/10 (réécriture depuis la phonétique, WER) : EWT dev 9,16 → 8,41 %,
        PUD 7,15 → 4,81 %."""
        from .lexique import brancher

        lex = self.lexique
        if getattr(lex, "mode", "") != "local":
            raise FonctionIndisponible("écriture élargie à Lexicon : il faut une base Lexicon locale")
        brancher(self.chaine, lex)
        self.ecriture_lexique = True

    def fonction_lexique(self, nom: str, *args, **kwargs):
        """Appelle une fonction lexicale par son nom (``FONCTIONS_LEXIQUE``)."""
        if nom not in FONCTIONS_LEXIQUE:
            raise ValueError(f"fonction lexicale inconnue : {nom}")
        return getattr(self.lexique, nom)(*args, **kwargs)

    # --- Correcteur -------------------------------------------------------------------------------------------

    @property
    def correcteur(self):
        """Le Correcteur (extra ``[correcteur]``), chargé au premier usage : local (il réutilise la chaîne de
        l'Analyseur), ou par l'API."""
        if self._correcteur is None:
            if self._correcteur_mode == "indisponible":
                raise FonctionIndisponible(f"Correcteur indisponible : {self._raison_correcteur or 'mode dégradé'} "
                                           "(il lui faut les modèles du Correcteur et une base Lexicon locale, "
                                           "ou l'API).")
            if self._correcteur_mode == "api":
                if self.demande == "auto":
                    warnings.warn("Correcteur anglais : calcul par l'API publique de Lectura (le texte part sur le "
                                  f"serveur), faute de pièces locales ({self._raison_correcteur}).",
                                  AvertissementNLP, stacklevel=3)
                from .api import ClientAPI, CorrecteurAPI

                self._correcteur = CorrecteurAPI(self._client or ClientAPI())
            else:
                self._correcteur = self._correcteur_local()
        return self._correcteur

    def _correcteur_local(self):
        if importlib.util.find_spec("kenlm") is None:
            raise FonctionIndisponible("Correcteur : kenlm n'est pas installé (pip install \"lectura-nlp-en[correcteur]\").")
        if self.chaine is None:
            raise FonctionIndisponible("Correcteur local : il faut l'Analyseur local (modèles).")
        lex = _lexicon_correcteur(self.lexique, self._taille_lexique)
        if lex is None:
            raise FonctionIndisponible("Correcteur local : il faut une base Lexicon anglaise locale (taille standard "
                                       "de préférence).")
        from .correcteur import Correcteur

        try:
            return Correcteur(chaine=self.chaine, lexique=lex, models_dir=self._correcteur_dir, tete=self._tete)
        except FileNotFoundError as e:
            raise FonctionIndisponible(str(e)) from e

    def corriger(self, texte: str, mode: str = "suggestions", explications: str | None = None,
                 langue: str | None = None):
        """Texte → ``Resultat`` (texte corrigé, corrections expliquées) ; ``mode`` : ``suggestions`` ou
        ``automatique`` ; ``explications`` (ou ``langue``, nom de la 0.3) : ``fr`` (défaut) ou ``en``."""
        explications = explications or langue or "fr"
        if self._correcteur_mode == "api":
            return self.correcteur.corriger(texte, mode=mode, explications=explications)
        return self.correcteur.corriger(texte, mode=mode, langue=explications)

    # --- État -------------------------------------------------------------------------------------------------

    def etat(self) -> dict:
        """D'où vient chaque pièce : mode, dossiers des modèles, base Lexicon, Correcteur, adresse de l'API."""
        from . import __version__

        a = self.analyseur
        lex = self._lexique
        etat_lex = {"mode": getattr(lex, "mode", None) if lex is not None else "non chargé"}
        if lex is not None and getattr(lex, "mode", "") == "local":
            etat_lex.update(base=str(getattr(lex, "chemin", "")), taille=getattr(lex, "taille", None))
        elif lex is not None and getattr(lex, "mode", "") == "api":
            etat_lex["api"] = getattr(lex, "api", None)
        elif isinstance(lex, LexiqueIndisponible):
            etat_lex["raison"] = lex.raison
        return {
            "langue": LANGUE, "version": __version__, "mode": self.mode, "demande": self.demande,
            "analyseur": {"mode": getattr(a, "mode", "local" if self.chaine is not None else "api"),
                          "dossier": str(getattr(a, "dossier", "")) or None,
                          "api": getattr(getattr(a, "client", None), "api", None)},
            "lexique": etat_lex, "ecriture_lexique": self.ecriture_lexique,
            "correcteur": {"mode": self._correcteur_mode, "charge": self._correcteur is not None,
                           "raison": self._raison_correcteur or None},
        }

    @staticmethod
    def briques() -> dict[str, bool]:
        """Pièces installées (sans les charger)."""
        res = {}
        for nom, paquet in BRIQUES.items():
            try:
                res[nom] = importlib.util.find_spec(paquet) is not None
            except ModuleNotFoundError:
                res[nom] = False
        return res


# ── Assemblage ────────────────────────────────────────────────────────────────


def _lexicon_local(lexique, taille: str | None):
    """Lexicon anglais en mode local, ou ``None`` si aucune base n'est trouvée. Jamais d'API."""
    from lectura_lexicon import Lexicon

    try:
        if lexique is not None and not isinstance(lexique, (str, Path)):
            return lexique
        return Lexicon(lexique, langue=LANGUE, mode="local", taille=taille)
    except FileNotFoundError:
        return None


def _lexicon_correcteur(lexique, taille: str | None):
    """Base du Correcteur : la taille standard (celle sur laquelle il est réglé) si elle est installée, sinon la base
    locale du moteur. ``None`` sans base locale."""
    if getattr(lexique, "mode", "") != "local":
        return None
    if taille is None and getattr(lexique, "taille", None) not in ("standard", None):
        autre = _lexicon_local(None, "standard")
        if autre is not None:
            return autre
    return lexique


def _correcteur_present(correcteur_dir) -> tuple[bool, str]:
    from .correcteur import dossier_modeles

    if importlib.util.find_spec("kenlm") is None:
        return False, "kenlm absent (extra [correcteur])"
    if dossier_modeles(correcteur_dir) is None:
        return False, "modèle de langue du Correcteur absent"
    return True, ""


def creer_moteur(mode: str = "auto", *, models_dir: str | Path | None = None, api: str | None = None,
                 cle: str | None = None, delai: float = 30.0, lexique=None, taille_lexique: str | None = None,
                 ecriture_lexique: bool | str = "auto", correcteur_dir: str | Path | None = None,
                 tete_correcteur: str | Path | bool | None = None, fils: int = 1, **options) -> MoteurNLP:
    """Moteur NLP de l'anglais.

    - ``mode`` : ``auto`` (défaut), ``local``, ``api`` ou ``degrade`` (voir le module) ;
    - ``models_dir`` : dossier des modèles de l'Analyseur (``LECTURA_NLP_EN_DIR``, ``LECTURA_MODELS_DIR``/transducer_en,
      ``~/.lectura/models/transducer_en``) ;
    - ``api``, ``cle``, ``delai`` : adresse de l'API (``LECTURA_API_URL``, défaut https://api.lectura.world), clé
      facultative (``LECTURA_API_KEY``), délai en secondes ;
    - ``lexique`` : base Lexicon (chemin), objet ``Lexicon``, ou ``False`` (sans lexique) ; ``taille_lexique`` :
      ``mini``, ``standard`` ou ``complet`` ; ``ecriture_lexique`` : élargir l'écriture aux formes de la base locale
      (``"auto"`` : si une base locale est là ; ``True`` : exigé ; ``False``) ;
    - ``correcteur_dir`` : dossier des modèles du Correcteur (``LECTURA_CORRECTEUR_EN_DIR``,
      ``LECTURA_MODELS_DIR``/corrector_en, ``~/.lectura/models/corrector_en``) ; ``tete_correcteur`` : dossier de la
      tête de graphie, ``False`` pour s'en passer ;
    - ``fils`` : fils d'exécution d'onnxruntime ; ``options`` : celles de la chaîne (``enchainements``,
      ``formes_fortes``).
    """
    from .analyseur.moteur import MoteurLocal, dossier_modeles, message_modeles_absents
    from .api import AnalyseurAPI, ClientAPI

    if mode not in MODES:
        raise ValueError(f"mode « {mode} » : attendu {', '.join(MODES)}")
    commun = {"demande": mode, "correcteur_dir": correcteur_dir, "tete_correcteur": tete_correcteur}

    if mode == "api":
        client = ClientAPI(api, cle, delai)
        lex = lexique if lexique is not None and not isinstance(lexique, (str, Path, bool)) else _lexicon_api(client)
        if lexique is False:
            lex = LexiqueIndisponible("lexique désactivé (lexique=False)")
        return MoteurNLP(AnalyseurAPI(client=client, **options), taille_lexique, False, lexique=lex, mode="api",
                         client=client, **commun)

    dossier = dossier_modeles(models_dir)
    if dossier is None and mode in ("local", "degrade"):
        raise ModelesAbsents(message_modeles_absents(models_dir))

    if mode == "degrade":
        return MoteurNLP(MoteurLocal(dossier, fils=fils, **options), taille_lexique, False,
                         lexique=LexiqueIndisponible("mode dégradé"), mode="degrade",
                         _raison_correcteur="mode dégradé : pas de base Lexicon", **commun)

    # local, ou auto
    client = ClientAPI(api, cle, delai) if mode == "auto" else None
    if dossier is not None:
        analyseur = MoteurLocal(dossier, fils=fils, **options)
    else:                                                    # auto, sans modèles
        warnings.warn("Analyseur anglais : modèles absents en local, calcul par l'API publique de Lectura (le texte "
                      "part sur le serveur). mode=\"local\" pour l'interdire.", AvertissementNLP, stacklevel=2)
        analyseur = AnalyseurAPI(client=client, **options)

    if lexique is False:
        lex = LexiqueIndisponible("lexique désactivé (lexique=False)")
    else:
        lex = _lexicon_local(lexique, taille_lexique)
        if lex is None and mode == "auto":
            warnings.warn("Lexicon anglais : aucune base locale, fonctions lexicales par l'API publique de Lectura.",
                          AvertissementNLP, stacklevel=2)
            lex = _lexicon_api(client)
        elif lex is None:
            warnings.warn("Lexicon anglais : aucune base locale ; en mode local, jamais d'API : fonctions lexicales "
                          "indisponibles, écriture sans Lexicon.", AvertissementNLP, stacklevel=2)
            lex = LexiqueIndisponible("aucune base Lexicon anglaise en local (mode local : pas d'API)")

    # Correcteur : local si tout est là ; en auto, sinon API ; en local, sinon indisponible
    present, raison = _correcteur_present(correcteur_dir)
    if dossier is None:
        present, raison = False, "Analyseur local absent"
    elif getattr(lex, "mode", "") != "local":
        present, raison = False, "pas de base Lexicon locale"
    mode_correcteur = "local" if present else ("api" if mode == "auto" else "indisponible")

    return MoteurNLP(analyseur, taille_lexique, ecriture_lexique, lexique=lex,
                     mode="local" if dossier is not None else "api", client=client,
                     _correcteur_mode=mode_correcteur, _raison_correcteur=raison, **commun)


def _lexicon_api(client):
    from lectura_lexicon import Lexicon

    return Lexicon(langue=LANGUE, mode="api", api=client.api, cle=client.cle, delai=client.delai)


__all__ = ["BRIQUES", "FONCTIONS_LEXIQUE", "LANGUE", "MODES", "MoteurNLP", "creer_moteur"]
