# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Analyseur exporté en ONNX (``outils/onnx/exporter_tagger.py``) derrière l'interface ``Analyseur``.

Inférence sans torch : onnxruntime et numpy. Mêmes entrées et mêmes décisions que l'enveloppe torch de l'instance
Modèles (``evaluer_tagger.Tagger``) : caractères en minuscules précédés d'une marque de casse, phonèmes, canal
(dual, ortho, phone) ; traits retenus selon la catégorie, lemme par classe ou par motif de suffixe. Un modèle qui a
une table des types de mots (modèle 2 v3, entrée ``types``) reçoit le type de chaque mot et, en phonétique, le symbole
de chaque signe de ponctuation (``<P:,>``, sinon ``<PONCT>``). Un modèle qui a une tête de graphie (entrée
``graphies``) choisit, en phonétique, la graphie de chaque mot parmi ses homophones, cherchés sous la clé du mot
(prononciation sans « . », sans « ‿ » et sans consonne de liaison). Un graphe à porte (``Correcteur/outils/
exporter_tagger.py`` : canal par mot, entrée ``correction``) accepte aussi une phrase à canal mixte
(``analyser_mixte`` : mots écrits et mots donnés par leur seule prononciation), pour le correcteur.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ..analyse import Analyse, par_tranches

_CANAUX = {"dual": (1.0, 1.0), "ortho": (1.0, 0.0), "phone": (0.0, 1.0)}


@dataclass
class Detail:
    """Probabilités d'un mot (``analyser_mixte``) : graphie → p (parmi les candidates de la tête de graphie),
    trait → {valeur: p}, UPOS → p (au-delà de 1 %)."""

    graphies: dict[str, float] = field(default_factory=dict)
    traits: dict[str, dict[str, float]] = field(default_factory=dict)
    upos: dict[str, float] = field(default_factory=dict)


def _softmax(np, x):
    e = np.exp(x - x.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


def _phonemes(ipa: str) -> list[str]:
    """Phonèmes d'une chaîne IPA, diacritiques rattachés au caractère précédent (« ɑ̃ »)."""
    resultat: list[str] = []
    for c in ipa:
        if unicodedata.category(c).startswith("M") and resultat:
            resultat[-1] += c
        else:
            resultat.append(c)
    return resultat


def _appliquer_motif(forme: str, motif: tuple[str, str]) -> str:
    """Lemme par motif de suffixe (« mangeons », (« eons », « er ») → « manger ») ; motif qui ne s'applique pas :
    la forme telle quelle."""
    retirer, ajouter = motif
    if retirer and not forme.endswith(retirer):
        return forme
    return forme[: len(forme) - len(retirer)] + ajouter


class AnalyseurOnnx:
    def __init__(self, dossier: str | Path, fichier: str = "analyseur.onnx", fils: int = 1):
        import numpy as np
        import onnxruntime as ort

        self._np = np
        dossier = Path(dossier)
        options = ort.SessionOptions()
        options.intra_op_num_threads = fils
        self._session = ort.InferenceSession(str(dossier / fichier), options, providers=["CPUExecutionProvider"])
        d = json.loads((dossier / "analyseur_vocabs.json").read_text(encoding="utf-8"))
        v = d["vocabs"]
        self._c2i = v["char2idx"]
        self._p2i = d["phone2idx"]
        self._pu = self._p2i.get("<UNK>", 1)
        self._i2pos = {i: p for p, i in v["pos2idx"].items()}
        self._i2m = {f: {i: x for x, i in voc.items()} for f, voc in v["morpho_vocabs"].items()}
        self._i2li = {i: x for x, i in v["liaison2idx"].items()}
        self._i2dep = {i: x for x, i in v["deprel2idx"].items()}
        self._i2mwt = {i: x for x, i in v["mwt_decomp2idx"].items()}
        self._classes = {int(k): x for k, x in v["lemme_classes"].items()}
        self._motifs = {int(k): tuple(x) for k, x in v["lemme_motifs"].items()}
        self._traits = d["traits"]
        self._valides = {u: set(t) for u, t in d["traits_par_upos"].items()}
        self._sorties = d["sorties"]
        self._types = v.get("type2idx") or {}
        formes_entrees = {e.name: e.shape for e in self._session.get_inputs()}
        entrees = set(formes_entrees)
        # Graphe à porte du Correcteur (adaptateur LoRA, 15/10) : canal donné par mot, entrée ``correction`` ;
        # porte 0 (défaut) = analyseur sans adaptateur, au bit près ; 1 = adaptateur de correction actif.
        self._canal_par_mot = len(formes_entrees.get("canal") or [2]) == 2
        self.porte = "correction" in entrees
        self.correction = 0.0
        self.types_de_mots = bool(self._types) and "types" in entrees
        g = v.get("graphies") if "graphies" in entrees else None
        self.tete_graphie = bool(g)
        if g:
            self._candidats = g["candidats"]
            self._i2g = {i: x for x, i in g["graphie2idx"].items()}

    # ── Interface ``Analyseur`` ────────────────────────────────────────────────

    def analyser(self, formes: list[str], types: list[str] | None = None) -> list[Analyse]:
        return self._analyser(formes, [""] * len(formes), "ortho", types)

    def analyser_phone(self, phones: list[str], formes: list[str] | None = None, types: list[str] | None = None,
                       cles: list[str] | None = None) -> list[Analyse]:
        """``cles`` : clé de recherche des graphies homophones de chaque mot (tête de graphie)."""
        return self._analyser(formes or [""] * len(phones), phones, "phone", types, cles)

    def analyser_dual(self, formes: list[str], phones: list[str], types: list[str] | None = None) -> list[Analyse]:
        return self._analyser(formes, phones, "dual", types)

    def analyser_mixte(self, formes: list[str], phones: list[str], canaux: list[str], types: list[str] | None = None,
                       cles: list[str] | None = None, correction: float | None = None) -> tuple[list[Analyse], list[Detail]]:
        """Phrase à canal par mot (graphe à porte seulement) : ``canaux[i]`` vaut « dual », « ortho » ou « phone » (le
        mot n'est donné que par sa prononciation) ; ``cles[i]`` : clé des graphies homophones (tête de graphie) des mots
        dont on veut la graphie, vide sinon ; ``correction`` : porte de l'adaptateur (défaut : ``self.correction``).
        Rend les analyses et, pour chaque mot, ses probabilités (``Detail``). Repris du Correcteur
        (``lectura_nlp_fr.correcteur.analyseur.AnalyseurCanaux``, 15/10)."""
        if not self._canal_par_mot:
            raise ValueError("analyser_mixte demande un graphe à canal par mot (graphe à porte du Correcteur)")
        np = self._np
        if not formes:
            return [], []
        chars, lc = self._tableau([self._forme(f if c != "phone" else "") for f, c in zip(formes, canaux)])
        ph, lp = self._tableau([self._phones(p, f) for p, f in zip(phones, formes)])
        flux = {"chars": chars, "longueurs_chars": lc, "phones": ph, "longueurs_phones": lp,
                "canal": np.array([_CANAUX[c] for c in canaux], dtype=np.float32)}
        if self.types_de_mots:
            m = self._types.get("m", 0)
            flux["types"] = np.array([self._types.get(t, m) for t in (types or ["m"] * len(formes))], dtype=np.int64)
        candidats: list[list[int]] = [[] for _ in formes]
        if self.tete_graphie:
            if cles:
                candidats = [self._candidats.get(c.replace(".", "").replace("‿", ""), []) if c else [] for c in cles]
            g = np.zeros((len(formes), max(1, max(len(c) for c in candidats))), dtype=np.int64)
            for i, c in enumerate(candidats):
                g[i, : len(c)] = c
            flux["graphies"] = g
        if self.porte:
            flux["correction"] = np.array([self.correction if correction is None else correction], dtype=np.float32)
        sorties = dict(zip(self._sorties, self._session.run(None, flux)))
        p_pos = _softmax(np, sorties["pos"][0])
        p_tetes = _softmax(np, sorties["tetes"][0])
        choix = {k: v[0].argmax(-1) for k, v in sorties.items()}
        analyses, details = [], []
        for i, forme in enumerate(formes):
            upos = self._i2pos[int(choix["pos"][i])]
            traits = {}
            detail = Detail(upos={self._i2pos[j]: float(p) for j, p in enumerate(p_pos[i]) if p > 0.01})
            for f in self._valides.get(upos, ()):
                val = self._i2m[f].get(int(choix[f"trait_{f}"][i]), "_")
                if val not in ("_", "<PAD>"):
                    traits[f] = val
            for f in self._traits:
                pt = _softmax(np, sorties[f"trait_{f}"][0][i])
                detail.traits[f] = {self._i2m[f].get(j, "_"): float(p) for j, p in enumerate(pt) if p > 0.01}
            if len(candidats[i]) > 1:
                pg = _softmax(np, sorties["graphie"][0][i][: len(candidats[i])])
                detail.graphies = {self._i2g[c]: float(p) for c, p in zip(candidats[i], pg)}
            classe = int(choix["lemme_classe"][i])
            lemme = self._classes.get(classe, "") if classe else _appliquer_motif(
                forme.lower(), self._motifs.get(int(choix["lemme_motif"][i]), ("", "")))
            amalgame = self._i2mwt.get(int(choix["mwt"][i]), "none")
            graphie = max(detail.graphies, key=detail.graphies.get) if detail.graphies else ""
            analyses.append(Analyse(
                upos, traits, lemme.lower(), int(choix["tetes"][i]) - 1, self._i2dep[int(choix["deprel"][i])],
                float(p_pos[i].max()), amalgame=("" if amalgame in ("none", "<PAD>") else amalgame).split(":")[0],
                confiance_tete=float(p_tetes[i].max()), graphie=graphie, graphies=tuple(detail.graphies)))
            details.append(detail)
        return analyses, details

    # ── Inférence ──────────────────────────────────────────────────────────────

    def _forme(self, forme: str) -> list[int]:
        unk = self._c2i.get("<UNK>", 1)
        ids = [self._c2i.get(c, unk) for c in forme.lower()] or [unk]
        if "<MAJ>" in self._c2i and forme[:1].isupper():
            ids = [self._c2i["<CAPS>" if len(forme) > 1 and forme.isupper() else "<MAJ>"]] + ids
        return ids

    def _tableau(self, suites: list[list[int]]):
        np = self._np
        longueurs = np.array([len(s) for s in suites], dtype=np.int64)
        tableau = np.zeros((len(suites), int(longueurs.max())), dtype=np.int64)
        for i, s in enumerate(suites):
            tableau[i, : len(s)] = s
        return tableau, longueurs

    def _phones(self, phone: str, forme: str) -> list[int]:
        ids = [self._p2i.get(x, self._pu) for x in _phonemes(phone)]
        if not ids and self.types_de_mots and forme and not any(c.isalnum() for c in forme):
            ids = [self._p2i.get(f"<P:{forme}>", self._p2i.get("<PONCT>", self._pu))]      # ponctuation
        return ids or [self._pu]

    def graphies_candidates(self, cle: str) -> list[str]:
        return [self._i2g[i] for i in self._candidats.get(cle.replace(".", "").replace("‿", ""), [])] if self.tete_graphie else []

    def _analyser(self, formes: list[str], phones: list[str], canal: str, types: list[str] | None = None,
                  cles: list[str] | None = None) -> list[Analyse]:
        return par_tranches(len(formes), lambda a, b: self._tranche(
            formes[a:b], phones[a:b], canal, types[a:b] if types else None, cles[a:b] if cles else None))

    def _tranche(self, formes: list[str], phones: list[str], canal: str, types: list[str] | None = None,
                 cles: list[str] | None = None) -> list[Analyse]:
        if not formes:
            return []
        np = self._np
        chars, lc = self._tableau([self._forme(f) for f in formes])
        ph, lp = self._tableau([self._phones(p, f) for p, f in zip(phones, formes)])
        flux = {"chars": chars, "longueurs_chars": lc, "phones": ph, "longueurs_phones": lp,
                "canal": np.array(_CANAUX[canal], dtype=np.float32)}
        if self._canal_par_mot:
            flux["canal"] = np.tile(flux["canal"], (len(formes), 1))
        if self.porte:
            flux["correction"] = np.array([self.correction], dtype=np.float32)
        if self.types_de_mots:
            m = self._types.get("m", 0)
            flux["types"] = np.array([self._types.get(t, m) for t in (types or ["m"] * len(formes))], dtype=np.int64)
        candidats: list[list[int]] = [[] for _ in formes]
        if self.tete_graphie:
            if cles:
                candidats = [self._candidats.get(c.replace(".", "").replace("‿", ""), []) if c else [] for c in cles]
            g = np.zeros((len(formes), max(1, max(len(c) for c in candidats))), dtype=np.int64)
            for i, c in enumerate(candidats):
                g[i, : len(c)] = c
            flux["graphies"] = g
        sorties = dict(zip(self._sorties, self._session.run(None, flux)))
        pos = sorties["pos"][0]
        e = np.exp(pos - pos.max(-1, keepdims=True))
        confiance = (e / e.sum(-1, keepdims=True)).max(-1)
        choix = {k: v[0].argmax(-1) for k, v in sorties.items()}
        t = sorties["tetes"][0]
        t = np.exp(t - t.max(-1, keepdims=True))
        confiance_tete = (t / t.sum(-1, keepdims=True)).max(-1)
        resultat = []
        for i, forme in enumerate(formes):
            upos = self._i2pos[int(choix["pos"][i])]
            traits = {}
            for f in self._valides.get(upos, ()):
                val = self._i2m[f].get(int(choix[f"trait_{f}"][i]), "_")
                if val not in ("_", "<PAD>"):
                    traits[f] = val
            classe = int(choix["lemme_classe"][i])
            if classe:
                lemme = self._classes.get(classe, "")
            else:
                lemme = _appliquer_motif(forme.lower(), self._motifs.get(int(choix["lemme_motif"][i]), ("", "")))
            amalgame = self._i2mwt.get(int(choix["mwt"][i]), "none")
            graphie = self._i2g[candidats[i][int(choix["graphie"][i])]] if len(candidats[i]) > 1 else ""
            resultat.append(Analyse(
                upos, traits, lemme.lower(), int(choix["tetes"][i]) - 1, self._i2dep[int(choix["deprel"][i])],
                float(confiance[i]), amalgame=("" if amalgame in ("none", "<PAD>") else amalgame).split(":")[0],
                confiance_tete=float(confiance_tete[i]), graphie=graphie, graphies=tuple(self._i2g[x] for x in candidats[i]) if graphie else (),
            ))
        return resultat
