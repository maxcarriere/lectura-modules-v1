# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Faux serveur de l'API v1 (``/v1/lire``, ``/v1/ecrire``, ``/v1/corriger``, ``/v1/lexique/<fonction>``) pour les tests :
bibliothèque standard, 127.0.0.1 seulement, aucun modèle. Il suit les formes du serveur réel (corps JSON, réponse
``{"resultat": …}``, erreurs ``{"error", "message"}``) et renvoie des résultats fabriqués, pour vérifier ce que le client
envoie et comment il lit les réponses.

Textes de test : ``"__429__"`` (quota, avec ``Retry-After``), ``"__422__"``, ``"__503__"`` forcent une erreur.
"""

from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APPELS: list[tuple[str, dict, dict]] = []      # (chemin, corps, en-têtes) reçus


def _phrase(ortho: str, phone: str) -> dict:
    mots = [{"forme": f, "debut": 0, "fin": len(f), "origine": "lexique", "phone": p, "jonction": "",
             "couples": [], "analyse": {"upos": "X", "traits": {}, "lemme": f.lower(), "tete": -1,
                                        "relation": "root", "confiance": 1.0},
             "lecture": [], "formule": ""} for f, p in zip(ortho.split(), phone.split())]
    return {"ortho": ortho, "phone": phone, "phone_sep": phone, "lineaire": [], "mots": mots, "corrections": []}


def demarrer(port: int = 0):
    class Gestion(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _repondre(self, statut: int, corps: dict, entetes: dict | None = None):
            donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
            self.send_response(statut)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(donnees)))
            for k, v in (entetes or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(donnees)

        def do_POST(self):
            url = urllib.parse.urlparse(self.path)
            longueur = int(self.headers.get("Content-Length") or 0)
            try:
                corps = json.loads(self.rfile.read(longueur) or b"{}")
            except ValueError:
                return self._repondre(422, {"error": "json", "message": "corps JSON illisible"})
            APPELS.append((self.path, corps, dict(self.headers)))
            valeur = str(corps.get("texte") or corps.get("phone") or "")
            force = valeur[2:5] if valeur.startswith("__") and valeur.endswith("__") else None
            if force == "429":
                return self._repondre(429, {"error": "quota", "message": "quota journalier atteint (test)",
                                            "service": "lire"}, {"Retry-After": "120"})
            if force:
                return self._repondre(int(force), {"error": "test", "message": f"erreur {force} (test)"})
            chemin = url.path.rstrip("/")
            if chemin == "/v1/lire":
                texte = corps["texte"]
                return self._repondre(200, {"resultat": [_phrase(texte, " ".join("p" for _ in texte.split()))]})
            if chemin == "/v1/ecrire":
                phone = corps["phone"]
                return self._repondre(200, {"resultat": [_phrase(" ".join("o" for _ in phone.split()), phone)]})
            if chemin == "/v1/corriger":
                return self._repondre(200, {"resultat": {"texte": corps["texte"].replace("enfant ", "enfants "),
                                                         "corrections": [{"debut": 4, "fin": 10, "original": "enfant",
                                                                          "proposition": "enfants", "type": "accord",
                                                                          "confiance": 0.9, "motif": "nombre",
                                                                          "explication": "Après « Les », pluriel."}]}})
            if chemin.startswith("/v1/lexique/"):
                fonction = chemin.rsplit("/", 1)[1]
                if fonction == "frequence":
                    return self._repondre(200, {"resultat": 4.5})
                return self._repondre(404, {"error": "fonction_inconnue", "message": fonction})
            return self._repondre(404, {"error": "introuvable", "message": chemin})

    srv = ThreadingHTTPServer(("127.0.0.1", port), Gestion)
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
