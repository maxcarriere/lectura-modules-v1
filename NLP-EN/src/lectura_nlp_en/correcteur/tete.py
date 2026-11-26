# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Tête de graphie du modèle de phrase anglais, en juge des homophones (graphe ONNX à canal par mot).

Le mot examiné n'est donné que par sa prononciation (canal (0, 1)), les autres mots par leurs deux canaux : la tête de
graphie dit quelle graphie le contexte écrit attend parmi les homophones du lexique (their / there / they're…). Graphe :
``outils/exporter_tagger_lora.py`` (entrée ``correction`` : porte de l'adaptateur, 0 = modèle de base ``modele_en4b``).

    tete = TeteGraphie("modeles/onnx_lora_en_v1_fp16")
    tete.probas(jetons, k)                 # {"their": 0.97, "there": 0.02, "they're": 0.01}
"""

from __future__ import annotations

import json
from pathlib import Path


def _softmax(np, x):
    e = np.exp(x - x.max())
    return e / e.sum()


def _type(t) -> str:
    """Type du découpage (celui que la chaîne donne à l'analyseur) d'un jeton de surface du correcteur."""
    from ..analyseur.structures import TypeMot

    h = t.lus[0]
    if h.mot.type is TypeMot.PONCTUATION:
        return "p"
    if h.origine == "formule":
        return "f:nombre"
    if h.mot.abregement:
        return f"a:{h.mot.abregement}"
    if h.mot.type is TypeMot.FORMULE:
        return f"f:{h.mot.type_formule}" if h.mot.type_formule else "s"
    return "m"


def phone_jeton(t) -> str:
    """Prononciation d'un jeton de surface ; une contraction (it's, they're) réunit celles de ses mots."""
    if len(t.lus) > 1:
        return "".join((l.phone or "").strip("‿ ") for l in t.lus)
    return t.phone


class TeteGraphie:
    def __init__(self, dossier: str | Path, fils: int = 1, correction: float = 1.0):
        import numpy as np
        import onnxruntime as ort
        from ..analyseur.adaptateurs.analyseur_onnx import _encoder_forme, _ids_ponctuation, _Vocabulaires

        dossier = Path(dossier)
        options = ort.SessionOptions()
        options.intra_op_num_threads = fils
        self.np = np
        self.session = ort.InferenceSession(str(dossier / "analyseur.onnx"), options, providers=["CPUExecutionProvider"])
        d = json.loads((dossier / "analyseur_vocabs.json").read_text(encoding="utf-8"))
        if not d.get("canal_par_mot"):
            raise ValueError("graphe sans canal par mot (exporter avec outils/exporter_tagger_lora.py)")
        self.noms = d["sorties"]
        self.tg = _Vocabulaires(d)
        self.g2i = self.tg.graphies["graphie2idx"]
        self._forme, self._ponct = _encoder_forme, _ids_ponctuation
        self.correction = correction

    @staticmethod
    def cle(phone: str) -> str:
        return "".join(c for c in phone if c not in ".‿ ˈˌ")

    def candidats(self, phone: str) -> list[str]:
        return [self.tg.i2g[i] for i in self.tg.graphies["candidats"].get(self.cle(phone), [])]

    def _phones(self, phone: str, forme: str, type_: str) -> list[int]:
        tg = self.tg
        if type_ != "p" and phone:
            ids = [tg.phone2idx.get(x, tg.pu) for x in tg.iter_phonemes(phone)]
            if ids:
                return ids
        return self._ponct(forme, tg.phone2idx, tg.pu) or [tg.pu]

    def probas(self, jetons, k: int, phone: str | None = None, correction: float | None = None,
               formes: dict[int, str] | None = None) -> dict[str, float]:
        """p(graphie) du jeton ``k`` donné par sa prononciation (``phone``, défaut : celle de la chaîne) dans la phrase
        écrite ; ``formes`` : formes à substituer (corrections déjà faites). Vide si moins de deux candidats."""
        np, tg = self.np, self.tg
        phone = phone_jeton(jetons[k]) if phone is None else phone
        cands = self.candidats(phone)
        if len(cands) < 2:
            return {}
        formes = formes or {}
        chars, phones, types, canal = [], [], [], []
        for i, t in enumerate(jetons):
            ty = _type(t)
            f = formes.get(i, t.forme)
            chars.append(self._forme(f if i != k else "x", tg.c2i))
            phones.append(self._phones(phone if i == k else phone_jeton(t), f, ty))
            types.append(tg.type2idx.get(ty, tg.type2idx.get("m", 0)))
            canal.append((0.0, 1.0) if i == k else (1.0, 1.0) if ty != "p" else (1.0, 0.0))
        g = np.zeros((len(jetons), len(cands)), dtype=np.int64)
        g[k] = [self.g2i[c] for c in cands]
        c, lc = self._tableau(chars)
        p, lp = self._tableau(phones)
        flux = {"chars": c, "longueurs_chars": lc, "phones": p, "longueurs_phones": lp,
                "canal": np.array(canal, dtype=np.float32), "types": np.array(types, dtype=np.int64), "graphies": g,
                "correction": np.array([self.correction if correction is None else correction], dtype=np.float32)}
        sortie = self.session.run(["graphie"], flux)[0]
        pg = _softmax(np, sortie[0, k, : len(cands)].astype(np.float64))
        return dict(zip(cands, map(float, pg)))

    def _tableau(self, suites):
        np = self.np
        lg = np.array([len(s) for s in suites], dtype=np.int64)
        t = np.zeros((len(suites), max(1, int(lg.max()))), dtype=np.int64)
        for i, s in enumerate(suites):
            t[i, : len(s)] = s
        return t, lg
