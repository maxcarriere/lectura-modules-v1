# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Composition des alignements : A₁ (texte ⇄ phonétique, alignement linéaire) ∘ A₂ (phonétique ⇄ voix, temps de
chaque phonème) → temps de chaque phonème, lettre et mot (millisecondes). Format commun des briques qui datent un
texte : lectura-aligner (alignement forcé), lectura-synthesizer (durées du modèle), métiers STT, TTS, STS.

    toutes = [colonnes(texte, p) for p in phrases]           # phrases : ``vers_dict()`` du transducer
    for i, j, r, p in phonemes_des_colonnes(toutes): …       # phonèmes réalisés, dans l'ordre du texte
    alignement = composer(texte, phrases, toutes, dates, duree)   # dates : {(i, j, r): Phoneme}
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field

def phonemes(chaine: str) -> list[str]:
    """« tʁwa.z » → t, ʁ, w, a, z (diacritiques rattachés, marques retirées)."""
    resultat: list[str] = []
    for c in chaine:
        if c in ".‿ ˈˌ":         # marques de syllabe, d'accent, de jonction
            continue
        if unicodedata.category(c).startswith("M") and resultat:
            resultat[-1] += c
        else:
            resultat.append(c)
    return resultat


@dataclass
class Phoneme:
    phoneme: str
    debut: int                     # millisecondes
    fin: int
    confiance: float
    realise: bool = True           # False : phonème facultatif (schwa) non entendu, durée nulle
    lettres: list[int] = field(default_factory=list)   # indices dans ``Phrase.lettres``


@dataclass
class Lettre:
    lettre: str
    position: int                  # dans le texte
    phone: str                     # colonne phonétique de l'alignement linéaire (_C, _M, phonèmes)
    debut: int
    fin: int
    coupure: str = "_"             # colonne coupure : SYL (début de syllabe dans le mot), APO, TIR, PONCT, FML…


@dataclass
class MotDate:
    forme: str
    position: int
    fin_texte: int
    debut: int
    fin: int
    phone: str


@dataclass
class PhraseDatee:
    ortho: str
    phone: str
    mots: list[MotDate]
    lettres: list[Lettre]
    phonemes: list[Phoneme]


@dataclass
class Alignement:
    texte: str
    duree: int
    phrases: list[PhraseDatee]
    score: float = 0.0             # aligneur : log-probabilité moyenne par trame du chemin retenu

    def vers_dict(self) -> dict:
        return asdict(self)

    @property
    def mots(self) -> list[MotDate]:
        return [m for p in self.phrases for m in p.mots]


def colonnes(texte: str, phrase: dict) -> list[dict]:
    """Colonnes de l'alignement linéaire situées dans le texte, avec leurs phonèmes réalisés."""
    colonnes, curseur = [], phrase["mots"][0]["debut"] if phrase.get("mots") else 0
    for ortho, phone, coupure in phrase["lineaire"]:
        position = -1
        if ortho not in ("_D", " "):
            position = texte.find(ortho, curseur)
            if position < 0:
                position = texte.find(ortho.replace("'", "’"), curseur)
            if position >= 0:
                curseur = position + len(ortho)
        dits = [] if phone in ("_C", "_M", " ", "‿", ".") or coupure == "PONCT" else phonemes(phone)
        colonnes.append({"ortho": ortho, "phone": phone, "coupure": coupure, "position": position, "phonemes": dits})
    return colonnes

def phonemes_des_colonnes(toutes: list[list[dict]]):
    """(phrase, colonne, rang, phonème) de chaque phonème réalisé, dans l'ordre du texte."""
    for i, cols in enumerate(toutes):
        for j, col in enumerate(cols):
            for r, p in enumerate(col["phonemes"]):
                yield i, j, r, p


def composer(texte: str, phrases: list[dict], toutes: list[list[dict]], dates: dict, duree: int,
             score: float = 0.0) -> Alignement:
    """Alignement daté. ``dates`` : {(phrase, colonne, rang): Phoneme} ; un phonème absent (schwa non dit, phonème
    que la voix n'a pas rendu) prend une durée nulle au début du phonème daté suivant (``realise=False``)."""
    prochain = duree
    for i, j, r, p in reversed(list(phonemes_des_colonnes(toutes))):
        if (i, j, r) in dates:
            prochain = dates[(i, j, r)].debut
        else:
            dates[(i, j, r)] = Phoneme(p, prochain, prochain, 0.0, realise=False)
    return Alignement(texte, duree, [_phrase(phrase, cols, i, dates) for i, (phrase, cols) in enumerate(zip(phrases, toutes))],
                      round(score, 4))


def _phrase(phrase: dict, colonnes: list[dict], i: int, dates: dict) -> PhraseDatee:
    lettres: list[Lettre] = []
    liste: list[Phoneme] = []
    index_lettre: dict[int, int] = {}
    for j, col in enumerate(colonnes):
        if col["ortho"] in (" ", "_D") or col["position"] < 0:
            continue
        index_lettre[j] = len(lettres)
        ps = [dates[(i, j, r)] for r in range(len(col["phonemes"])) if (i, j, r) in dates]
        debut = min((p.debut for p in ps), default=-1)
        fin = max((p.fin for p in ps), default=-1)
        lettres.append(Lettre(col["ortho"], col["position"], col["phone"], debut, fin, col["coupure"]))
        for p in ps:
            p.lettres = [len(lettres) - 1]
            liste.append(p)
    # Colonnes « _D » (phonème de plus) : rattachées à la lettre précédente.
    for j, col in enumerate(colonnes):
        if col["ortho"] == "_D":
            for r in range(len(col["phonemes"])):
                p = dates.get((i, j, r))
                if p:
                    # la dernière lettre qui a ses propres phonèmes (« M » de « M. » lu « monsieur »)
                    prec = max((index_lettre[x] for x in index_lettre if x < j and colonnes[x]["phonemes"]),
                               default=max((index_lettre[x] for x in index_lettre if x < j), default=0))
                    p.lettres = [prec]
                    liste.append(p)
                    if lettres:
                        lettres[prec].fin = max(lettres[prec].fin, p.fin)
    liste.sort(key=lambda p: (p.debut, p.fin))
    # Lettres sans phonème propre : suite d'un graphème (_C) → l'intervalle de sa tête ; muette (_M) → durée nulle
    # à la fin de la lettre précédente (au début de la suivante en tête de mot).
    for k, l in enumerate(lettres):
        if l.debut >= 0:
            continue
        prec = next((x for x in reversed(lettres[:k]) if x.debut >= 0), None)
        if l.phone == "_C" and prec:
            l.debut, l.fin = prec.debut, prec.fin
        elif prec and (k == 0 or lettres[k - 1].position == l.position - 1):
            l.debut = l.fin = prec.fin
        else:
            suiv = next((x for x in lettres[k + 1 :] if x.debut >= 0), None)
            l.debut = l.fin = suiv.debut if suiv else (prec.fin if prec else 0)
    mots = []
    for m in phrase["mots"]:
        dedans = [l for l in lettres if m["debut"] <= l.position < m["fin"]]
        dits = [l for l in dedans if l.fin > l.debut]
        if not dedans or m.get("origine") == "ponctuation":
            continue
        debut = min(l.debut for l in (dits or dedans))
        fin = max(l.fin for l in (dits or dedans))
        mots.append(MotDate(m["forme"], m["debut"], m["fin"], debut, fin, m.get("phone", "")))
    return PhraseDatee(phrase.get("ortho", ""), phrase.get("phone", ""), mots, lettres, liste)
