# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Dictionnaire de l'utilisateur : mots qu'il ajoute (noms de proches, termes de métier, néologismes), reconnus par
Lexicon comme des formes acceptées et proposables, et par le Transducer branché (``transducer.brancher``).

Fichier texte UTF-8, une ligne par lecture, séparée par des tabulations (les lignes vides et celles qui commencent
par « # » sont ignorées) :

    graphie  prononciation (API, syllabée ou non ; facultative)  UPOS (facultatif)  lemme (facultatif)  zipf

Chemin par défaut : ``LECTURA_LEXICON_UTILISATEUR``, sinon ``~/.lectura/lexicon/utilisateur.tsv``.

    from lectura_lexicon import Lexicon
    lex = Lexicon(taille="standard", dictionnaire=True)       # fichier par défaut (créé au premier ajout)
    lex.dictionnaire.ajouter("Kélyan", "ke.ljɑ̃")              # enregistré aussitôt
    lex.validite("Kélyan")                                    # "proposable"
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from .cles import cle_phone, minuscule

ZIPF = 3.0          # fréquence prêtée à un mot ajouté : assez pour être proposé et préféré aux formes rares


@dataclass(frozen=True)
class Mot:
    ortho: str
    phone: str = ""
    upos: str = ""
    lemme: str = ""
    zipf: float = ZIPF

    def categorie(self) -> str:
        """UPOS donnée, sinon nom propre pour une graphie à majuscule, nom commun pour les autres."""
        return self.upos or ("PROPN" if self.ortho[:1].isupper() else "NOUN")


def chemin_par_defaut() -> Path:
    env = os.environ.get("LECTURA_LEXICON_UTILISATEUR")
    return Path(env) if env else Path.home() / ".lectura" / "lexicon" / "utilisateur.tsv"


class Dictionnaire:
    """Mots de l'utilisateur, en mémoire ; enregistrés dans ``chemin`` à chaque changement (``None`` : en mémoire
    seulement). ``version`` augmente à chaque changement (caches des branchements)."""

    def __init__(self, chemin: str | Path | None = None):
        self.chemin = Path(chemin) if chemin else None
        self.version = 0
        self._mots: dict[str, list[Mot]] = {}        # graphie en minuscules → lectures
        self._verrou = threading.Lock()
        if self.chemin is not None and self.chemin.exists():
            self._lire()

    # ── Fichier ────────────────────────────────────────────────────────────────

    def _lire(self) -> None:
        for ligne in self.chemin.read_text(encoding="utf-8").splitlines():
            if not ligne.strip() or ligne.startswith("#"):
                continue
            champs = (ligne.split("\t") + [""] * 5)[:5]
            ortho, phone, upos, lemme, zipf = (c.strip() for c in champs)
            if ortho:
                self._mettre(Mot(ortho, phone, upos, lemme, float(zipf) if zipf else ZIPF))

    def enregistrer(self) -> None:
        if self.chemin is None:
            return
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        provisoire = self.chemin.with_name(self.chemin.name + ".tmp")
        lignes = ["# Dictionnaire de l'utilisateur (lectura-lexicon) : graphie, prononciation, UPOS, lemme, zipf"]
        lignes += [f"{m.ortho}\t{m.phone}\t{m.upos}\t{m.lemme}\t{m.zipf:g}" for m in self.mots()]
        provisoire.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        provisoire.replace(self.chemin)

    # ── Mots ───────────────────────────────────────────────────────────────────

    def _mettre(self, mot: Mot) -> None:
        lectures = self._mots.setdefault(minuscule(mot.ortho), [])
        lectures[:] = [m for m in lectures if (m.ortho, cle_phone(m.phone)) != (mot.ortho, cle_phone(mot.phone))]
        lectures.append(mot)

    def ajouter(self, ortho: str, phone: str = "", upos: str = "", lemme: str = "", zipf: float = ZIPF) -> Mot:
        """Ajoute (ou remplace) une lecture de ``ortho`` et enregistre le fichier."""
        ortho = ortho.strip()
        if not ortho or "\t" in ortho:
            raise ValueError(f"graphie invalide : {ortho!r}")
        mot = Mot(ortho, phone.strip(), upos.strip(), lemme.strip(), zipf)
        with self._verrou:
            self._mettre(mot)
            self.version += 1
            self.enregistrer()
        return mot

    def retirer(self, ortho: str) -> bool:
        """Retire toutes les lectures de cette graphie exacte ; vrai si elle était présente."""
        with self._verrou:
            lectures = self._mots.get(minuscule(ortho), [])
            gardees = [m for m in lectures if m.ortho != ortho]
            if len(gardees) == len(lectures):
                return False
            if gardees:
                self._mots[minuscule(ortho)] = gardees
            else:
                del self._mots[minuscule(ortho)]
            self.version += 1
            self.enregistrer()
        return True

    def mots(self) -> list[Mot]:
        return sorted((m for lectures in self._mots.values() for m in lectures), key=lambda m: (minuscule(m.ortho), m.ortho))

    def lectures_min(self, mini: str) -> list[Mot]:
        """Lectures des graphies qui valent ``mini`` en minuscules."""
        return list(self._mots.get(mini, ()))

    def par_cle(self, cle: str) -> list[Mot]:
        """Lectures dont la prononciation a cette clé (sans frontières de syllabe)."""
        return [m for m in self.mots() if m.phone and cle_phone(m.phone) == cle]

    def __len__(self) -> int:
        return sum(len(v) for v in self._mots.values())

    def __contains__(self, ortho: str) -> bool:
        return any(m.ortho == ortho for m in self._mots.get(minuscule(ortho), ()))
