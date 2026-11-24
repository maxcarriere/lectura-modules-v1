# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Clés de recherche communes à la construction des données et à l'API : clé phonétique, minuscules, suppressions
(index des voisins façon SymSpell), distance d'édition bornée."""

from __future__ import annotations

import re
import unicodedata
import zlib
from functools import lru_cache
from itertools import combinations

_MARQUES = str.maketrans("", "", ".‿'- ")      # comme ``lectura_transducer.index_phone.cle_de``
_NEUTRES = {"ɛ": "e", "ɔ": "o", "œ": "ø"}


def cle_phone(phone: str) -> str:
    """Prononciation sans frontières de syllabe ni séparateurs : clé des homophones."""
    return phone.translate(_MARQUES)


def phonemes(cle: str) -> list[str]:
    """Découpe une clé en phonèmes : un caractère suivi de ses diacritiques combinants (ɑ̃)."""
    res: list[str] = []
    for c in cle:
        if res and unicodedata.combining(c):
            res[-1] += c
        else:
            res.append(c)
    return res


def inverse(cle: str) -> str:
    """Clé à l'envers, phonème par phonème (ɑ̃ garde son tilde après la voyelle) : les rimes deviennent des préfixes."""
    return "".join(reversed(phonemes(cle)))


def nombre_syllabes(phone: str) -> int:
    """Syllabes d'une prononciation syllabée du cadre (« ɛt.se.te.ʁa » : 4) ; 0 si vide."""
    return len([s for s in phone.replace("‿", ".").replace(" ", ".").split(".") if s])


VOYELLES = frozenset("a ɑ e ɛ i o ɔ u y ø œ ə ɑ̃ ɛ̃ ɔ̃ œ̃".split())   # semi-voyelles j, w, ɥ : consonnes


def syllabes_de(phone: str) -> list[str]:
    """Syllabes d'une prononciation syllabée du cadre (« ʃɑ̃.sɔ̃ » → ʃɑ̃, sɔ̃) ; non syllabée (clé de la taille mini),
    découpage approché : chaque syllabe commence à la consonne qui précède sa voyelle (« paʁdɔ̃ » → paʁ, dɔ̃)."""
    if re.search(r"[.‿ ]", phone):
        return [s for s in re.split(r"[.‿ ]", phone) if s]
    ph, res, debut = phonemes(phone), [], 0
    voyelles = [i for i, p in enumerate(ph) if p in VOYELLES]
    for v in voyelles[1:]:
        coupe = v - 1 if v - 1 > voyelles[0] and ph[v - 1] not in VOYELLES else v
        res.append("".join(ph[debut:coupe]))
        debut = coupe
    res.append("".join(ph[debut:]))
    return [s for s in res if s]


def rime_finale(ph: list[str]) -> list[str]:
    """Phonèmes depuis la dernière voyelle (« ʃɑ̃sɔ̃ » → ɔ̃, « tabl » → a b l) ; tout, s'il n'y a pas de voyelle."""
    for i in range(len(ph) - 1, -1, -1):
        if ph[i] in VOYELLES:
            return ph[i:]
    return ph


def commun_final(a: list[str], b: list[str]) -> int:
    """Nombre de phonèmes finaux communs à ``a`` et ``b``."""
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def qualite_rime(a: list[str], b: list[str]) -> str:
    """Qualité de la rime entre deux suites de phonèmes, au sens de la versification : « aucune » si la dernière
    voyelle et ce qui la suit diffèrent, sinon « pauvre » (un phonème commun : voyelle seule), « suffisante » (deux),
    « riche » (trois et plus)."""
    n = commun_final(a, b)
    if n < len(rime_finale(a)) or n < len(rime_finale(b)) or n == 0:
        return "aucune"
    return "pauvre" if n == 1 else "suffisante" if n == 2 else "riche"


@lru_cache(maxsize=500_000)
def fin_inverse(inverse: str) -> int:
    """Phonèmes de la rime finale (depuis la dernière voyelle) d'une clé donnée à l'envers : « ɔ̃sɑ̃ʃ » → 1."""
    n = 0
    for i, c in enumerate(inverse):
        if unicodedata.combining(c):
            continue
        n += 1
        p = c + "".join(x for x in inverse[i + 1 : i + 3] if unicodedata.combining(x))
        if p in VOYELLES:
            return n
    return n


def commun_inverse(a: str, b: str) -> int:
    """Phonèmes communs au début de deux clés à l'envers (= phonèmes finaux communs), sans découper en listes :
    préfixe commun en caractères, ramené à une frontière de phonème (« ɔ » ≠ « ɔ̃ »)."""
    k, m = 0, min(len(a), len(b))
    while k < m and a[k] == b[k]:
        k += 1
    if (k < len(a) and unicodedata.combining(a[k])) or (k < len(b) and unicodedata.combining(b[k])):
        while k > 0 and unicodedata.combining(a[k - 1]):
            k -= 1
        k = max(k - 1, 0)
    return sum(1 for c in a[:k] if not unicodedata.combining(c))


def qualite_commune(n: int, fin_a: int, fin_b: int) -> str:
    """Qualité d'une rime de ``n`` phonèmes finaux communs, rimes finales de ``fin_a`` et ``fin_b`` phonèmes."""
    if n == 0 or n < fin_a or n < fin_b:
        return "aucune"
    return "pauvre" if n == 1 else "suffisante" if n == 2 else "riche"


def anagramme(forme: str) -> str:
    """Lettres triées, sans accents ni casse (« Marie » et « aimer » : aeimr)."""
    return "".join(sorted(c for c in sans_accents(minuscule(forme)) if c.isalpha()))


def neutraliser(cle: str) -> str:
    """Confond les voyelles moyennes orales (e/ɛ, o/ɔ, ø/œ) ; les nasales restent."""
    return "".join(p if len(p) > 1 else _NEUTRES.get(p, p) for p in phonemes(cle))


def minuscule(forme: str) -> str:
    return forme.lower()


def sans_accents(forme: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", forme) if not unicodedata.combining(c))


def empreinte(texte: str) -> int:
    """Empreinte 32 bits signée d'une clé de l'index des voisins (crc32) ; les collisions sont vérifiées par la distance."""
    h = zlib.crc32(texte.encode("utf-8"))
    return h - (1 << 32) if h >= 1 << 31 else h


def suppressions(unites: str | list[str], n: int) -> set[str]:
    """Toutes les chaînes obtenues en supprimant de 0 à ``n`` unités (lettres, ou phonèmes si on passe une liste)."""
    unites = list(unites)
    base, taille = "".join(unites), len(unites)
    res = {base}
    # une ou deux unités : découpes de la chaîne aux positions des unités (chemin rapide, l'installation de la
    # mini en calcule des millions) ; au-delà, combinaisons
    pos = [0]
    for u in unites:
        pos.append(pos[-1] + len(u))
    if n >= 1 and taille >= 2:
        res.update(base[: pos[i]] + base[pos[i + 1] :] for i in range(taille))
    if n >= 2 and taille >= 3:
        res.update(base[: pos[i]] + base[pos[i + 1] : pos[j]] + base[pos[j + 1] :]
                   for i in range(taille) for j in range(i + 1, taille))
    for k in range(3, min(n, taille - 1) + 1):
        for idx in combinations(range(taille), k):
            ecartes = set(idx)
            res.add("".join(u for i, u in enumerate(unites) if i not in ecartes))
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
