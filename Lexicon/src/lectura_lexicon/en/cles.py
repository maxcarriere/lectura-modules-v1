# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Clés de recherche communes à la construction des données et à l'API : clé phonétique, minuscules, suppressions
(index des voisins façon SymSpell), distance d'édition bornée. Inventaire anglais (``NLP_EN/Lexique/spec/02``) :
diphtongues et affriquées sont **un** phonème (eɪ aɪ ɔɪ aʊ oʊ tʃ dʒ) ; l'accent (ˈ ˌ) ne compte pas dans la clé."""

from __future__ import annotations

import unicodedata
import zlib
from itertools import combinations

_MARQUES = str.maketrans("", "", ".‿'- ˈˌ")     # syllabes, accent, séparateurs : la clé ne garde que les phonèmes
# Inventaire de `NLP_EN/Lexique/construction/phonemes_en.py`, plus long d'abord (découpage glouton).
PHONEMES = sorted(["ɑ", "æ", "ɔ", "aʊ", "aɪ", "ɛ", "eɪ", "ɪ", "i", "oʊ", "ɔɪ", "ʊ", "u", "ʌ", "ə", "ɝ", "ɚ",
                   "b", "tʃ", "d", "ð", "f", "ɡ", "h", "dʒ", "k", "l", "m", "n", "ŋ", "p", "ɹ", "s", "ʃ", "t", "θ",
                   "v", "w", "j", "z", "ʒ"], key=len, reverse=True)
VOYELLES = {"ɑ", "æ", "ɔ", "aʊ", "aɪ", "ɛ", "eɪ", "ɪ", "i", "oʊ", "ɔɪ", "ʊ", "u", "ʌ", "ə", "ɝ", "ɚ"}
# Timbres que l'accent seul distingue (ʌ / ə, ɝ / ɚ) et fusion cot-caught (ɑ / ɔ), répandue en américain.
_NEUTRES = {"ʌ": "ə", "ɝ": "ɚ", "ɔ": "ɑ"}


def cle_phone(phone: str) -> str:
    """Prononciation sans frontières de syllabe, accent ni séparateurs : clé des homophones."""
    return phone.translate(_MARQUES)


def phonemes(cle: str) -> list[str]:
    """Découpe une clé en phonèmes de l'inventaire (glouton) ; un symbole hors inventaire compte pour un phonème."""
    res: list[str] = []
    i = 0
    while i < len(cle):
        if res and unicodedata.combining(cle[i]):
            res[-1] += cle[i]
            i += 1
            continue
        for p in PHONEMES:
            if cle.startswith(p, i):
                res.append(p)
                i += len(p)
                break
        else:
            res.append(cle[i])
            i += 1
    return res


def inverse(cle: str) -> str:
    """Clé à l'envers, phonème par phonème, séparés par des espaces (« t ʃ » ≠ « tʃ ») et terminée par une espace :
    les rimes deviennent des préfixes exacts."""
    return " ".join(reversed(phonemes(cle))) + " "


def nombre_syllabes(phone: str) -> int:
    """Syllabes d'une prononciation syllabée du cadre (« ˈdɪk.ʃəˌnɛɹ.i » : 4) ; 0 si vide."""
    t = phone
    for s in "‿ ˈˌ":
        t = t.replace(s, ".")
    return len([s for s in t.split(".") if s])


def syllabes(phone: str) -> list[str]:
    """Syllabes d'une prononciation, l'accent gardé en tête de la syllabe qu'il ouvre (« ˈdɪk », « ʃə », « ˌnɛɹ »)."""
    res, cour = [], ""
    for c in phone:
        if c in ".‿ ":
            if cour:
                res.append(cour)
            cour = ""
        elif c in "ˈˌ":
            if cour:
                res.append(cour)
            cour = c
        else:
            cour += c
    if cour:
        res.append(cour)
    return res


def anagramme(forme: str) -> str:
    """Lettres triées, sans accents ni casse (« listen » et « silent » : eilnst)."""
    return "".join(sorted(c for c in sans_accents(minuscule(forme)) if c.isalpha()))


def neutraliser(cle: str) -> str:
    """Confond ʌ / ə, ɝ / ɚ (seul l'accent les sépare) et ɑ / ɔ (cot / caught)."""
    return "".join(_NEUTRES.get(p, p) for p in phonemes(cle))


def minuscule(forme: str) -> str:
    return forme.lower()


def sans_accents(forme: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", forme) if not unicodedata.combining(c))


def empreinte(texte: str) -> int:
    """Empreinte 32 bits signée d'une clé de l'index des voisins (crc32) ; les collisions sont vérifiées par la distance."""
    h = zlib.crc32(texte.encode("utf-8"))
    return h - (1 << 32) if h >= 1 << 31 else h


def suppressions(unites: str | list[str], n: int) -> set[str]:
    """Toutes les chaînes obtenues en supprimant de 0 à ``n`` unités (lettres, ou phonèmes si on passe une liste ;
    les phonèmes restants sont joints par « | » pour que « t ʃ » et « tʃ » restent distincts)."""
    liste = isinstance(unites, list)
    unites = list(unites)
    sep = "|" if liste else ""
    res = {sep.join(unites)}
    for k in range(1, min(n, len(unites) - 1) + 1):
        for idx in combinations(range(len(unites)), k):
            ecartes = set(idx)
            res.add(sep.join(u for i, u in enumerate(unites) if i not in ecartes))
    return res


def distance(a: str | list[str], b: str | list[str], borne: int = 2) -> int:
    """Distance d'édition avec transposition de deux unités voisines (OSA) ; ``borne + 1`` dès qu'elle la dépasse."""
    if abs(len(a) - len(b)) > borne:
        return borne + 1
    debut = 0                               # préfixe et suffixe communs retirés : la table ne couvre que l'écart
    while debut < len(a) and debut < len(b) and a[debut] == b[debut]:
        debut += 1
    fin = 0
    while fin < len(a) - debut and fin < len(b) - debut and a[-1 - fin] == b[-1 - fin]:
        fin += 1
    a, b = a[debut : len(a) - fin], b[debut : len(b) - fin]
    if not a or not b:
        return min(len(a) + len(b), borne + 1)
    if len(a) == len(b) and (len(a) == 1 or (len(a) == 2 and a[0] == b[1] and a[1] == b[0])):
        return min(1, borne + 1)            # une substitution, ou deux unités voisines inversées
    # Table limitée à la bande |i − j| ≤ borne : hors bande, la distance dépasse la borne.
    n, m, hors = len(a), len(b), borne + 1
    avant, prec = None, [j if j <= borne else hors for j in range(m + 1)]
    for i in range(1, n + 1):
        cour = [hors] * (m + 1)
        if i <= borne:
            cour[0] = i
        ai = a[i - 1]
        for j in range(max(1, i - borne), min(m, i + borne) + 1):
            v = prec[j - 1] + (ai != b[j - 1])
            if prec[j] + 1 < v:
                v = prec[j] + 1
            if cour[j - 1] + 1 < v:
                v = cour[j - 1] + 1
            if avant is not None and j > 1 and ai == b[j - 2] and a[i - 2] == b[j - 1] and avant[j - 2] + 1 < v:
                v = avant[j - 2] + 1
            cour[j] = v
        if min(cour) > borne:
            return hors
        avant, prec = prec, cour
    return min(prec[-1], hors)
