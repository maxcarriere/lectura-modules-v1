# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Troisième juge des homophones : le juge du transducer (``lectura_nlp_fr.analyseur.juge``, encodeur bidirectionnel entraîné
à choisir, dans une phrase, la graphie d'un mot parmi ses homophones ; Module NLP, 18/10). Facultatif : si le modèle
n'est pas installé, le cœur s'en tient au modèle de langue écrit (KenLM). Le juge du Correcteur est le v2b, donné
explicitement (``charger(dossier)``) : jamais celui de l'écriture (v3).

``note(formes, j, recue, meilleure)`` : log P(meilleure) − log P(recue) d'après le juge, la phrase étant donnée par
ses mots (corrections déjà faites comprises) ; None quand le juge ne connaît pas le couple (mots hors de son
vocabulaire ou de groupes différents), auquel cas le modèle de langue reste seul juge."""

from __future__ import annotations

from pathlib import Path


class JugeHomophones:
    def __init__(self, juge):
        from lectura_nlp_fr.analyseur.relecture import mots_ecrits

        self._juge = juge
        self._mots = mots_ecrits
        from lectura_nlp_fr.analyseur.juge import LONGUEUR, UNK

        self._longueur, self._unk = LONGUEUR, UNK

    @classmethod
    def charger(cls, dossier: str | Path, fils: int = 1) -> "JugeHomophones":
        """Depuis ``dossier`` (``juge_int8.onnx``, ``vocab.txt``, ``groupes.npz``) : toujours explicite, jamais le juge
        branché sur la chaîne de l'Analyseur (voir ``lectura_nlp_fr.correcteur.trouver_juge``)."""
        from lectura_nlp_fr.analyseur.juge import Juge

        return cls(Juge.charger(Path(dossier), fils=fils))

    def empreinte(self) -> str | None:
        """sha256 du fichier ONNX du juge chargé."""
        return self._juge.empreinte()

    @property
    def modele(self):
        return getattr(self._juge, "modele", None)

    def note(self, formes: list[str], j: int, recue: str, meilleure: str) -> float | None:
        np = self._juge._np
        a, b = self._mots(recue), self._mots(meilleure)
        if len(a) != 1 or len(b) != 1:
            return None
        ia, ib = self._juge._id(a[0]), self._juge._id(b[0])
        if self._unk in (ia, ib) or ia == ib:
            return None
        g = self._juge._groupe(ia)
        if g < 0:
            return None
        membres = set(self._juge.membres[g].tolist())
        if ib not in membres:
            return None
        jetons, position = [], None
        for i, f in enumerate(formes):
            mots = self._mots(f) if i != j else a
            if i == j:
                position = len(jetons)
            jetons.extend(self._juge._id(w) for w in mots)
        if position is None:
            return None
        if len(jetons) > self._longueur:          # fenêtre centrée sur le mot jugé
            debut = max(0, min(position - self._longueur // 2, len(jetons) - self._longueur))
            jetons, position = jetons[debut:debut + self._longueur], position - debut
        logits = self._juge._logits(jetons, {position: [ia, ib]})
        ligne = logits[position, :2].astype(np.float64)
        return float(ligne[1] - ligne[0])
