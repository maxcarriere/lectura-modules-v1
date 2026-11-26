# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Faux serveur de l'API ``/v1/traduire`` pour les tests (bibliothèque standard, 127.0.0.1 seulement).

Il suit la spécification de ``docs/API-HTTP.md`` et peut servir de référence au serveur réel :

- ``GET  /v1/traduire?source=&cible=``  → ``{"resultat": {"version", "paires", "tailles", "limites", …}}`` ;
- ``POST /v1/traduire``                 ``{"texte", "source", "cible", "options"}`` → ``{"resultat": {"texte", "phrases"}}`` ;
- ``POST /v1/traduire/aligner``         → ``{"resultat": {"liens"}}`` ;
- ``POST /v1/traduire/gloser``          → ``{"resultat": {"phrases"}}`` ;
- erreurs ``{"error", "message", "service"}`` : 400, 404, 413, 422, 429 (en-tête de test ``X-Test-Quota``).

Sans traducteur réel, il « traduit » de façon factice et déterministe (« [fr] » + la phrase), sans aucun modèle. Avec
``traducteurs={("en", "fr"): TraducteurLocal…}``, il appelle les vrais moteurs (contrôle « API = local »).
"""

from __future__ import annotations

import json
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TEXTE_MAX, GLOSE_MAX, MOTS_MAX, MOT_MAX = 2_000, 1_000, 200, 200
OPTIONS = {"aligner", "formules", "taille"}
PAIRES = {("en", "fr"), ("fr", "en")}
APPELS: list[tuple[str, dict]] = []       # (chemin, corps) reçus, pour les tests
UNITES: list[int] = []                    # unités décomptées par requête


class Factice:
    """Traduction factice : découpage aux fins de phrase, « [cible] » + la phrase, liens diagonaux."""

    def __init__(self, source: str, cible: str):
        self.source, self.cible = source, cible

    def traduire(self, texte, aligner=False, formules=True):
        phrases = []
        for m in re.finditer(r"\S[^.!?]*[.!?]*", texte):
            p = {"source": m.group(0).rstrip(), "debut": m.start(), "fin": m.start() + len(m.group(0).rstrip()),
                 "traduction": f"[{self.cible}] " + m.group(0).rstrip()}
            if aligner:
                ms = p["source"].split()
                mc = p["traduction"].split()[1:]
                p.update(mots_source=ms, mots_cible=mc, liens=[(i, i) for i in range(min(len(ms), len(mc)))])
            phrases.append(p)
        return {"texte": " ".join(p["traduction"] for p in phrases), "phrases": phrases}

    def aligner(self, ms, mc):
        return {(i, i) for i in range(min(len(ms), len(mc)))}

    def gloser(self, texte):
        sorties = []
        for p in self.traduire(texte)["phrases"]:
            mots = []
            for m in re.finditer(r"\w+", p["source"]):
                mots.append({"forme": m.group(0), "debut": p["debut"] + m.start(), "fin": p["debut"] + m.end(),
                             "lemme": m.group(0).lower(), "upos": "X", "phone": "", "ici": m.group(0),
                             "choix": "aucun", "sens": None, "autres": []})
            sorties.append({"source": p["source"], "traduction": p["traduction"], "mots": mots})
        return sorties


def demarrer(traducteurs: dict | None = None, port: int = 0):
    moteurs = traducteurs or {paire: Factice(*paire) for paire in PAIRES}

    class Gestion(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _repondre(self, statut: int, corps: dict):
            donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
            self.send_response(statut)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(donnees)))
            if statut == 200:
                self.send_header("X-Quota-Unite", "caracteres")
            if statut == 429:
                self.send_header("Retry-After", "3600")
            self.end_headers()
            self.wfile.write(donnees)

        def _erreur(self, statut: int, code: str, message: str):
            self._repondre(statut, {"error": code, "message": message, "service": "traduction"})

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path.rstrip("/") != "/v1/traduire":
                return self._erreur(404, "introuvable", url.path)
            self._repondre(200, {"resultat": {
                "version": "test", "paires": sorted(f"{s}-{c}" for s, c in moteurs),
                "tailles": {f"{s}-{c}": ["base"] for s, c in moteurs}, "aligneur": "precis", "glossaire": True,
                "limites": {"texte_max": TEXTE_MAX, "glose_max": GLOSE_MAX, "mots_max": MOTS_MAX}}})

        def do_POST(self):
            chemin = urllib.parse.urlparse(self.path).path.rstrip("/")
            longueur = int(self.headers.get("Content-Length") or 0)
            try:
                corps = json.loads(self.rfile.read(longueur) or b"{}")
            except ValueError:
                return self._erreur(422, "requete_invalide", "corps JSON illisible")
            APPELS.append((chemin, corps))
            if self.headers.get("X-Test-Quota"):
                return self._erreur(429, "quota", "quota journalier atteint (test)")
            if chemin == "/v1/traduire":
                return self._traduire(corps)
            if chemin == "/v1/traduire/aligner":
                return self._aligner(corps)
            if chemin == "/v1/traduire/gloser":
                return self._gloser(corps)
            return self._erreur(404, "introuvable", chemin)

        def _paire(self, source, cible):
            if (source, cible) not in moteurs:
                self._erreur(400, "requete_invalide", f"paire non prise en charge : {source} → {cible}")
                return None
            return moteurs[(source, cible)]

        def _traduire(self, corps):
            texte, options = corps.get("texte", ""), corps.get("options") or {}
            if not isinstance(texte, str) or not texte.strip():
                return self._erreur(400, "requete_invalide", "Texte vide.")
            if set(options) - OPTIONS:
                return self._erreur(422, "requete_invalide", f"options inconnues : {sorted(set(options) - OPTIONS)}")
            if options.get("taille", "base") != "base":
                return self._erreur(422, "requete_invalide", "taille « big » non servie par l'API publique")
            if len(texte) > TEXTE_MAX:
                return self._erreur(413, "trop_long", f"{len(texte)} caractères, {TEXTE_MAX} au plus par requête")
            m = self._paire(corps.get("source"), corps.get("cible"))
            if m is None:
                return
            UNITES.append(len(texte) * (2 if options.get("aligner") else 1))
            r = m.traduire(texte, aligner=bool(options.get("aligner")), formules=options.get("formules", True))
            self._repondre(200, {"resultat": r})

        def _aligner(self, corps):
            ms, mc = corps.get("mots_source") or [], corps.get("mots_cible") or []
            if not ms or not mc:
                return self._erreur(400, "requete_invalide", "Liste de mots vide.")
            if len(ms) > MOTS_MAX or len(mc) > MOTS_MAX:
                return self._erreur(413, "trop_long", f"{MOTS_MAX} mots au plus de chaque côté")
            if any(not isinstance(x, str) or len(x) > MOT_MAX for x in ms + mc):
                return self._erreur(422, "requete_invalide", f"mots : textes de {MOT_MAX} caractères au plus")
            m = self._paire(corps.get("source"), corps.get("cible"))
            if m is None:
                return
            UNITES.append(sum(map(len, ms + mc)))
            self._repondre(200, {"resultat": {"liens": sorted(m.aligner(ms, mc))}})

        def _gloser(self, corps):
            texte, source = corps.get("texte", ""), corps.get("source")
            if not isinstance(texte, str) or not texte.strip():
                return self._erreur(400, "requete_invalide", "Texte vide.")
            if len(texte) > GLOSE_MAX:
                return self._erreur(413, "trop_long", f"{len(texte)} caractères, {GLOSE_MAX} au plus par requête")
            m = self._paire(source, "fr" if source == "en" else "en")
            if m is None:
                return
            UNITES.append(4 * len(texte))
            self._repondre(200, {"resultat": {"phrases": m.gloser(texte)}})

    srv = ThreadingHTTPServer(("127.0.0.1", port), Gestion)
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"
