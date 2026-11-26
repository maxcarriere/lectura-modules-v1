# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Mode API : lecture, écriture et correction calculées par l'API publique de Lectura.

**Les textes et les prononciations passés aux fonctions sont envoyés au serveur de Lectura**
(``https://api.lectura.world`` par défaut ; politique de confidentialité : https://www.lectura.world/confidentialite/#api).
L'adresse se change par l'argument ``api=`` ou la variable ``LECTURA_API_URL`` (votre propre serveur, par exemple).

Bibliothèque standard seule (urllib). Routes (spécification : ``docs/API-HTTP.md``) :

- ``POST /v1/lire``     ``{"texte", "langue", "options"}``  → phrases alignées ;
- ``POST /v1/ecrire``   ``{"phone", "langue", "options"}``  → phrases alignées ;
- ``POST /v1/corriger`` ``{"texte", "langue", "mode", "explications"}`` → ``{"texte", "corrections"}`` ;
- lexique : ``LexiconAPI`` de ``lectura-lexicon`` (``POST /v1/lexique/<fonction>?langue=fr``).

Réponse ``{"resultat": …}`` ; erreur ``{"error", "message"}``. Erreurs Python : ``QuotaDepasse`` (429),
``ValueError`` (400, 404, 413, 422), ``ErreurAPI`` (réseau, délai, 5xx).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .erreurs import ErreurAPI, QuotaDepasse

API_PAR_DEFAUT = "https://api.lectura.world"
LANGUE = "fr"
# Options admises par le serveur (le reste est ignoré par lui) : options de la chaîne et du format linéaire.
OPTIONS_CHAINE = ("e_caduc", "schwas_finaux", "liaisons", "enchainements", "elisions", "juge")
OPTIONS_FORMAT = ("x_entier", "doubles")
OPTIONS_ECRITURE = ("formules",)


def adresse_api(api: str | None = None) -> str:
    """Adresse de l'API : ``api``, sinon ``LECTURA_API_URL``, sinon https://api.lectura.world."""
    return (api or os.environ.get("LECTURA_API_URL") or API_PAR_DEFAUT).rstrip("/")


def _version() -> str:
    from . import __version__

    return __version__


def _message(e: urllib.error.HTTPError) -> str:
    try:
        corps = json.loads(e.read().decode("utf-8"))
    except (ValueError, OSError):
        return e.reason or ""
    if isinstance(corps, dict):
        return str(corps.get("message") or corps.get("detail") or corps.get("error") or corps)
    return str(corps)


class ClientAPI:
    """Envoi des requêtes à l'API v1 de Lectura. ``api`` : adresse (``LECTURA_API_URL``) ; ``cle`` : clé facultative
    (``LECTURA_API_KEY``) ; ``delai`` : en secondes."""

    def __init__(self, api: str | None = None, cle: str | None = None, delai: float = 30.0):
        self.api = adresse_api(api)
        self.cle = cle if cle is not None else (os.environ.get("LECTURA_API_KEY") or None)
        self.delai = delai

    def __repr__(self) -> str:
        return f"ClientAPI(api={self.api!r})"

    def appeler(self, route: str, corps: dict):
        """``POST <api>/v1/<route>`` avec ``corps`` en JSON ; rend la valeur de ``resultat``."""
        url = f"{self.api}/v1/{route}"
        entetes = {"Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": f"lectura-nlp-fr/{_version()}"}
        if self.cle:
            entetes["Authorization"] = f"Bearer {self.cle}"
        donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
        requete = urllib.request.Request(url, data=donnees, headers=entetes, method="POST")
        try:
            with urllib.request.urlopen(requete, timeout=self.delai) as r:
                reponse = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            message = _message(e)
            if e.code == 429:
                erreur = QuotaDepasse(f"quota de l'API atteint ({route}) : {message}", 429)
                try:
                    erreur.attente = int(e.headers.get("Retry-After") or 0) or None
                except (TypeError, ValueError):
                    erreur.attente = None
                raise erreur from e
            if e.code in (400, 404, 413, 422):
                raise ValueError(f"{route} : {message} (HTTP {e.code})") from e
            raise ErreurAPI(f"{url} : HTTP {e.code} : {message}", e.code) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErreurAPI(f"API Lectura injoignable ({self.api}) : {e}. Hors ligne : mode=\"local\" avec les "
                            "modèles installés.") from e
        except ValueError as e:
            raise ErreurAPI(f"{url} : réponse illisible") from e
        if not isinstance(reponse, dict) or "resultat" not in reponse:
            raise ErreurAPI(f"{url} : réponse sans « resultat »")
        return reponse["resultat"]


def _options(defaut: dict, options: dict, admises: tuple[str, ...]) -> dict:
    tout = {**defaut, **options}
    inconnues = set(tout) - set(admises)
    if inconnues:
        raise ValueError(f"options non prises en charge par l'API : {sorted(inconnues)} (admises : {', '.join(admises)})")
    return {k: bool(v) for k, v in tout.items()}


class AnalyseurAPI:
    """Analyseur calculé par l'API : même interface que l'Analyseur local (``lire``, ``ecrire``, ``decouper``).
    ``options`` : options de la chaîne envoyées à chaque requête (``e_caduc``, ``liaisons``…, ``juge``)."""

    mode = "api"

    def __init__(self, api: str | None = None, cle: str | None = None, delai: float = 30.0,
                 client: ClientAPI | None = None, **options):
        self.client = client or ClientAPI(api, cle, delai)
        self.options = _options({}, options, OPTIONS_CHAINE)
        self.url = self.client.api                    # compatibilité (ancien MoteurAPI)

    def __repr__(self) -> str:
        return f"AnalyseurAPI(api={self.client.api!r})"

    def lire(self, texte: str, **options) -> list[dict]:
        """Texte → phrases alignées (``POST /v1/lire``)."""
        return self.client.appeler("lire", {"texte": texte, "langue": LANGUE,
                                            "options": _options(self.options, options, OPTIONS_CHAINE + OPTIONS_FORMAT)})

    def ecrire(self, phone: str, **options) -> list[dict]:
        """Phonétique → phrases alignées (``POST /v1/ecrire``)."""
        admises = OPTIONS_CHAINE + OPTIONS_FORMAT + OPTIONS_ECRITURE
        return self.client.appeler("ecrire", {"phone": phone, "langue": LANGUE,
                                              "options": _options(self.options, options, admises)})

    @staticmethod
    def decouper(texte: str) -> list[list[dict]]:
        """Découpage en phrases et mots : toujours local, sans modèle ni réseau."""
        from .analyseur.decoupage_texte import decouper

        return [[vars(m) for m in p] for p in decouper(texte)]


class CorrecteurAPI:
    """Correcteur calculé par l'API (``POST /v1/corriger``) ; rend le même ``Resultat`` que le Correcteur local."""

    def __init__(self, client: ClientAPI):
        self.client = client

    def corriger(self, texte: str, mode: str = "suggestions", explications: str = "fr"):
        from .resultats import Correction, Resultat

        if mode not in ("suggestions", "automatique"):
            raise ValueError("mode : suggestions ou automatique")
        r = self.client.appeler("corriger", {"texte": texte, "langue": LANGUE, "mode": mode,
                                             "explications": explications})
        champs = set(Correction.__dataclass_fields__)
        return Resultat(r.get("texte", texte),
                        [Correction(**{k: v for k, v in c.items() if k in champs}) for c in r.get("corrections", [])])
