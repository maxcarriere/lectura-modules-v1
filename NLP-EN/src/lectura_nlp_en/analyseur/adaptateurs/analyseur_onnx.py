# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Modèle de phrase anglais et tête de sélection exportés en ONNX, derrière l'interface ``Analyseur`` (``analyse.py``).

Inférence sans torch (onnxruntime et numpy) : ``analyseur.onnx`` et ``selection.onnx``, vocabulaires à côté.
``_Arbitrage`` porte toutes les décisions (candidats du lexique, contractions, mots lus d'une formule, choix entre la
tête et l'analyse libre) ; ``AnalyseurOnnx`` n'y ajoute que les deux passages des réseaux. Le décodeur de lemme n'est
pas exporté : en phonétique, un mot hors lexique prend son lemme par classe ou par motif (comme le français).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ..analyse import TRANCHE, Analyse, Entree, Jeton, par_tranches

MAX_CANDS = 40
MOIS = frozenset("January February March April May June July August September October November December".split())
MOTS_NOMBRE = frozenset(
    "zero oh one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion trillion".split())
_ORDINAUX = frozenset("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth twentieth "
                      "thirtieth fortieth fiftieth sixtieth seventieth eightieth ninetieth hundredth thousandth "
                      "millionth billionth".split())


def _rang_casse(ortho: str) -> int:
    """Casse ordinaire d'abord : minuscules, puis majuscule initiale, puis capitales."""
    return 0 if ortho == ortho.lower() else (1 if ortho[:1].isupper() and ortho[1:] == ortho[1:].lower() else 2)


def _ordinal(f: str) -> bool:
    return f in _ORDINAUX or f.endswith(("teenth",)) or (f.endswith("th") and f[:-2] in MOTS_NOMBRE)


def _encoder_forme(forme: str, c2i: dict) -> list[int]:
    """Caractères en minuscules, précédés d'une marque de casse (<MAJ>, <CAPS>) si le vocabulaire en a."""
    unk = c2i.get("<UNK>", 1)
    ids = [c2i.get(c, unk) for c in forme.lower()] or [unk]
    if "<MAJ>" in c2i and forme[:1].isupper():
        ids = [c2i["<CAPS>" if len(forme) > 1 and forme.isupper() else "<MAJ>"]] + ids
    return ids


def _ids_ponctuation(forme: str, p2i: dict, unk: int) -> list[int] | None:
    if not forme or any(c.isalnum() for c in forme):
        return None
    return [p2i.get(f"<P:{forme}>", p2i.get("<PONCT>", unk))]


def _appliquer_motif(forme: str, motif: tuple[str, str]) -> str:
    retirer, ajouter = motif
    if retirer:
        if not forme.endswith(retirer):
            return forme
        forme = forme[: -len(retirer)]
    return forme + ajouter


class _Vocabulaires:
    """Vocabulaires du modèle de phrase exporté (``analyseur_vocabs.json``)."""

    def __init__(self, d: dict):
        v = d["vocabs"]
        self.c2i = v["char2idx"]
        self.i2c = {i: c for c, i in self.c2i.items()}
        self.phone2idx = d["phone2idx"]
        self.pu = self.phone2idx.get("<UNK>", 1)
        self.i2pos = {i: p for p, i in v["pos2idx"].items()}
        self.i2m = {f: {i: x for x, i in voc.items()} for f, voc in v["morpho_vocabs"].items()}
        self.i2dep = {i: x for x, i in v["deprel2idx"].items()}
        self.i2mwt = {i: x for x, i in v["mwt_decomp2idx"].items()}
        self.classes = {int(k): x for k, x in v["lemme_classes"].items()}
        self.motifs = {int(k): tuple(x) for k, x in v["lemme_motifs"].items()}
        self.type2idx = v.get("type2idx") or {}
        self.graphies = v.get("graphies")
        self.tete_graphie = bool(self.graphies) and "graphie" in d["sorties"]
        if self.tete_graphie:
            self.i2g = {i: g for g, i in self.graphies["graphie2idx"].items()}
        self.phonemes = d["phonemes"]
        self.accents = tuple(d["accents"])

    def iter_phonemes(self, ipa: str) -> list[str]:
        """Découpage glouton en phonèmes : « . », « ‿ », espace ignorés."""
        res, i = [], 0
        while i < len(ipa):
            c = ipa[i]
            if c in ".‿ ":
                i += 1
                continue
            if c in self.accents:
                res.append(c)
                i += 1
                continue
            for p in self.phonemes:
                if ipa.startswith(p, i):
                    res.append(p)
                    i += len(p)
                    break
            else:
                res.append(c)
                i += 1
        return res

    def candidats_graphie(self, t: dict) -> list[str]:
        phone = t.get("phone")
        if not self.tete_graphie or not phone:
            return []
        cle = phone.replace(".", "").replace("‿", "").replace(" ", "").replace("ˈ", "").replace("ˌ", "")
        return [self.i2g[i] for i in self.graphies["candidats"].get(cle, [])]


class _Arbitrage:
    """Décisions de l'analyseur, communes à toute inférence : candidats du lexique, contractions, mots lus d'une
    formule, choix entre la tête de sélection et l'analyse libre. Les sous-classes fournissent ``_sorties_lot``
    (passage du modèle de phrase) et ``_noter`` (tête de sélection)."""

    # ── Interface ─────────────────────────────────────────────────────────────

    def analyser(self, jetons: list[Jeton]) -> list[list[Analyse]]:
        return par_tranches(len(jetons), lambda a, b: self._phrase(jetons[a:b], "ortho"))

    def analyser_phone(self, jetons: list[Jeton]) -> list[list[Analyse]]:
        return par_tranches(len(jetons), lambda a, b: self._phrase(jetons[a:b], "phone"))

    def analyser_lot(self, phrases: list[list[Jeton]], canal: str = "ortho", taille: int = 32) -> list[list[list[Analyse]]]:
        """Plusieurs phrases à la fois (un passage du modèle par paquet de ``taille`` phrases) : même résultat que
        ``analyser`` / ``analyser_phone`` phrase par phrase, plus vite. Une phrase de plus de 512 jetons passe seule."""
        resultats: list = [None] * len(phrases)
        courtes = [k for k, p in enumerate(phrases) if 0 < len(p) <= 2 * TRANCHE]
        for d in range(0, len(courtes), taille):
            paquet = courtes[d : d + taille]
            for k, r in zip(paquet, self._sorties_lot([phrases[k] for k in paquet], canal)):
                resultats[k] = self._phrase(phrases[k], canal, r)
        for k, p in enumerate(phrases):
            if resultats[k] is None:
                resultats[k] = (self.analyser if canal == "ortho" else self.analyser_phone)(p) if p else []
        return resultats

    # ── Modèle ────────────────────────────────────────────────────────────────

    def _sorties(self, jetons: list[Jeton], canal: str) -> dict:
        return self._sorties_lot([jetons], canal)[0]

    def _candidats(self, j: Jeton, canal: str) -> list[Entree]:
        if canal == "ortho":
            return self.lexique.lectures(j.forme)[:MAX_CANDS]
        cands = list(self.lexique.homophones(j.phone))
        for v in j.variantes:
            cands += [e for e in self.lexique.homophones(v) if e not in cands]
        # une seule graphie par analyse : la casse ordinaire (dog plutôt que DOG, même analyse) ; puis les graphies les
        # plus fréquentes d'abord, les Spéciaux après les Mots
        uniques: dict[tuple, Entree] = {}
        for e in sorted(cands, key=lambda e: (e.speciale, -e.frequence, _rang_casse(e.ortho))):
            uniques.setdefault((e.ortho.lower(), e.upos, e.lemme.lower(), tuple(sorted(e.feats.items()))), e)
        return list(uniques.values())[:MAX_CANDS]

    def _encoder(self, e: Entree) -> tuple:
        cle = (e.upos, e.lemme, tuple(sorted(e.feats.items())), e.ortho)
        if cle not in self._encodes:
            valides = self.valides.get(e.upos, ())
            tr = {f: v for f, v in e.feats.items() if f in valides and f in self.m2i and v in self.m2i[f]
                  and not (e.upos == "PROPN" and f in ("Gender", "Number"))}
            self._encodes[cle] = (
                self.pos2i.get(e.upos, 0),
                [self.m2i[f].get(tr.get(f, "_") if f in valides else "_", self.m2i[f].get("_", 0)) for f in self.feats],
                self.classe2i.get(e.lemme, self.classe2i.get(e.lemme.lower(), 0)),
                self.encoder_forme(e.ortho, self.tg.c2i)[:24],
            )
        return self._encodes[cle]

    # ── Analyse libre et choix ────────────────────────────────────────────────

    def _libre(self, j: Jeton, r: dict, i: int, canal: str) -> tuple[str, str, dict]:
        lp_pos = r["lp_pos"][i]
        ordre = lp_pos.argsort()[::-1]
        upos = self.tg.i2pos[int(ordre[0])]
        if upos == "MWT":
            upos = self.tg.i2pos[int(ordre[1])]
        traits = {}
        for k, f in enumerate(self.feats):
            if f in self.valides.get(upos, ()):
                val = self.tg.i2m[f].get(int(r["lp_m"][i][k].argmax()), "_")
                if val not in ("_", "<PAD>"):
                    traits[f] = val
        c = int(r["lp_c"][i].argmax())
        # une classe remplacée par « <RARE> » dans les vocabulaires livrés (données personnelles retirées) vaut repli
        if c != 0 and self.tg.classes.get(c) != "<RARE>":
            lemme = self.tg.classes.get(c, "")
        elif canal == "phone" and r["dec"] is not None:
            lemme = "".join(self.tg.i2c.get(int(x), "") for x in self.tg.jusqu_a_eos(r["dec"][i]))
        else:
            try:
                lemme = self.apply_pattern(j.forme.lower(), self.tg.motifs.get(int(r["motif"][i]), ("", "")))
            except Exception:
                lemme = j.forme.lower()
        return lemme, upos, traits

    def _commun(self, r: dict, i: int) -> dict:
        tete = r["tete"]
        return {"tete": (int(tete[i]) - 1) if tete is not None else None,
                "relation": self.tg.i2dep.get(int(r["relation"][i]), ""),
                "confiance": float(math.exp(float(r["lp_pos"][i].max())))}

    def _choisir(self, j: Jeton, r: dict, i: int, cands: list[Entree], scores: list[float] | None, canal: str) -> Analyse:
        commun = self._commun(r, i)
        graphies = tuple(r["cands_graphie"][i]) if r["cands_graphie"][i] else ()
        graphie_tete = ""
        if r["graphie"] is not None and len(graphies) > 1:
            graphie_tete = graphies[int(r["graphie"][i])]
        if not cands:
            lemme, upos, traits = self._libre(j, r, i, canal)
            return Analyse(upos, traits, lemme, graphie=graphie_tete, graphies=graphies, code="E", **commun)
        if scores is not None:
            x = max(range(len(scores)), key=lambda k: scores[k])
            if x > 0 and cands[x - 1].upos == "MWT":
                x = 0
        else:                                    # sans tête : UPOS de l'étalon parmi les candidats, puis fréquence
            lp = r["lp_pos"][i]
            x = 1 + max(range(len(cands)), key=lambda k: (lp[self.pos2i.get(cands[k].upos, 0)], cands[k].frequence))
        if x == 0:
            lemme, upos, traits = self._libre(j, r, i, canal)
            memes = [e for e in cands if e.upos == upos]
            memes = [e for e in memes if e.lemme.lower() == lemme.lower()] or memes
            if memes and canal == "ortho":
                # prononciation du lexique quand un candidat a le même UPOS (les traits en litige ne la changent pas) ;
                # lemme du candidat, jamais celui de l'étalon (classes de lemme inventées pour les noms rares)
                e = max(memes, key=lambda c: (scores[1 + cands.index(c)] if scores else 0.0))
                return Analyse(upos, traits, e.lemme, entree=e, graphie=graphie_tete, graphies=graphies, code="M", **commun)
            if upos == "PROPN" and j.forme[:1].isupper() and canal == "ortho":
                e = max(cands, key=lambda c: (c.upos in ("NOUN", "ADJ"), c.frequence))
                return Analyse(upos, traits, j.forme, entree=e, code="M", **commun)
            return Analyse(upos, traits, lemme, graphie=graphie_tete, graphies=graphies, code="E", **commun)
        e = cands[x - 1]
        if canal == "phone" and e.upos == "PROPN":
            # nom propre choisi alors que l'étalon voit un nom commun (« the Apple », « Bush's Dog ») : la graphie
            # ordinaire de même forme, si elle est candidate
            _l, libre, _t = self._libre(j, r, i, canal)
            autres = [k for k, c in enumerate(cands) if c.upos != "PROPN" and c.ortho.lower() == e.ortho.lower()]
            if libre != "PROPN" and autres:
                e = cands[max(autres, key=lambda k: scores[1 + k] if scores else 0.0)]
        valides = self.valides.get(e.upos, ())
        traits = {f: v for f, v in e.feats.items() if f in valides}
        return Analyse(e.upos, traits, e.lemme, entree=e, graphie=e.ortho if canal == "phone" else graphie_tete,
                       graphies=graphies, code="1" if len(cands) == 1 else "L", **commun)

    def _formule(self, mot: str) -> Analyse | None:
        """Mot lu d'une formule, étiqueté par convention (corpus `cadre_module`) : nombre NUM, ordinal ADJ, mois PROPN."""
        fl = mot.lower()
        if fl in MOTS_NOMBRE:
            upos, traits = "NUM", {"NumType": "Card"}
        elif _ordinal(fl):
            upos, traits = "ADJ", {"Degree": "Pos", "NumType": "Ord"}
        elif mot in MOIS:
            upos, traits = "PROPN", {"Number": "Sing"}
        else:
            return None
        cands = self.lexique.lectures(mot)
        e = next((c for c in cands if c.upos == upos), None) or (max(cands, key=lambda c: c.frequence) if cands else None)
        return Analyse(upos, traits, mot if upos == "PROPN" else fl, entree=e, code="F")

    def _contraction(self, j: Jeton, r: dict, i: int) -> list[Analyse]:
        """Contraction : classe de l'étalon parmi celles du clitique écrit, puis analyse du lexique de chaque mot."""
        commun = self._commun(r, i)
        clitique = "".join(j.mots[1:]).lower().replace("’", "'")
        idx = self.classes_mwt.get(clitique, [])
        mwt = r["mwt"][i]
        for k in sorted(idx, key=lambda q: -mwt[q]):
            upos_mots = self.tg.i2mwt[k].split(":", 1)[1].split(" + ")
            if len(upos_mots) != len(j.mots):
                continue
            analyses = []
            for m, u in zip(j.mots, upos_mots):
                cands = [c for c in self.lexique.lectures(m) if c.upos == u]
                if not cands and u == "PROPN" and m[:1].isupper() and self.lexique.lectures(m):
                    e = max(self.lexique.lectures(m), key=lambda c: c.frequence)
                    analyses.append(Analyse("PROPN", {"Number": "Sing"}, m, entree=e, code="C", **commun))
                    continue
                if not cands:
                    break
                e = max(cands, key=lambda c: (c.ortho == m, c.frequence))
                valides = self.valides.get(u, ())
                analyses.append(Analyse(u, {f: v for f, v in e.feats.items() if f in valides}, e.lemme, entree=e, code="C", **commun))
            else:
                return analyses
        # aucune classe ne convient : chaque mot seul, analyse la plus fréquente du lexique
        res = []
        for m in j.mots:
            cands = self.lexique.lectures(m)
            e = max(cands, key=lambda c: c.frequence) if cands else None
            res.append(Analyse(e.upos if e else "X", dict(e.feats) if e else {}, e.lemme if e else m, entree=e, code="C", **commun))
        return res

    def _phrase(self, jetons: list[Jeton], canal: str, r: dict | None = None) -> list[list[Analyse]]:
        if not jetons:
            return []
        r = r if r is not None else self._sorties(jetons, canal)
        a_noter, cands_par = [], {}
        for i, j in enumerate(jetons):
            if j.type == "p" or (canal == "ortho" and len(j.mots) > 1):
                continue
            if canal == "ortho" and j.type.startswith("f:") and self._formule(j.forme) is not None:
                continue
            cands = self._candidats(j, canal)
            cands_par[i] = cands
            if cands:
                a_noter.append((i, cands, j.forme))
        scores = self._noter(r, a_noter, canal)
        resultat = []
        for i, j in enumerate(jetons):
            if j.type == "p":
                resultat.append([Analyse("PUNCT", {}, j.forme, code="P", **self._commun(r, i))])
            elif canal == "ortho" and len(j.mots) > 1:
                resultat.append(self._contraction(j, r, i))
            elif canal == "ortho" and j.type.startswith("f:") and self._formule(j.forme) is not None:
                resultat.append([self._formule(j.forme)])
            else:
                resultat.append([self._choisir(j, r, i, cands_par.get(i, []), scores.get(i), canal)])
        return resultat



class AnalyseurOnnx(_Arbitrage):
    def __init__(self, lexique, dossier: str | Path, fils: int = 1):
        import numpy as np
        import onnxruntime as ort

        self.np = np
        dossier = Path(dossier)
        options = ort.SessionOptions()
        options.intra_op_num_threads = fils
        self._analyseur = ort.InferenceSession(str(dossier / "analyseur.onnx"), options, providers=["CPUExecutionProvider"])
        self._selection = (ort.InferenceSession(str(dossier / "selection.onnx"), options, providers=["CPUExecutionProvider"])
                           if (dossier / "selection.onnx").exists() else None)
        d = json.loads((dossier / "analyseur_vocabs.json").read_text(encoding="utf-8"))
        self._noms = d["sorties"]
        self._entrees = {e.name for e in self._analyseur.get_inputs()}
        self.tg = _Vocabulaires(d)
        v = d["vocabs"]
        self.valides = {u: set(t) for u, t in d["traits_par_upos"].items()}
        self.encoder_forme, self.ids_ponctuation = _encoder_forme, _ids_ponctuation
        self.iter_phonemes = self.tg.iter_phonemes
        self.apply_pattern = _appliquer_motif
        self.lexique = lexique
        self.pos2i = v["pos2idx"]
        self.feats = sorted(v["morpho_vocabs"])
        if self.feats != d["traits"]:
            raise ValueError("traits de l'analyseur exporté différents de ses vocabulaires")
        self.m2i = {f: v["morpho_vocabs"][f] for f in self.feats}
        self.classe2i = {x: i for i, x in self.tg.classes.items()}
        self.i_mwt = self.pos2i.get("MWT", -1)
        self.classes_mwt: dict[str, list[int]] = {}
        for cle, i in v["mwt_decomp2idx"].items():
            if cle.startswith("*") and ":" in cle:
                self.classes_mwt.setdefault(cle[1:].split(":", 1)[0].replace("’", "'"), []).append(i)
        self.tete = self._selection
        self._encodes: dict = {}

    # ── Réseaux ───────────────────────────────────────────────────────────────

    def _tableau(self, suites: list[list[int]]):
        np = self.np
        longueurs = np.array([len(s) for s in suites], dtype=np.int64)
        t = np.zeros((len(suites), max(1, int(longueurs.max()))), dtype=np.int64)
        for i, s in enumerate(suites):
            t[i, : len(s)] = s
        return t, longueurs

    def _log_softmax(self, x):
        np = self.np
        m = x.max(-1, keepdims=True)
        return x - m - np.log(np.exp(x - m).sum(-1, keepdims=True))

    def _sorties_lot(self, phrases: list[list[Jeton]], canal: str) -> list[dict]:
        return [self._une_phrase(p, canal) for p in phrases]

    def _une_phrase(self, jetons: list[Jeton], canal: str) -> dict:
        np, tg = self.np, self.tg
        chars, phones, types = [], [], []
        for j in jetons:
            forme = j.forme if canal == "ortho" or j.type == "p" else "x"
            chars.append(self.encoder_forme(forme, tg.c2i))
            ids = [tg.phone2idx.get(x, tg.pu) for x in self.iter_phonemes(j.phone)] if canal == "phone" and j.type != "p" else []
            phones.append(ids or self.ids_ponctuation(j.forme, tg.phone2idx, tg.pu) or [tg.pu])
            types.append(tg.type2idx.get(j.type, tg.type2idx.get("m", 0)))
        cands = ([tg.candidats_graphie({"phone": j.phone}) if j.type != "p" else [] for j in jetons]
                 if tg.tete_graphie and canal == "phone" else [[] for _ in jetons])
        c, lc = self._tableau(chars)
        p, lp = self._tableau(phones)
        flux = {"chars": c, "longueurs_chars": lc, "phones": p, "longueurs_phones": lp,
                "canal": np.array((1.0, 0.0) if canal == "ortho" else (0.0, 1.0), dtype=np.float32)}
        if "types" in self._entrees:
            flux["types"] = np.array(types, dtype=np.int64)
        if "graphies" in self._entrees:
            g2i = tg.graphies["graphie2idx"]
            g = np.zeros((len(jetons), max([len(x) for x in cands] + [1])), dtype=np.int64)
            for i, x in enumerate(cands):
                g[i, : len(x)] = [g2i[y] for y in x]
            flux["graphies"] = g
        o = dict(zip(self._noms, self._analyseur.run(None, flux)))
        n, n_vals = len(jetons), max(len(m) for m in self.m2i.values())
        lp_m = np.full((n, len(self.feats), n_vals), -30.0, dtype=np.float32)
        for k, f in enumerate(self.feats):
            l = self._log_softmax(o[f"trait_{f}"][0])
            lp_m[:, k, : l.shape[-1]] = l
        return {
            "repr": o["repr"][0], "lp_pos": self._log_softmax(o["pos"][0]), "lp_c": self._log_softmax(o["lemme_classe"][0]),
            "lp_m": lp_m, "motif": o["lemme_motif"][0].argmax(-1), "mwt": o["mwt"][0],
            "tete": o["tetes"][0].argmax(-1), "relation": o["deprel"][0].argmax(-1),
            "graphie": o["graphie"][0].argmax(-1) if "graphie" in o else None, "dec": None, "cands_graphie": cands,
        }

    def _noter(self, r: dict, mots: list[tuple[int, list[Entree], str]], canal: str) -> dict[int, list[float]]:
        if self._selection is None or not mots:
            return {}
        np = self.np
        upos, traits, classe, chars, za, casse, app = [], [], [], [], [], [], []
        for i, cands, forme in mots:
            for e in cands:
                u, t, c, ch = self._encoder(e)
                upos.append(u); traits.append(t); classe.append(c); chars.append(ch)
                za.append(e.frequence); casse.append(float(e.ortho == forme) if canal == "ortho" else 0.0); app.append(i)
        upos_a, traits_a, classe_a, app_a = (np.array(x, dtype=np.int64) for x in (upos, traits, classe, app))
        c, lg = self._tableau(chars)
        preuves = np.stack([r["lp_pos"][app_a, upos_a],
                            r["lp_m"][app_a[:, None], np.arange(traits_a.shape[1])[None, :], traits_a].sum(1),
                            r["lp_c"][app_a, classe_a]], -1).astype(np.float32)
        s, s_hors = self._selection.run(None, {
            "repr": r["repr"].astype(np.float32), "upos": upos_a, "traits": traits_a, "classe": classe_a, "chars": c,
            "longueurs": lg, "za": np.array(za, dtype=np.float32), "casse": np.array(casse, dtype=np.float32),
            "appartenance": app_a, "preuves": preuves})
        res, debut = {}, 0
        for i, cands, _ in mots:
            res[i] = [float(s_hors[i])] + [float(x) for x in s[debut : debut + len(cands)]]
            debut += len(cands)
        return res
