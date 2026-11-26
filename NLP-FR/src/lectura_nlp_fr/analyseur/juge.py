# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Juge des homophones : relecture de l'écriture (phonétique → orthographe) par un encodeur entraîné à choisir, dans
une phrase, la graphie de chaque mot ambigu parmi ses homophones (2026-10-18).

Chaque mot ambigu de la phrase n'est donné au modèle que par son groupe d'homophones (sa prononciation) ; le modèle
lit la phrase entière dans les deux sens et note les graphies que l'écriture propose. On retient, mot par mot,
log P(juge) + ``poids`` × (note − meilleure note de la chaîne). Le juge ne départage que les membres du groupe du mot
écrit (les seules graphies qu'il a appris à noter) et laisse les interjections à l'écriture.

Facultatif : livré à part du paquet (52 Mo), dans un dossier ``juge/`` qui contient ``juge_int8.onnx`` (ou
``juge.onnx``), ``vocab.txt`` et ``groupes.npz``, cherché par ``trouver`` : ``LECTURA_JUGE_DIR``, ``juge/`` dans le dossier
des modèles du transducer, ``$LECTURA_MODELS_DIR/juge``, ``~/.lectura/models/juge``. Absent, l'écriture se fait sans
lui.

Mesures (juge_v2b, poids 0,25 ; erreurs de mots de l'écriture depuis la phonétique) : phrases fautives des bancs STT
2 366 → 1 965 (−17 %), cadre dev + test sans chiffres (3 000 phrases) 2 575 → 2 370 (−8 %).

Branchement : ``Juge.charger(dossier).brancher(chaine)`` (accroche ``chaine.recherche``) ; ``MoteurLocal`` le
branche d'office quand il le trouve (option ``juge=False`` pour s'en passer).
"""

from __future__ import annotations

import os
from pathlib import Path

from .relecture import Relecture, mots_ecrits
from .structures import TypeMot

DOSSIER = "juge"
POIDS = 0.25
LONGUEUR = 64
UNK = 1
# Hésitations de l'oral, presque absentes des textes d'entraînement (le juge changeait « euh » en « eux ») : laissées
# au choix de l'écriture.
INTERJECTIONS = {"euh", "heu", "bah", "ben", "hum", "hm", "mh", "ah", "oh", "eh", "hein", "bof", "pff", "ouf", "hé"}


def trouver(dossier_modeles: Path | None = None) -> Path | None:
    """Dossier du juge, ou None s'il n'est pas installé."""
    candidats = []
    if os.environ.get("LECTURA_JUGE_DIR"):
        candidats.append(Path(os.environ["LECTURA_JUGE_DIR"]))
    if dossier_modeles is not None:
        candidats.append(Path(dossier_modeles) / DOSSIER)
    if os.environ.get("LECTURA_MODELS_DIR"):
        candidats.append(Path(os.environ["LECTURA_MODELS_DIR"]) / DOSSIER)
    candidats.append(Path.home() / ".lectura" / "models" / DOSSIER)
    return next((d for d in candidats if (d / "vocab.txt").exists() and (d / "groupes.npz").exists()), None)


class Juge:
    def __init__(self, session, vocab: list[str], groupe_de, membres, poids: float = POIDS):
        import numpy as np

        self._np = np
        self.session, self.poids = session, poids
        self.ident = {w: i for i, w in enumerate(vocab)}
        self.groupe_de, self.membres = groupe_de, membres

    @classmethod
    def charger(cls, dossier: str | Path, poids: float = POIDS, fils: int = 1) -> "Juge":
        import numpy as np
        import onnxruntime as ort

        dossier = Path(dossier)
        modele = dossier / "juge_int8.onnx"
        if not modele.exists():
            modele = dossier / "juge.onnx"
        options = ort.SessionOptions()
        options.intra_op_num_threads = fils
        session = ort.InferenceSession(str(modele), options, providers=["CPUExecutionProvider"])
        vocab = (dossier / "vocab.txt").read_text(encoding="utf-8").split("\n")[:-1]
        g = np.load(dossier / "groupes.npz")
        juge = cls(session, vocab, g["groupe_de"], g["membres"], poids)
        juge.modele = modele
        return juge

    modele: Path | None = None              # fichier ONNX chargé (``charger``)

    def empreinte(self) -> str | None:
        """sha256 du fichier ONNX chargé : il identifie la version du juge (v2b, v3…) dans les journaux et les tests."""
        if self.modele is None:
            return None
        import hashlib

        h = hashlib.sha256()
        with open(self.modele, "rb") as f:
            for bloc in iter(lambda: f.read(1 << 20), b""):
                h.update(bloc)
        return h.hexdigest()

    def brancher(self, chaine) -> None:
        chaine.recherche = self

    def _id(self, mot: str) -> int:
        return self.ident.get(mot, UNK)

    def _groupe(self, x: int) -> int:
        return int(self.groupe_de[x]) if x != UNK else -1

    def _logits(self, jetons: list[int], juges: dict[int, list[int]]):
        """Logits (L, T) : à chaque position jugée, notes des graphies ``juges[j]`` ; les autres mots ambigus sont
        donnés par leur groupe, comme à l'entraînement."""
        np = self._np
        L = LONGUEUR                         # longueur fixe du modèle exporté ; fin de phrase complétée par 0 (masqué)
        groupes = np.full((1, L), -1, dtype=np.int64)
        lignes: dict[int, list[int]] = {}
        for j, x in enumerate(jetons):
            g = self._groupe(x)
            if j in juges:
                groupes[0, j] = g if g >= 0 else -2
                lignes[j] = juges[j]
            elif g >= 0:
                groupes[0, j] = g
                lignes[j] = [c for c in self.membres[g].tolist() if c >= 0]
        largeur = max(len(c) for c in lignes.values())
        candidats = np.full((1, L, largeur), -1, dtype=np.int64)
        for j, c in lignes.items():
            candidats[0, j, : len(c)] = c
        mots = np.zeros((1, L), dtype=np.int64)
        mots[0, : len(jetons)] = jetons
        return self.session.run(None, {"mots": mots, "groupes": groupes, "candidats": candidats})[0][0]

    def choisir(self, chaine, mots, analyses, inverses, entrees):
        np = self._np
        options = Relecture._options(None, chaine, mots, analyses, inverses, entrees)
        jetons, positions = [], []           # (indice du jeton, indice du mot, [(k, id)])
        for i, opts in enumerate(options):
            e = entrees[i]
            ecrits = mots_ecrits(e.ortho) if e is not None else []
            if len(opts) > 1 and len(ecrits) == 1 and ecrits[0] not in INTERJECTIONS:
                g = self._groupe(self._id(ecrits[0]))
                if g >= 0:
                    membres = set(self.membres[g].tolist())
                    dans = [(k, self._id(o[1][0])) for k, o in enumerate(opts) if len(o[1]) == 1]
                    dans = [(k, x) for k, x in dans if x in membres]
                    if len({x for _, x in dans}) > 1:
                        positions.append((len(jetons), i, dans))
            if e is None and (mots[i].type is TypeMot.FORMULE or getattr(analyses[i], "upos", "") == "NUM"):
                ecrits = ["<nombre>"]        # comme à l'entraînement (``mots_ecrits``) : « 53 ans » et non « ans » seul
            jetons.extend(self._id(w) for w in ecrits)
        if not positions or len(jetons) > LONGUEUR:
            return entrees
        logits = self._logits(jetons, {j: [x for _, x in c] for j, _, c in positions})
        choisies = list(entrees)
        for j, i, cands in positions:
            ligne = logits[j, : len(cands)].astype(np.float64)
            logp = ligne - ligne.max() - np.log(np.exp(ligne - ligne.max()).sum())
            # Graphies de même identifiant (« cœur » / « coeur ») : la note de la chaîne les départage.
            notes = [logp[c] + (self.poids + 1e-6) * options[i][k][2] for c, (k, _) in enumerate(cands)]
            choisies[i] = options[i][cands[int(np.argmax(notes))][0]][0]
        return choisies
