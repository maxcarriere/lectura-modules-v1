# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Alignement mot à mot entre une phrase et sa traduction, par l'attention des modèles OPUS-MT de base.

La traduction (venue de n'importe quel modèle, tc-big compris) est passée de force dans le modèle de base
(décodage forcé : ``target_prefix``) ; l'attention croisée donne, pour chaque sous-mot cible, une distribution sur les
sous-mots source. On remonte aux mots (moyenne des sous-mots), dans les deux sens (en→fr et fr→en), puis on
symétrise : intersection des meilleurs choix, élargie aux voisins (« grow-diag »).
"""
from __future__ import annotations

import numpy as np

from .modeles import dossier_modeles, dossier_traduction


class _Sens:
    """Un modèle de base (CTranslate2 int8) et ses sentencepiece, pour un sens."""

    def __init__(self, source: str, cible: str, fils: int, models_dir=None):
        try:
            import ctranslate2
            import sentencepiece as spm
        except ImportError as e:
            raise ImportError(f"aligneur léger : {e.name} absent ; pip install \"lectura-traducteur[local]\"") from e
        d = dossier_traduction(source, cible, "base", models_dir)
        self.sp = {False: spm.SentencePieceProcessor(model_file=str(d / "source.spm")),
                   True: spm.SentencePieceProcessor(model_file=str(d / "target.spm"))}
        self.modele = ctranslate2.Translator(str(d), device="cpu", compute_type="int8", intra_threads=fils)

    def _pieces(self, mots: list[str], cible: bool) -> tuple[list[str], list[int]]:
        """Sous-mots de la phrase et, pour chacun, l'indice de son mot."""
        pieces, mot_de = [], []
        for i, m in enumerate(mots):
            p = self.sp[cible].encode(m.replace("’", "'"), out_type=str)
            pieces += p
            mot_de += [i] * len(p)
        return pieces, mot_de

    def matrices(self, lots: list[tuple[list[str], list[str]]]) -> list[np.ndarray]:
        """Pour chaque couple (mots source, mots cible) : matrice [mots cible × mots source] d'attention."""
        src, tgt, infos = [], [], []
        for ms, mc in lots:
            ps, ds = self._pieces(ms, False)
            pc, dc = self._pieces(mc, True)
            src.append(ps + ["</s>"])
            tgt.append(pc)
            infos.append((ds, dc, len(ms), len(mc)))
        res = self.modele.translate_batch(src, target_prefix=tgt, beam_size=1, return_attention=True,
                                          max_decoding_length=max(len(t) for t in tgt) + 2)
        sorties = []
        for r, (ds, dc, ns, nc) in zip(res, infos):
            att = np.array(r.attention[0])[:len(dc), :len(ds)]  # sans </s> source ni la suite après le préfixe
            m = np.zeros((nc, ns))
            n = np.zeros((nc, ns))
            for j, wc in enumerate(dc):
                for i, ws in enumerate(ds):
                    m[wc, ws] += att[j, i]
                    n[wc, ws] += 1
            sorties.append(m / np.maximum(n, 1))
        return sorties


def symetriser(a_st: np.ndarray, a_ts: np.ndarray, mode: str = "grow") -> set[tuple[int, int]]:
    """``a_st`` : [cible × source] (modèle source→cible) ; ``a_ts`` : [source × cible] (modèle cible→source).
    Rend des couples (i source, j cible)."""
    st = {(int(a_st[j].argmax()), j) for j in range(a_st.shape[0])}
    ts = {(i, int(a_ts[i].argmax())) for i in range(a_ts.shape[0])}
    if mode == "st":
        return st
    if mode == "ts":
        return ts
    if mode == "union":
        return st | ts
    inter = st & ts
    if mode == "inter":
        return inter
    # grow-diag : ajouter les points de l'union voisins d'un point gardé, si l'un des deux mots est encore seul
    union = st | ts
    garde = set(inter)
    voisins = [(-1, 0), (0, -1), (1, 0), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    change = True
    while change:
        change = False
        for (i, j) in sorted(garde):
            for di, dj in voisins:
                p = (i + di, j + dj)
                if p in union and p not in garde:
                    src_seul = all(q[0] != p[0] for q in garde)
                    cib_seul = all(q[1] != p[1] for q in garde)
                    if src_seul or cib_seul:
                        garde.add(p)
                        change = True
    # final : points de l'union dont les deux mots sont encore seuls
    for p in sorted(union - garde):
        if all(q[0] != p[0] for q in garde) and all(q[1] != p[1] for q in garde):
            garde.add(p)
    return garde


class Aligneur:
    def __init__(self, langue_a: str = "en", langue_b: str = "fr", fils: int = 4, models_dir=None):
        self.ab = _Sens(langue_a, langue_b, fils, models_dir)
        self.ba = _Sens(langue_b, langue_a, fils, models_dir)

    def aligner(self, couples: list[tuple[list[str], list[str]]], mode: str = "grow",
                lot: int = 32) -> list[set[tuple[int, int]]]:
        """``couples`` : (mots en langue a, mots en langue b). Rend, pour chacun, les couples (i a, j b)."""
        sorties = []
        for k in range(0, len(couples), lot):
            c = couples[k:k + lot]
            m_ab = self.ab.matrices(c)
            m_ba = self.ba.matrices([(b, a) for a, b in c])
            sorties += [symetriser(x, y, mode) for x, y in zip(m_ab, m_ba)]
        return sorties


class AligneurMbert:
    """Alignement précis (méthode SimAlign) : vecteurs de mots de BERT multilingue (couche 8, moyenne des sous-mots),
    similarité cosinus, intersection des meilleurs choix dans les deux sens. Hansards en-fr : AER 5,7 % (attention
    OPUS-MT : 21,1 %), mesuré en octobre 2026 sur la version 0.1. Toute paire de langues.

    Modèle : ``mbert8/`` du dossier des modèles (mBERT coupé après la couche 8, ONNX int8), lu par onnxruntime."""

    def __init__(self, couche: int = 8, gpu: bool = False, fils: int = 4, models_dir=None):
        if couche != 8:
            raise ValueError("seul le modèle coupé après la couche 8 est livré")
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as e:
            raise ImportError(f"aligneur précis : {e.name} absent ; pip install \"lectura-traducteur[aligneur]\" "
                              "(ou aligneur=\"leger\")") from e
        dossier = dossier_modeles(models_dir) / "mbert8"
        if not (dossier / "mbert8_int8.onnx").is_file():
            from .modeles import ModelesAbsents
            raise ModelesAbsents(f"{dossier} absent : aligneur précis non installé (ou aligneur=\"leger\")")
        self.couche = couche
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = fils
        # GPU : même modèle ONNX ; CUDA s'il est disponible
        fournisseurs = (["CUDAExecutionProvider"] if gpu and "CUDAExecutionProvider" in ort.get_available_providers()
                        else []) + ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(dossier / "mbert8_int8.onnx"), opts, providers=fournisseurs)
        self.tok = Tokenizer.from_file(str(dossier / "tokenizer.json"))
        self.tok.enable_truncation(512)

    def _vecteurs(self, mots: list[str]) -> np.ndarray:
        e = self.tok.encode(mots, is_pretokenized=True)
        ids = e.word_ids
        h = self.session.run(None, {"input_ids": np.array([e.ids], dtype=np.int64),
                                    "attention_mask": np.array([e.attention_mask], dtype=np.int64)})[0][0]
        v = np.zeros((len(mots), h.shape[1]), dtype=np.float32)
        n = np.zeros(len(mots), dtype=np.float32)
        for t, i in enumerate(ids):
            if i is not None:
                v[i] += h[t]
                n[i] += 1
        v /= np.maximum(n, 1)[:, None]
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)

    def aligner(self, couples: list[tuple[list[str], list[str]]], mode: str = "inter+",
                lot: int = 32) -> list[set[tuple[int, int]]]:
        """``inter`` : intersection (AER 5,7 %) ; ``inter+`` : intersection, plus les liens « grow » des mots source
        restés seuls (pour le glossaire : un mot traduit librement garde un lien) ; ``grow`` (AER 9,8 %)."""
        sorties = []
        for a, b in couples:
            if not a or not b:
                sorties.append(set())
                continue
            sim = self._vecteurs(a) @ self._vecteurs(b).T
            st = {(int(sim[:, j].argmax()), j) for j in range(sim.shape[1])}
            ts = {(i, int(sim[i].argmax())) for i in range(sim.shape[0])}
            inter = st & ts
            if mode == "inter":
                sorties.append(inter)
                continue
            grow = symetriser(sim.T, sim, "grow")
            if mode == "grow":
                sorties.append(grow)
                continue
            seuls = {i for i in range(sim.shape[0])} - {i for i, _ in inter}
            sorties.append(inter | {(i, j) for i, j in grow if i in seuls})
        return sorties
