# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Faux serveur de l'API ``/v1/lexique`` pour les tests (bibliothèque standard, 127.0.0.1 seulement).

Il suit la spécification de ``docs/API-HTTP.md`` et peut servir de référence au serveur réel :

- ``GET  /v1/lexique?langue=fr``             → ``{"resultat": {"langue", "version", "base", "fonctions", "limites"}}``
- ``POST /v1/lexique/<fonction>?langue=fr``  → corps JSON = arguments nommés ; ``{"resultat": …}``
- erreurs : 404 (fonction inconnue), 422 (argument inconnu ou invalide), 429 (quota), au format
  ``{"error": code, "message": texte}``.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lectura_lexicon import FONCTIONS, Lexicon

LIMITE_MAX = 200
APPELS: list[tuple[str, str, dict]] = []      # (langue, fonction, arguments) reçus, pour les tests


def vers_json(objet):
    if dataclasses.is_dataclass(objet):
        return {k: vers_json(v) for k, v in dataclasses.asdict(objet).items()}
    if isinstance(objet, dict):
        return {k: vers_json(v) for k, v in objet.items()}
    if isinstance(objet, (list, tuple)):
        return [vers_json(v) for v in objet]
    return objet


def demarrer(bases: dict[str, object], port: int = 0):
    lexicons = {langue: Lexicon(chemin, langue=langue) for langue, chemin in bases.items()}

    class Gestion(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _repondre(self, statut: int, corps: dict):
            donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
            self.send_response(statut)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def _erreur(self, statut: int, code: str, message: str):
            self._repondre(statut, {"error": code, "message": message})

        def _analyser(self):
            url = urllib.parse.urlparse(self.path)
            langue = urllib.parse.parse_qs(url.query).get("langue", ["fr"])[0]
            return url.path.rstrip("/"), langue

        def do_GET(self):
            chemin, langue = self._analyser()
            if chemin != "/v1/lexique" or langue not in lexicons:
                return self._erreur(404, "introuvable", chemin)
            lex = lexicons[langue]
            self._repondre(200, {"resultat": {
                "langue": langue, "version": "test", "base": {"taille": lex.taille, **lex.meta},
                "fonctions": list(FONCTIONS[langue]), "limites": {"limite_max": LIMITE_MAX}}})

        def do_POST(self):
            chemin, langue = self._analyser()
            if self.headers.get("X-Test-Quota"):
                return self._erreur(429, "quota", "quota journalier atteint (test)")
            if not chemin.startswith("/v1/lexique/") or langue not in lexicons:
                return self._erreur(404, "introuvable", chemin)
            fonction = chemin.rsplit("/", 1)[1]
            if fonction not in FONCTIONS[langue]:
                return self._erreur(404, "fonction_inconnue", f"fonction lexicale inconnue en « {langue} » : {fonction}")
            longueur = int(self.headers.get("Content-Length") or 0)
            try:
                arguments = json.loads(self.rfile.read(longueur) or b"{}")
            except ValueError:
                return self._erreur(422, "json", "corps JSON illisible")
            methode = getattr(lexicons[langue], fonction)
            parametres = inspect.signature(methode).parameters
            libres = any(p.kind == p.VAR_KEYWORD for p in parametres.values())
            inconnus = set(arguments) - set(parametres)
            if inconnus and not libres:
                return self._erreur(422, "argument_inconnu", f"arguments inconnus pour {fonction} : {sorted(inconnus)}")
            if "limite" in arguments:
                arguments["limite"] = max(1, min(int(arguments["limite"]), LIMITE_MAX))
            APPELS.append((langue, fonction, dict(arguments)))
            try:
                resultat = methode(**arguments)
            except (TypeError, ValueError) as e:
                return self._erreur(422, "argument_invalide", str(e))
            self._repondre(200, {"resultat": vers_json(resultat)})

    srv = ThreadingHTTPServer(("127.0.0.1", port), Gestion)
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
