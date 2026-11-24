# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Mode API : les fonctions lexicales sont calculées par l'API publique de Lectura.

**Les mots, motifs et prononciations passés aux fonctions sont envoyés au serveur de Lectura**
(``https://api.lectura.world`` par défaut ; politique de confidentialité : https://www.lectura.world/confidentialite/#api). L'adresse se
change par l'argument ``api=`` ou la variable ``LECTURA_LEXICON_API`` (votre propre serveur, par exemple).

Bibliothèque standard seule (urllib). Une requête par appel : ``POST <api>/v1/lexique/<fonction>?langue=<fr|en>``,
arguments nommés dans un corps JSON, réponse ``{"resultat": …}`` (spécification : ``docs/API-HTTP.md``). Les
réponses sont gardées en mémoire (``cache`` appels au plus).
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict

from . import __version__
from ._types import forme_depuis_json, lecture_depuis_json

API_PAR_DEFAUT = "https://api.lectura.world"
PREFIXE = "/v1/lexique"


class ErreurAPI(RuntimeError):
    """L'API n'a pas répondu (réseau, délai, erreur du serveur) ou a refusé la requête."""

    def __init__(self, message: str, statut: int | None = None):
        super().__init__(message)
        self.statut = statut


class QuotaDepasse(ErreurAPI):
    """Quota de l'API publique atteint (HTTP 429) : réessayer plus tard, ou passer en mode local."""


def adresse_api(api: str | None = None) -> str:
    return (api or os.environ.get("LECTURA_LEXICON_API") or API_PAR_DEFAUT).rstrip("/")


def depuis_json(objet):
    """Rend aux résultats JSON leurs types Python : ``Forme`` et ``Lecture``."""
    if isinstance(objet, dict):
        if "ortho" in objet and "validite" in objet:
            return forme_depuis_json(objet)
        if "ortho" in objet and "feats" in objet:
            return lecture_depuis_json(objet)
        return {k: depuis_json(v) for k, v in objet.items()}
    if isinstance(objet, list):
        return [depuis_json(v) for v in objet]
    return objet


class Transport:
    """Envoi des requêtes et cache des réponses (partagé par les fils d'exécution)."""

    def __init__(self, api: str | None = None, cle: str | None = None, delai: float = 10.0, cache: int = 4096):
        self.base = adresse_api(api) + PREFIXE
        self.cle = cle if cle is not None else os.environ.get("LECTURA_API_KEY")
        self.delai = delai
        self._cache: OrderedDict[str, object] = OrderedDict()
        self._taille_cache = cache
        self._verrou = threading.Lock()

    def appeler(self, fonction: str, langue: str, arguments: dict):
        corps = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        url = f"{self.base}/{urllib.parse.quote(fonction)}?{urllib.parse.urlencode({'langue': langue})}"
        cle_cache = f"{url}\n{corps}"
        with self._verrou:
            if cle_cache in self._cache:
                self._cache.move_to_end(cle_cache)
                return self._cache[cle_cache]
        entetes = {"Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": f"lectura-lexicon/{__version__}"}
        if self.cle:
            entetes["Authorization"] = f"Bearer {self.cle}"
        requete = urllib.request.Request(url, data=corps.encode("utf-8"), headers=entetes, method="POST")
        try:
            with urllib.request.urlopen(requete, timeout=self.delai) as r:
                reponse = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            message = _message(e)
            if e.code == 429:
                raise QuotaDepasse(f"quota de l'API atteint : {message}", 429) from e
            if e.code in (400, 404, 422):
                raise ValueError(f"{fonction} : {message} (HTTP {e.code})") from e
            raise ErreurAPI(f"{url} : HTTP {e.code} : {message}", e.code) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErreurAPI(f"API Lectura injoignable ({self.base}) : {e}. Hors ligne, utilisez une base locale "
                            "(chemin= ou LECTURA_LEXICON_DATA).") from e
        except ValueError as e:
            raise ErreurAPI(f"{url} : réponse illisible") from e
        if not isinstance(reponse, dict) or "resultat" not in reponse:
            raise ErreurAPI(f"{url} : réponse sans « resultat »")
        resultat = depuis_json(reponse["resultat"])
        with self._verrou:
            self._cache[cle_cache] = resultat
            if len(self._cache) > self._taille_cache:
                self._cache.popitem(last=False)
        return resultat

    def infos(self, langue: str) -> dict:
        """``GET <api>/v1/lexique?langue=`` : version, base servie, fonctions, limites."""
        url = f"{self.base}?{urllib.parse.urlencode({'langue': langue})}"
        requete = urllib.request.Request(url, headers={"Accept": "application/json",
                                                       "User-Agent": f"lectura-lexicon/{__version__}"})
        try:
            with urllib.request.urlopen(requete, timeout=self.delai) as r:
                return json.loads(r.read().decode("utf-8")).get("resultat", {})
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            raise ErreurAPI(f"API Lectura injoignable ({self.base}) : {e}") from e


def _message(e: urllib.error.HTTPError) -> str:
    try:
        corps = json.loads(e.read().decode("utf-8"))
    except (ValueError, OSError):
        return e.reason or ""
    if isinstance(corps, dict):
        return str(corps.get("message") or corps.get("detail") or corps.get("error") or corps)
    return str(corps)


# ── Lexicon en mode API ────────────────────────────────────────────────────────

from ._lexicon import FONCTIONS, Lexicon, _langue  # noqa: E402


class LexiconAPI(Lexicon):
    """Lexicon dont les fonctions sont calculées par l'API publique de Lectura. Mêmes noms, mêmes arguments et mêmes
    types de résultats (``Forme``, ``Lecture``) qu'en mode local. Le dictionnaire de l'utilisateur (``ajouter``,
    ``retirer``) et les seuils de validité n'existent qu'en mode local."""

    mode = "api"

    def __init__(self, chemin=None, langue: str = "fr", taille: str | None = None, mode: str | None = None,
                 api: str | None = None, cle: str | None = None, delai: float = 10.0, seuils=None,
                 dictionnaire=None, cache: int = 4096):
        if chemin is not None:
            raise ValueError("mode API : pas de chemin de base (chemin= choisit le mode local)")
        if seuils is not None or dictionnaire:
            raise ValueError("seuils et dictionnaire de l'utilisateur : mode local seulement")
        self.langue = _langue(langue)
        self.taille = taille                     # indicatif : la base est celle du serveur
        self._transport = Transport(api, cle, delai, cache)
        self.api = self._transport.base

    def __repr__(self) -> str:
        return f"LexiconAPI(langue={self.langue!r}, api={self.api!r})"

    def _appel(self, fonction: str, **arguments):
        if fonction not in FONCTIONS[self.langue]:
            raise AttributeError(f"« {fonction} » n'existe pas en « {self.langue} » (fonctions : {', '.join(FONCTIONS[self.langue])})")
        return self._transport.appeler(fonction, self.langue, arguments)

    def infos(self) -> dict:
        """Version et base servies par l'API, fonctions et limites (``GET /v1/lexique``)."""
        return self._transport.infos(self.langue)

    # Formes
    def validite(self, forme: str) -> str:
        return self._appel("validite", forme=forme)

    def existe(self, forme: str) -> bool:
        return self._appel("existe", forme=forme)

    def est_valide(self, forme: str) -> bool:
        return self._appel("est_valide", forme=forme)

    def non_valide(self, forme: str) -> bool:
        return self._appel("non_valide", forme=forme)

    def usuelle(self, forme: str) -> str | None:
        return self._appel("usuelle", forme=forme)

    def frequence(self, forme: str) -> float:
        return self._appel("frequence", forme=forme)

    def forme(self, forme: str, avec_lectures: bool = True):
        return self._appel("forme", forme=forme, avec_lectures=avec_lectures)

    def lectures(self, forme: str, toutes: bool = False) -> list:
        return self._appel("lectures", forme=forme, toutes=toutes)

    def phones(self, forme: str) -> list[str]:
        return self._appel("phones", forme=forme)

    # Voisinages (options : voir la documentation de chaque langue)
    def homophones(self, phone: str, **options) -> list:
        return self._appel("homophones", phone=phone, **options)

    def voisins_orthographiques(self, forme: str, **options) -> list:
        return self._appel("voisins_orthographiques", forme=forme, **options)

    def voisins_phonetiques(self, phone: str, **options) -> list:
        return self._appel("voisins_phonetiques", phone=phone, **options)

    # Paradigmes
    def formes_de(self, lemme: str, upos: str | None = None, toutes: bool = False) -> list:
        return self._appel("formes_de", lemme=lemme, **({"upos": upos} if upos else {}), toutes=toutes)

    def variante(self, forme: str, toutes: bool = False, **traits: str) -> list:
        return [tuple(c) for c in self._appel("variante", forme=forme, toutes=toutes, **traits)]

    def lemmes_de(self, forme: str) -> list[str]:
        return self._appel("lemmes_de", forme=forme)

    def conjuguer(self, verbe: str) -> dict:
        return self._appel("conjuguer", verbe=verbe)

    def lemme_info(self, lemme: str) -> list[dict]:
        return self._appel("lemme_info", lemme=lemme)

    # Sons, rimes, recherche
    def rimes(self, forme: str = "", phone: str = "", **options) -> list:
        return self._appel("rimes", forme=forme, phone=phone, **options)

    def rechercher(self, motif: str = "*", **criteres) -> list:
        return self._appel("rechercher", motif=motif, **criteres)

    def filtrer(self, formes, motif: str = "*", **criteres) -> list:
        graphies = [getattr(f, "ortho", f) for f in formes]
        return self._appel("filtrer", formes=[str(g) for g in graphies], motif=motif, **criteres)

    def contient_son(self, son: str, **options) -> list:
        return self._appel("contient_son", son=son, **options)

    def syllabes(self, forme: str) -> list[str]:
        return self._appel("syllabes", forme=forme)

    def mots_par_syllabes(self, n: int, **options) -> list:
        return self._appel("mots_par_syllabes", n=n, **options)

    def anagrammes(self, forme: str, **options) -> list:
        return self._appel("anagrammes", forme=forme, **options)

    # Propres au français
    def rectifiee(self, forme: str) -> bool:
        return self._appel("rectifiee", forme=forme)

    def autre_genre(self, lemme: str) -> list[str]:
        return self._appel("autre_genre", lemme=lemme)

    def h_aspire(self, forme: str) -> bool:
        return self._appel("h_aspire", forme=forme)

    def auxiliaire(self, verbe: str) -> str | None:
        return self._appel("auxiliaire", verbe=verbe)

    def pronominal(self, verbe: str) -> str | None:
        return self._appel("pronominal", verbe=verbe)

    def est_pronominal(self, verbe: str) -> bool:
        return self._appel("est_pronominal", verbe=verbe)

    def groupe(self, verbe: str) -> int | None:
        return self._appel("groupe", verbe=verbe)

    # Propres à l'anglais
    def britannique(self, forme: str) -> bool:
        return self._appel("britannique", forme=forme)

    def americaine(self, forme: str) -> str | None:
        return self._appel("americaine", forme=forme)

    def britanniques(self, forme: str) -> list[str]:
        return self._appel("britanniques", forme=forme)

    def rime(self, forme: str = "", phone: str = "") -> list[str]:
        return self._appel("rime", forme=forme, phone=phone)

    # Mode local seulement
    def ajouter(self, *args, **kwargs):
        raise NotImplementedError("dictionnaire de l'utilisateur : mode local seulement (Lexicon(chemin=…))")

    retirer = ajouter

    def fermer(self) -> None:
        with self._transport._verrou:
            self._transport._cache.clear()
