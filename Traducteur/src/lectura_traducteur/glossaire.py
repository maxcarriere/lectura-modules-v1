# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Glossaire en contexte, dans les deux sens (en → fr, fr → en) : pour chaque mot d'un texte, sa traduction dans le
sens qu'il a ici.

1. Analyseur de la langue source (mode local, ses modèles ONNX) : lemme, catégorie, prononciation de chaque mot ;
2. traduction de chaque phrase (OPUS-MT, formules protégées) et découpage de la traduction par l'Analyseur de la langue cible ;
3. alignement mot à mot (mBERT) : les mots de la traduction qui rendent ce mot dans cette phrase (« ici ») ;
4. locutions (*give up*, *pomme de terre*) : suites de 2–3 mots présentes dans le glossaire, traitées comme un mot ;
5. glossaire (``glossaire.db`` du dossier des modèles) : sens candidats ; on retient le sens dont une traduction est un des
   mots alignés (« accord », score 2), sinon dont la glose contient un de ces mots (score 1), sinon le premier
   sens courant (« defaut »).
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field, replace

from . import analyseurs
from .modeles import ModelesAbsents, dossier_modeles
from .opus import MoteurOpus
PLEINS = {"NOUN", "VERB", "ADJ", "ADV", "PROPN", "NUM", "INTJ"}
FORMULE = re.compile(r"\d")  # chiffre dans la forme : formule lue par l'Analyseur (nombre, heure, date, monnaie…)
# sources par langue décrite, dans l'ordre de préférence (la première a des gloses dans la langue cible)
ORDRE_SOURCES = {"en": {"wikt_fr": 0, "wikt_en": 1, "wikilexik_inv": 2},
                 "fr": {"wikilexik": 0, "wikt_en_fr": 1}}


@dataclass
class Sens:
    glose: str
    traductions: list[str]
    precision: str
    registre: str
    source: str
    langue_glose: str = ""

    def libelle(self, langue_cible: str) -> str:
        """Ce qu'on affiche : la glose si elle est dans la langue du lecteur, sinon les traductions."""
        if self.langue_glose == langue_cible and self.glose:
            return self.glose
        return ", ".join(self.traductions[:4]) or self.glose


@dataclass
class Entree:
    forme: str
    debut: int
    fin: int
    lemme: str
    upos: str
    phone: str
    ici: str = ""                       # mots de la traduction qui le rendent dans cette phrase
    choix: str = ""                     # accord, glose, (…_cat : autre catégorie), defaut, aucun, outil, propre, nombre,
                                        # formule
    sens: Sens | None = None
    autres: list[Sens] = field(default_factory=list)


def _norm(m: str) -> str:
    return m.lower().strip(" .,;:!?«»\"'’").replace("’", "'")


def _mots_glose(glose: str) -> set[str]:
    return {m for m in re.findall(r"[\w'-]+", glose.lower().replace("’", "'")) if len(m) > 2}


class Glossaire:
    def __init__(self, source: str = "en", taille: str = "base", fils: int = 4, gpu: bool = False,
                 aligneur: str = "precis", models_dir=None, traducteur: MoteurOpus | None = None, aligneur_obj=None,
                 analyseur=None):
        self.source, self.cible = source, ("fr" if source == "en" else "en")
        base = dossier_modeles(models_dir) / "glossaire.db"
        if not base.exists():
            raise ModelesAbsents(f"{base} absent : glossaire non installé")
        self.module = analyseur or analyseurs.analyseur_local(source)      # jamais l'API : mode local
        self.traducteur = traducteur or MoteurOpus(source, self.cible, taille, gpu=gpu, fils=fils,
                                                   models_dir=models_dir)
        from .aligneur import Aligneur, AligneurMbert
        self.aligneur = aligneur_obj or (AligneurMbert(gpu=gpu, fils=fils, models_dir=models_dir)
                                         if aligneur == "precis" else Aligneur(source, self.cible, fils=fils,
                                                                               models_dir=models_dir))
        # lecture seule, partagée entre fils (un serveur appelle gloser depuis son pool de fils, un à la fois)
        self.base = sqlite3.connect(f"file:{base}?mode=ro", uri=True, check_same_thread=False)
        self.decouper_cible = analyseurs.decouper(self.cible)
        self.ordre = ORDRE_SOURCES[source]

    # --- glossaire ---
    def sens_de(self, lemme: str, upos: str | None = None) -> list[Sens]:
        req = ("select glose, traductions, precision, registre, source, rang, langue_glose from sens "
               "where langue=? and lemme=?" + (" and upos=?" if upos else ""))
        lignes = self.base.execute(req, (self.source, lemme, upos) if upos else (self.source, lemme)).fetchall()
        if not lignes and lemme != lemme.lower():
            return self.sens_de(lemme.lower(), upos)
        lignes.sort(key=lambda l: (bool(l[3]), self.ordre.get(l[4], 9), l[5]))
        return [Sens(g or "", [t for t in (tr or "").split("|") if t], p or "", r or "", s, lg or "")
                for g, tr, p, r, s, _, lg in lignes]

    def lemmes_cible(self, mots: list[str]) -> set[str]:
        """Formes et lemmes des mots alignés (et leur suite, pour les locutions)."""
        res = {_norm(m) for m in mots}
        if len(mots) > 1:
            res.add(_norm(" ".join(mots)))
        for m in mots:
            for (l,) in self.base.execute("select lemme from formes where langue=? and forme=?",
                                          (self.cible, _norm(m))):
                res.add(l.lower())
        return res - {""}

    @staticmethod
    def score(s: Sens, cibles: set[str]) -> int:
        if any(_norm(t) in cibles for t in s.traductions):
            return 2
        if s.glose and s.langue_glose and _mots_glose(s.glose) & cibles:
            return 1
        return 0

    def choisir(self, candidats: list[Sens], cibles: set[str]) -> tuple[Sens | None, int]:
        meilleur, sc = None, 0
        for s in candidats:  # déjà dans l'ordre de préférence : le premier au meilleur score gagne
            v = self.score(s, cibles)
            if v > sc:
                meilleur, sc = s, v
        return meilleur, sc

    def locution(self, mots: list[dict], i: int) -> tuple[int, str]:
        """(longueur 3 ou 2, clé) de la locution qui commence au mot i, (0, "") sinon. Clés essayées : formes, puis
        lemme du premier mot + formes des suivants (*gave up* → *give up*)."""
        for n in (3, 2):
            if i + n > len(mots):
                continue
            span = mots[i:i + n]
            if not any(m["analyse"]["upos"] in {"NOUN", "VERB", "ADJ", "ADV"} for m in span):
                continue
            if any(m["analyse"]["upos"] in {"PUNCT", "PROPN", "NUM"} for m in span):
                continue
            formes = [m["forme"].lower() for m in span]
            for tete in dict.fromkeys((formes[0], span[0]["analyse"]["lemme"].lower())):
                cle = tete
                for f in formes[1:]:
                    cle += ("" if cle.endswith(("'", "’")) else " ") + f
                if self.base.execute("select 1 from sens where langue=? and lemme=? and traductions != '' limit 1",
                                     (self.source, cle)).fetchone():
                    return n, cle
        return 0, ""

    # --- chaîne ---
    def gloser(self, texte: str) -> list[dict]:
        sorties = []
        for ph in self.module.lire(texte):
            mots = [m for m in ph["mots"] if m.get("analyse")]
            trad = self.traducteur.traduire_phrases([ph["ortho"]])[0]
            jetons = [j for p in self.decouper_cible(trad) for j in p]
            formes_c = [j.forme for j in jetons]
            liens = self.aligneur.aligner([([m["forme"] for m in mots], formes_c)])[0] if formes_c else set()
            entrees, i = [], 0
            while i < len(mots):
                m = mots[i]
                a = m["analyse"]
                n, cle = self.locution(mots, i) if a["upos"] != "PUNCT" else (0, "")
                if n:
                    span = mots[i:i + n]
                    e = Entree(" ".join(x["forme"] for x in span), m["debut"], span[-1]["fin"], cle, "LOC",
                               " ".join(x.get("phone_mot") or x.get("phone", "") for x in span))
                    idx = set(range(i, i + n))
                    candidats = self.sens_de(cle)
                else:
                    e = Entree(m["forme"], m["debut"], m["fin"], a["lemme"], a["upos"],
                               (m.get("phone_mot") or m.get("phone", "")).rstrip("‿"))
                    idx = {i}
                    candidats = self.sens_de(e.lemme, e.upos) if e.upos in PLEINS else []
                cibles_idx = sorted({j for (k, j) in liens if k in idx})
                e.ici = " ".join(formes_c[j] for j in cibles_idx)
                if not n and e.upos not in PLEINS:
                    e.choix = "outil"
                elif not n and FORMULE.search(e.forme):
                    # formule (5 p.m., $3.50, 2024) : traduite par les conventions de la langue cible (« ici »), pas de
                    # sens ; le lemme de l'Analyseur (five, three) ne vaut que pour la lecture
                    e.lemme, e.choix = e.forme, "formule"
                else:
                    cibles = self.lemmes_cible([formes_c[j] for j in cibles_idx])
                    e.sens, sc = self.choisir(candidats, cibles)
                    e.choix = {2: "accord", 1: "glose"}.get(sc, "")
                    if e.sens is None and cibles and not n:
                        # catégorie peut-être fausse (the fair ADJ) : autres catégories du même lemme
                        autres = [s for s in self.sens_de(e.lemme) if s not in candidats]
                        e.sens, sc = self.choisir(autres, cibles)
                        e.choix = {2: "accord_cat", 1: "glose_cat"}.get(sc, "")
                    if e.sens is None and candidats:
                        e.sens = next((s for s in candidats if s.traductions and not s.registre), candidats[0])
                        e.choix = "defaut"
                    elif e.sens is None:
                        # nom propre, nombre : rien à traduire, on montre seulement « ici »
                        e.choix = {"PROPN": "propre", "NUM": "nombre"}.get(e.upos, "aucun")
                    if sc == 1 and e.sens is not None:
                        # sens reconnu par sa glose seulement : ses traductions ne rendent pas cette phrase (smoking :
                        # « Fait de fumer le tabac » → tabac, alors que la phrase dit « fumer ») ; on garde la glose
                        e.sens = replace(e.sens, traductions=[])
                    e.autres = [s for s in candidats if s is not e.sens][:5]
                entrees.append(e)
                i += max(n, 1)
            sorties.append({"source": ph["ortho"], "traduction": trad, "mots": entrees})
        return sorties
