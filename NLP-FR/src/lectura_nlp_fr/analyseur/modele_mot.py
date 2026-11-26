# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Modèle de mot (GPA à couples) exporté en ONNX derrière l'interface ``ModeleDeMot``, sans torch.

Le modèle produit une suite de couples (phonème, graphème) : en G2P il lit la graphie, en P2G la prononciation.
Le décodage est glouton et contraint par l'entrée : à chaque pas, seuls sont permis les couples dont le côté lu
prolonge ce qui reste à lire ; les couples qui ne lisent rien (frontière de syllabe en G2P ; lettres muettes,
consonnes latentes, h aspiré, séparateurs en P2G) sont admis en nombre limité de suite. C'est la reprise exacte du
décodeur de l'instance Modèles (``GPA/couples.py``, ``GPA/donnees_couples.py``, ``GPA/decoder_couples.py``) ; les
deux graphes ONNX viennent de ``outils/onnx/exporter_modele_mot.py``.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from .analyse import Analyse, Couple, redresser

PAD, INC, DEBUT, FIN = "<PAD>", "<INC>", "<DEBUT>", "<FIN>"
SENS = ("g2p", "p2g")
MARQUES = (".", "‿")
ESPACE = "␣"
MAX_VIDES = 5
_H = "*h*"
_UNITE = re.compile(r"\{[^{}]*\}|\([^()]*\)|\[[^\]]*\]")


def phonemes(chaine: str) -> list[str]:
    res: list[str] = []
    for ch in chaine:
        if unicodedata.category(ch).startswith("M") and res:
            res[-1] += ch
        else:
            res.append(ch)
    return res


def projeter(phone_enrichi: str) -> str:
    """Forme brute : sans h aspiré ni consonne latente finale, sans ``( )`` ni ``[ ]``, première valeur des ``{ }``."""
    s = phone_enrichi[len(_H):] if phone_enrichi.startswith(_H) else phone_enrichi
    if s.endswith("]") and "[" in s:
        s = s[: s.rindex("[")]
    return _UNITE.sub(lambda m: m.group(0)[1:-1].split("|")[0] if m.group(0)[0] == "{" else "", s)


class Couples:
    def __init__(self, couples: list[tuple[str, str]]):
        self.liste = [(PAD, PAD), (INC, INC), (DEBUT, DEBUT), (FIN, FIN)] + couples
        self.pad, self.inc, self.debut, self.fin = 0, 1, 2, 3
        self.lu = {"g2p": [None] * 4, "p2g": [None] * 4}
        for p, g in couples:
            self.lu["g2p"].append("" if (p, g) == (".", ".") else g.replace(ESPACE, " "))
            self.lu["p2g"].append(tuple(x for x in phonemes(projeter(p)) if x not in MARQUES))
        self.vides = {s: [i for i in range(4, len(self.liste)) if not self.lu[s][i]] for s in SENS}
        self.par_premier: dict[str, dict] = {s: {} for s in SENS}
        for s in SENS:
            for i in range(4, len(self.liste)):
                lu = self.lu[s][i]
                if lu:
                    self.par_premier[s].setdefault(lu[0], []).append(i)
        self.point = next((i for i, c in enumerate(self.liste) if c == (".", ".")), None)

    def entree(self, sens: str, ortho: str, phone: str):
        if sens == "g2p":
            return ortho.lower()
        return [x for x in phonemes(projeter(phone).replace(" ", ESPACE)) if x not in MARQUES]

    def permis(self, sens: str, entree, pos: int, vides: int, dernier: int) -> list[int]:
        res = []
        if pos < len(entree):
            lus = self.lu[sens]
            for i in self.par_premier[sens].get(entree[pos], ()):
                if sens == "g2p":
                    if entree.startswith(lus[i], pos):
                        res.append(i)
                elif tuple(entree[pos : pos + len(lus[i])]) == lus[i]:
                    res.append(i)
        else:
            res.append(self.fin)
        if vides < MAX_VIDES:
            for i in self.vides[sens]:
                if i == self.point and (dernier == self.point or dernier == self.debut or pos >= len(entree)):
                    continue
                res.append(i)
        return res


class Vocabulaires:
    def __init__(self, symboles: list[str], upos: list[str], traits: list[str], couples: list[list[str]]):
        self.s2i = {s: i for i, s in enumerate(symboles)}
        self.u2i = {u: i for i, u in enumerate(upos)}
        self.t2i = {t: i for i, t in enumerate(traits)}
        self.n_traits = len(traits)
        self.couples = Couples([tuple(c) for c in couples])

    def ids(self, symboles) -> list[int]:
        return [self.s2i.get(s, 1) for s in symboles]

    def entree(self, sens: str, ortho: str, phone: str, presentation: str) -> tuple[list[int], list[int]]:
        if sens == "g2p":
            toks = list(ortho.lower())
            lus = list(range(len(toks)))
        else:
            toks, lus = [], []
            for x in phonemes(projeter(phone).replace(" ", ESPACE)):
                if x in MARQUES:
                    if presentation == "syllabee" or (presentation == "liaison" and x == "‿"):
                        toks.append(x)
                else:
                    lus.append(len(toks))
                    toks.append(x)
        ids = [self.s2i[f"<{sens}>"]] + self.ids(toks) + [self.s2i[FIN]]
        return ids, [i + 1 for i in lus] + [len(ids) - 1]


class ModeleDeMotOnnx:
    """Interface ``ModeleDeMot`` : ``aligner`` (graphie → couples) et ``graphier`` (prononciation → couples)."""

    def __init__(self, dossier: str | Path, fils: int = 1):
        import numpy as np
        import onnxruntime as ort

        self._np = np
        dossier = Path(dossier)
        options = ort.SessionOptions()
        options.intra_op_num_threads = fils
        self._preparation = ort.InferenceSession(str(dossier / "modele_mot_preparation.onnx"), options,
                                                 providers=["CPUExecutionProvider"])
        self._pas = ort.InferenceSession(str(dossier / "modele_mot_pas.onnx"), options, providers=["CPUExecutionProvider"])
        self._entrees_preparation = [e.name for e in self._preparation.get_inputs()]
        # Modèle v3 (attention sur les lettres du lemme) : la préparation rend aussi la mémoire du lemme, que chaque pas reçoit.
        self._memoire = "etats_lemme" in {e.name for e in self._pas.get_inputs()}
        d = json.loads((dossier / "modele_mot_vocabs.json").read_text(encoding="utf-8"))
        self._voc = Vocabulaires(d["symboles"], d["upos"], d["traits"], d["couples"])

    def aligner(self, forme: str, analyse: Analyse | None) -> tuple[Couple, ...] | None:
        return self._decoder(forme.lower(), "", analyse, "g2p", "pure")

    def graphier(self, phone: str, analyse: Analyse | None) -> tuple[Couple, ...] | None:
        presentation = "syllabee" if "." in phone or "‿" in phone else "pure"
        return self._decoder("", phone, analyse, "p2g", presentation)

    def _decoder(self, ortho: str, phone: str, analyse: Analyse | None, sens: str, presentation: str):
        np, voc, C = self._np, self._voc, self._voc.couples
        ids, lus = voc.entree(sens, ortho, phone, presentation)
        upos = voc.u2i.get((analyse.upos if analyse else "") or "_", 0)
        traits = np.zeros((1, voc.n_traits), dtype=np.float32)
        for k, v in sorted((analyse.feats if analyse else {}).items()):
            i = voc.t2i.get(f"{k}={v}")
            if i is not None:
                traits[0, i] = 1.0
        lemme = voc.ids(((analyse.lemme if analyse else "") or "").lower())
        valeurs = {
            "entree": np.array([ids], dtype=np.int64), "entree_lg": np.array([len(ids)], dtype=np.int64),
            "upos": np.array([upos], dtype=np.int64), "traits": traits,
            "lemme": np.array([lemme or [0]], dtype=np.int64), "lemme_lg": np.array([len(lemme)], dtype=np.int64),
            "indicateurs": np.array([[1.0, 1.0]], dtype=np.float32),
        }
        enc, cond, h, c, *memoire = self._preparation.run(None, {k: valeurs[k] for k in self._entrees_preparation})
        lemme_mem = dict(zip(("etats_lemme", "masque_lemme"), memoire)) if self._memoire else {}
        entree = C.entree(sens, ortho, phone)
        pos, vides, dernier, res = 0, 0, C.debut, []
        for _ in range(3 * len(entree) + 12):
            ok = C.permis(sens, entree, pos, vides, dernier)
            if not ok:
                break
            scores, h, c = self._pas.run(None, {
                "enc": enc, "cond": cond, "precedent": np.array([[dernier]], dtype=np.int64),
                "pointeur": np.array([[lus[min(pos, len(entree))]]], dtype=np.int64), "h": h, "c": c, **lemme_mem,
            })
            i = max(ok, key=lambda k: scores[0, 0, k])
            if i == C.fin:
                break
            res.append(C.liste[i])
            n = len(C.lu[sens][i])
            pos += n
            vides = 0 if n else vides + 1
            dernier = i
        if not res:
            return None
        return redresser(tuple(Couple(p, " " if g == ESPACE else g) for p, g in res))
