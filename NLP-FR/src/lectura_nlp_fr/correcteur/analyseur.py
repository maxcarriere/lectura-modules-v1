# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Analyseur à canal par mot : une phrase écrite dont certains mots ne sont donnés que par leur prononciation.

Depuis le 15/10, ``lectura_nlp_fr.analyseur.adaptateurs.analyseur_onnx.AnalyseurOnnx`` publie ``analyser_mixte(formes,
phones, canaux, types, cles, correction)`` → ``(analyses, details)`` et la classe ``Detail`` (repris du code du
correcteur). Ici ne reste qu'une enveloppe qui fixe la porte de l'adaptateur de correction (``correction``, 1 par
défaut pour le correcteur), vérifie que le graphe a bien un canal par mot (export ``outils/exporter_tagger.py``) et,
quand un dossier contient aussi ``analyseur_lot.onnx`` (export ``outils/exporter_tagger_lot.py``) ou sa version int8,
analyse en un seul passage les K variantes d'une phrase que le correcteur relit mot à mot (``analyser_variantes``).
``partager`` construit l'enveloppe sur la session ONNX d'un analyseur déjà chargé (celui du transducer du serveur) :
un seul graphe en mémoire.
"""

from __future__ import annotations

from pathlib import Path

from lectura_nlp_fr.analyseur.adaptateurs.analyseur_onnx import AnalyseurOnnx, Detail, _softmax

__all__ = ["AnalyseurCanaux", "Detail"]

_CANAUX = {"dual": (1.0, 1.0), "ortho": (1.0, 0.0), "phone": (0.0, 1.0)}
_LOTS = ("analyseur_lot_int8.onnx", "analyseur_lot.onnx")   # int8 (outils/quantifier_lot.py) : 4× plus petit, 20 % plus rapide


class AnalyseurCanaux(AnalyseurOnnx):
    def __init__(self, dossier: str | Path, fils: int = 1, correction: float = 1.0, lot: bool = True,
                 dossier_lot: str | Path | None = None):
        """``correction`` : porte de l'adaptateur de correction (graphe exporté avec un adaptateur LoRA) ; 0 = modèle
        de base, sorties identiques à celles du graphe sans adaptateur. ``lot`` : utiliser le graphe par variantes
        (``analyseur_lot_int8.onnx`` ou ``analyseur_lot.onnx``) s'il existe dans ``dossier`` ou ``dossier_lot`` (dossier
        de modèles du correcteur : le graphe à une phrase est celui du transducer, le graphe par lot est au correcteur)."""
        super().__init__(dossier, fils=fils)
        self._preparer(correction, [dossier, dossier_lot] if lot else [], fils)

    @classmethod
    def partager(cls, analyseur: AnalyseurOnnx, correction: float = 1.0, dossier_lot: str | Path | None = None,
                 fils: int = 1) -> "AnalyseurCanaux":
        """Même session ONNX (et mêmes tables) qu'un ``AnalyseurOnnx`` déjà chargé — l'analyseur à porte du transducer
        du serveur — plus le graphe par variantes du correcteur : un seul graphe à une phrase en mémoire."""
        obj = cls.__new__(cls)
        obj.__dict__.update(analyseur.__dict__)
        dossier = getattr(analyseur._session, "_model_path", None)
        obj._preparer(correction, [Path(dossier).parent if dossier else None, dossier_lot], fils)
        return obj

    def _preparer(self, correction: float, dossiers, fils: int) -> None:
        forme = self._session.get_inputs()[[e.name for e in self._session.get_inputs()].index("canal")].shape
        if len(forme) != 2 or not self.porte:
            raise ValueError("analyseur sans porte de correction ni canal par mot ; exporter avec "
                             "Correcteur/outils/exporter_tagger.py")
        self.correction = correction
        self._session_lot = None
        self.fichier_lot = None
        for fichier in (Path(d) / nom for d in dossiers if d is not None for nom in _LOTS):
            if fichier.exists():
                import onnxruntime as ort

                options = ort.SessionOptions()
                options.intra_op_num_threads = fils
                options.enable_cpu_mem_arena = False          # 16/10 : −150 Mo de RSS sur les textes longs, vitesse égale
                self._session_lot = ort.InferenceSession(str(fichier), options, providers=["CPUExecutionProvider"])
                self.fichier_lot = fichier
                break

    @property
    def par_lot(self) -> bool:
        return self._session_lot is not None

    def analyser_variantes(self, formes: list[str], phones: list[str], canaux: list[str], types: list[str],
                           variantes: list[tuple[int, str]], correction: float | None = None) -> list[Detail]:
        """K variantes de la phrase (canaux communs), chacune relisant le mot ``j`` en prononciation seule avec, si
        ``cle`` est donnée, ses graphies candidates (tête de graphie) ; rend le ``Detail`` du mot ``j`` de chaque
        variante — ce que ``analyser_mixte`` donnerait pour ``details[j]``, en un seul passage du graphe."""
        if not variantes:
            return []
        if self._session_lot is None:
            res = []
            for j, cle in variantes:
                c = list(canaux)
                c[j] = "phone"
                _a, details = self.analyser_mixte(formes, phones, c, types, ["" if i != j else cle for i in range(len(formes))],
                                                  correction)
                res.append(details[j])
            return res
        np = self._np
        n, k = len(formes), len(variantes)
        chars, lc = self._tableau([self._forme(f) for f in formes])
        ph, lp = self._tableau([self._phones(p, f) for p, f in zip(phones, formes)])
        canal = np.tile(np.array([_CANAUX[c] for c in canaux], dtype=np.float32), (k, 1, 1))
        candidats = []
        for v, (j, cle) in enumerate(variantes):
            canal[v, j] = _CANAUX["phone"]
            candidats.append(self._candidats.get(cle.replace(".", "").replace("‿", ""), []) if cle else [])
        g = np.zeros((k, n, max(1, max(len(c) for c in candidats))), dtype=np.int64)
        for v, (j, _cle) in enumerate(variantes):
            g[v, j, : len(candidats[v])] = candidats[v]
        m = self._types.get("m", 0)
        flux = {"chars": chars, "longueurs_chars": lc, "phones": ph, "longueurs_phones": lp, "canal": canal,
                "types": np.array([self._types.get(t, m) for t in types], dtype=np.int64), "graphies": g,
                "correction": np.array([self.correction if correction is None else correction], dtype=np.float32)}
        sorties = dict(zip(self._sorties, self._session_lot.run(None, flux)))
        details = []
        for v, (j, _cle) in enumerate(variantes):
            p_pos = _softmax(np, sorties["pos"][v, j])
            detail = Detail(upos={self._i2pos[i]: float(p) for i, p in enumerate(p_pos) if p > 0.01})
            for f in self._traits:
                pt = _softmax(np, sorties[f"trait_{f}"][v, j])
                detail.traits[f] = {self._i2m[f].get(i, "_"): float(p) for i, p in enumerate(pt) if p > 0.01}
            if len(candidats[v]) > 1:
                pg = _softmax(np, sorties["graphie"][v, j, : len(candidats[v])])
                detail.graphies = {self._i2g[c]: float(p) for c, p in zip(candidats[v], pg)}
            details.append(detail)
        return details
