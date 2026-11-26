# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Mode API : la traduction est calculée par l'API publique de Lectura.

**Les textes et les mots passés aux fonctions sont envoyés au serveur de Lectura** (``https://api.lectura.world``
par défaut ; politique de confidentialité : https://www.lectura.world/confidentialite/#api). L'adresse se change par
l'argument ``api=``, la variable ``LECTURA_TRADUCTEUR_API`` ou la variable commune aux modules v1 ``LECTURA_API_URL``
(votre propre serveur, par exemple).

Bibliothèque standard seule (urllib). Routes (spécification : ``docs/API-HTTP.md``) :

- ``POST <api>/v1/traduire``          ``{"texte", "source", "cible", "options"}`` ;
- ``POST <api>/v1/traduire/aligner``  ``{"mots_source", "mots_cible", "source", "cible"}`` ;
- ``POST <api>/v1/traduire/gloser``   ``{"texte", "source"}`` ;
- ``GET  <api>/v1/traduire``          version, paires, limites.

Un texte plus long que la limite d'une requête est découpé ici, entre deux phrases, en plusieurs requêtes ; les
positions (``debut``, ``fin``) restent celles du texte d'origine.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from ._traducteur import Traducteur, verifier_paire

API_PAR_DEFAUT = "https://api.lectura.world"
PREFIXE = "/v1/traduire"
# Limites par requête de la spécification (docs/API-HTTP.md) ; ``infos()`` donne celles du serveur.
TEXTE_MAX = 2_000
GLOSE_MAX = 1_000
MOTS_MAX = 200


try:                                               # mêmes classes que lectura-lexicon et lectura-nlp-fr / -en
    from lectura_lexicon.api import ErreurAPI, QuotaDepasse
except ImportError:                                # lectura-lexicon absent : classes équivalentes
    class ErreurAPI(RuntimeError):                 # type: ignore[no-redef]
        """L'API n'a pas répondu (réseau, délai, erreur du serveur) ou a refusé la requête."""

        def __init__(self, message: str, statut: int | None = None):
            super().__init__(message)
            self.statut = statut

    class QuotaDepasse(ErreurAPI):                 # type: ignore[no-redef]
        """Quota de l'API publique atteint (HTTP 429) : réessayer après minuit UTC, ou passer en mode local."""


def adresse_api(api: str | None = None) -> str:
    """``api``, sinon ``LECTURA_TRADUCTEUR_API``, sinon ``LECTURA_API_URL``, sinon https://api.lectura.world."""
    return (api or os.environ.get("LECTURA_TRADUCTEUR_API") or os.environ.get("LECTURA_API_URL")
            or API_PAR_DEFAUT).rstrip("/")


def _message(e: urllib.error.HTTPError) -> str:
    try:
        corps = json.loads(e.read().decode("utf-8"))
    except (ValueError, OSError):
        return e.reason or ""
    if isinstance(corps, dict):
        return str(corps.get("message") or corps.get("detail") or corps.get("error") or corps)
    return str(corps)


class Transport:
    """Envoi des requêtes JSON à l'API."""

    def __init__(self, api: str | None = None, cle: str | None = None, delai: float = 60.0):
        from . import __version__
        self.base = adresse_api(api) + PREFIXE
        self.cle = cle if cle is not None else (os.environ.get("LECTURA_API_KEY") or None)
        self.delai = delai
        self.agent = f"lectura-traducteur/{__version__}"

    def _requete(self, url: str, corps: bytes | None, methode: str):
        entetes = {"Accept": "application/json", "User-Agent": self.agent}
        if corps is not None:
            entetes["Content-Type"] = "application/json"
        if self.cle:
            entetes["Authorization"] = f"Bearer {self.cle}"
        requete = urllib.request.Request(url, data=corps, headers=entetes, method=methode)
        try:
            with urllib.request.urlopen(requete, timeout=self.delai) as r:
                reponse = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            message = _message(e)
            if e.code == 429:
                erreur = QuotaDepasse(f"quota de l'API atteint (traduction) : {message}", 429)
                try:
                    erreur.attente = int(e.headers.get("Retry-After") or 0) or None
                except (TypeError, ValueError):
                    erreur.attente = None
                raise erreur from e
            if e.code in (400, 404, 413, 422):
                raise ValueError(f"{message} (HTTP {e.code})") from e
            raise ErreurAPI(f"{url} : HTTP {e.code} : {message}", e.code) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErreurAPI(f"API Lectura injoignable ({self.base}) : {e}. Hors ligne : mode local, avec les modèles "
                            "installés sur la machine.") from e
        except ValueError as e:
            raise ErreurAPI(f"{url} : réponse illisible") from e
        if not isinstance(reponse, dict) or "resultat" not in reponse:
            raise ErreurAPI(f"{url} : réponse sans « resultat »")
        return reponse["resultat"]

    def appeler(self, chemin: str, arguments: dict):
        corps = json.dumps(arguments, ensure_ascii=False).encode("utf-8")
        return self._requete(self.base + chemin, corps, "POST")

    def infos(self, source: str, cible: str) -> dict:
        url = f"{self.base}?{urllib.parse.urlencode({'source': source, 'cible': cible})}"
        return self._requete(url, None, "GET")


_FIN_DE_PHRASE = re.compile(r"[.!?…:;»\"”)\]]\s+|\n\s*")


def morceaux(texte: str, taille_max: int) -> list[tuple[int, str]]:
    """Découpe ``texte`` en morceaux d'au plus ``taille_max`` caractères, de préférence après une fin de phrase, sinon
    à une espace, sinon net. Rend (position dans le texte, morceau) ; les morceaux recouvrent tout le texte."""
    sorties, pos = [], 0
    while len(texte) - pos > taille_max:
        fenetre = texte[pos:pos + taille_max]
        coupe = 0
        for m in _FIN_DE_PHRASE.finditer(fenetre):
            coupe = m.end()
        if coupe < taille_max // 4:
            espace = fenetre.rfind(" ")
            coupe = espace + 1 if espace > taille_max // 4 else taille_max
        sorties.append((pos, texte[pos:pos + coupe]))
        pos += coupe
    sorties.append((pos, texte[pos:]))
    return sorties


def _liens(valeur) -> list[tuple[int, int]]:
    return [(int(i), int(j)) for i, j in (valeur or [])]


class TraducteurAPI(Traducteur):
    """Traducteur dont les calculs sont faits par l'API publique de Lectura. Mêmes fonctions et mêmes résultats qu'en
    mode local. ``api`` : adresse du serveur (``LECTURA_TRADUCTEUR_API``) ; ``cle`` : clé facultative
    (``LECTURA_API_KEY``) ; ``delai`` : délai d'attente en secondes. ``fils``, ``gpu``, ``aligneur`` et ``analyseur`` sont sans effet
    (le serveur choisit)."""

    mode = "api"

    def __init__(self, source: str = "en", cible: str = "fr", mode: str | None = None, taille: str = "base",
                 aligneur: str = "precis", fils: int = 4, gpu: bool = False, models_dir=None, api: str | None = None,
                 cle: str | None = None, delai: float | None = None, analyseur=None):
        if models_dir is not None:
            raise ValueError("mode API : pas de dossier de modèles (models_dir= choisit le mode local)")
        if taille not in ("base", "big"):
            raise ValueError(f"taille « {taille} » : base ou big")
        self.source, self.cible = verifier_paire(source, cible)
        self.taille = taille
        self.transport = Transport(api, cle, 60.0 if delai is None else delai)
        self.texte_max, self.glose_max = TEXTE_MAX, GLOSE_MAX

    @property
    def api(self) -> str:
        return self.transport.base[: -len(PREFIXE)]

    def traduire(self, texte: str, aligner: bool = False, formules: bool = True) -> dict:
        phrases = []
        for decalage, morceau in morceaux(texte, self.texte_max):
            if not morceau.strip():
                continue
            options = {"aligner": bool(aligner), "formules": bool(formules)}
            if self.taille != "base":
                options["taille"] = self.taille
            r = self.transport.appeler("", {"texte": morceau, "source": self.source, "cible": self.cible,
                                            "options": options})
            for p in r.get("phrases", []):
                p = dict(p)
                p["debut"], p["fin"] = int(p["debut"]) + decalage, int(p["fin"]) + decalage
                if "liens" in p:
                    p["liens"] = _liens(p["liens"])
                phrases.append(p)
        return {"texte": " ".join(p["traduction"] for p in phrases), "phrases": phrases}

    def aligner(self, mots_source: list[str], mots_cible: list[str]) -> set[tuple[int, int]]:
        if not mots_source or not mots_cible:
            return set()
        if len(mots_source) > MOTS_MAX or len(mots_cible) > MOTS_MAX:
            raise ValueError(f"aligner : {MOTS_MAX} mots au plus de chaque côté")
        r = self.transport.appeler("/aligner", {"mots_source": list(mots_source), "mots_cible": list(mots_cible),
                                                "source": self.source, "cible": self.cible})
        return set(_liens(r.get("liens")))

    def gloser(self, texte: str) -> list[dict]:
        sorties = []
        for decalage, morceau in morceaux(texte, self.glose_max):
            if not morceau.strip():
                continue
            r = self.transport.appeler("/gloser", {"texte": morceau, "source": self.source})
            for ph in r.get("phrases", []):
                ph = dict(ph)
                for m in ph.get("mots", []):
                    m["debut"], m["fin"] = int(m["debut"]) + decalage, int(m["fin"]) + decalage
                sorties.append(ph)
        return sorties

    def infos(self) -> dict:
        """``GET <api>/v1/traduire`` : version servie, paires, tailles, limites (sans quota)."""
        r = dict(self.transport.infos(self.source, self.cible))
        return {"mode": "api", "api": self.api, **r}
