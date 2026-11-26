# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Nombres ↔ mots anglais (américain), dans les deux sens.

Sens direct : un entier écrit en mots, chaque mot portant la plage de chiffres qu'il lit (alignement fin, mêmes règles
que le français). Un mot par élément, sans trait d'union (« twenty one », « two hundred five ») : chaque élément est
une entrée du lexique ; la graphie « twenty-one » est une affaire d'affichage. Pas de « and » britannique (« one
hundred five », usage américain dominant) ; le sens inverse l'accepte (« one hundred and five »).

Sens inverse : pas de grammaire propre. On calcule une valeur candidate puis on vérifie qu'elle se réécrit avec les
mêmes éléments : une suite de mots est un nombre si et seulement si le sens direct la produit.

Alignement (règles du français, ``span_num``) :
- dizaines et unités : « twenty » lit le chiffre des dizaines, « five » celui des unités ; un nombre de 10 à 19 ou
  une dizaine ronde est lu d'un bloc (ses deux chiffres) ;
- centaines : « two » et « hundred » lisent le chiffre des centaines, ou les trois chiffres si la centaine est ronde ;
- échelle : « thousand », « million » lisent le séparateur de milliers s'il est écrit (12,000), sinon leur groupe ;
  dans un millier rond de moins de cinq chiffres, tout le nombre (2000) ;
- les zéros intérieurs ne sont lus par aucun mot (1025 : twenty → 2, five → 5).
"""

from __future__ import annotations

from dataclasses import dataclass

UNITES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
          "seventeen eighteen nineteen").split()
DIZAINES = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"}
ECHELLES = ((10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (1000, "thousand"))
_NOM_ECHELLE = {3: "thousand", 6: "million", 9: "billion", 12: "trillion"}
_MAX_CHIFFRES = 15
ORDINAUX_IRREGULIERS = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth",
                        "nine": "ninth", "twelve": "twelfth"}

ET, ZERO, VIRGULE, MOINS, OH = "and", "zero", "point", "minus", "oh"

_VALEURS = {mot: v for v, mot in enumerate(UNITES)}
_VALEURS.update({mot: 10 * d for d, mot in DIZAINES.items()})
_VALEUR_ECHELLE = {nom: v for v, nom in ECHELLES}
_MULTIPLICATEURS = ("hundred",) + tuple(_VALEUR_ECHELLE)
ELEMENTS = frozenset(_VALEURS) | frozenset(_VALEUR_ECHELLE) | {"hundred"}


def ordinal_mot(mot: str) -> str:
    """Cardinal → ordinal d'un élément (« five » → fifth, « twenty » → twentieth)."""
    if mot in ORDINAUX_IRREGULIERS:
        return ORDINAUX_IRREGULIERS[mot]
    if mot.endswith("y"):
        return mot[:-1] + "ieth"
    return mot + "th"


_CARDINAL_DE = {ordinal_mot(m): m for m in ELEMENTS}
ORDINAUX = frozenset(_CARDINAL_DE)


@dataclass(frozen=True)
class Element:
    """Un élément de lecture (« twenty », « five ») et la plage de la source qu'il lit."""

    texte: str
    debut: int
    fin: int
    colle: bool = False      # relié au précédent par un trait d'union


@dataclass(frozen=True)
class MotLu:
    """Un mot de la lecture, la plage de la source qu'il lit et ses éléments ; ``composant`` numérote les parties
    d'une formule composée (mois, jour, année) ; ``nature`` « lettre » : lettre épelée."""

    texte: str
    debut: int
    fin: int
    elements: tuple[Element, ...] = ()
    composant: int = 0
    nature: str = ""

    def __post_init__(self) -> None:
        if not self.elements:
            object.__setattr__(self, "elements", (Element(self.texte, self.debut, self.fin),))


# ── Sens direct ────────────────────────────────────────────────────────────────


def _lire_groupe(g: int, p: list[int]) -> list[MotLu]:
    """Groupe de un à trois chiffres ; ``p`` donne la place de chaque chiffre."""
    fin = p[-1] + 1
    c, r = divmod(g, 100)
    mots = []
    if c:
        plage = (p[-3], p[-3] + 1) if r else (p[-3], fin)
        mots += [MotLu(UNITES[c], *plage), MotLu("hundred", *plage)]
    if r:
        if r < 10:
            mots.append(MotLu(UNITES[r], p[-1], fin))
        elif r < 20 or r % 10 == 0:
            mots.append(MotLu(UNITES[r] if r < 20 else DIZAINES[r // 10], p[-2], fin))
        else:
            mots += [MotLu(DIZAINES[r // 10], p[-2], p[-2] + 1), MotLu(UNITES[r % 10], p[-1], fin)]
    return mots


def lire_chiffres(chiffres: str, positions: list[int] | None = None, debut: int = 0, fin: int | None = None) -> list[MotLu]:
    """Lit une suite de chiffres comme un entier, aligné chiffre à chiffre ; zéros initiaux dits un à un, plus de
    quinze chiffres : chiffre à chiffre. ``positions`` : place de chaque chiffre (défaut : à partir de ``debut``)."""
    if not chiffres:
        return []
    if positions is None:
        positions = list(range(debut, debut + len(chiffres)))
    mots = []
    if len(chiffres) >= 5 and chiffres.startswith("0"):     # « 09819602175 » : un numéro, chiffre à chiffre
        return [MotLu(UNITES[int(c)], p, p + 1) for c, p in zip(chiffres, positions)]
    k = 0
    while k < len(chiffres) - 1 and chiffres[k] == "0":
        mots.append(MotLu(ZERO, positions[k], positions[k] + 1))
        k += 1
    chiffres, positions = chiffres[k:], positions[k:]
    if chiffres == "0":
        return mots + [MotLu(ZERO, positions[0], positions[0] + 1)]
    if len(chiffres) > _MAX_CHIFFRES:
        return mots + [MotLu(UNITES[int(c)], p, p + 1) for c, p in zip(chiffres, positions)]
    rang = (len(chiffres) - 1) // 3
    tete = len(chiffres) - 3 * rang
    fin_du_nombre = positions[-1] + 1
    d = 0
    for f in range(tete, len(chiffres) + 1, 3):
        g, places = int(chiffres[d:f]), positions[d:f]
        if g and rang == 0:
            mots.extend(_lire_groupe(g, places))
        elif g:
            lus = _lire_groupe(g, places)
            if rang == 1 and len(chiffres) < 5 and int(chiffres[f:]) == 0:
                etendue = (places[0], fin_du_nombre)            # millier rond : tout le nombre (2000)
                lus = [MotLu(m.texte, *etendue) for m in lus]
            elif positions[f] - places[-1] > 1:
                etendue = (places[-1] + 1, positions[f])        # séparateur écrit (12,000)
            else:
                etendue = (places[0], places[-1] + 1)
            mots.extend(lus + [MotLu(_NOM_ECHELLE[3 * rang], *etendue)])
        d = f
        rang -= 1
    return mots


def ecrire_entier(n: int) -> list[str]:
    """Mots d'un entier positif (« 1905 » → one thousand nine hundred five)."""
    return [m.texte for m in lire_chiffres(str(n))]


def ordinal(mots: list[str]) -> list[str]:
    """Dernier mot mis à l'ordinal (« twenty one » → twenty first)."""
    return mots[:-1] + [ordinal_mot(mots[-1])]


def lire_ordinal(chiffres: str, positions: list[int], fin_suffixe: int | None = None) -> list[MotLu]:
    """Ordinal aligné : le dernier mot prend la forme ordinale et lit aussi le suffixe (« 21st »)."""
    mots = lire_chiffres(chiffres, positions)
    dernier = mots[-1]
    mots[-1] = MotLu(ordinal_mot(dernier.texte), dernier.debut, fin_suffixe or dernier.fin)
    return mots


def pluriel(mot: str) -> str:
    return mot[:-1] + "ies" if mot.endswith("y") else mot + "s"


def annee(n: int) -> list[str]:
    """Lecture d'une année : 1905 nineteen oh five, 1900 nineteen hundred, 1066 ten sixty six, 2005 two thousand five,
    2024 twenty twenty four ; 1000, 2000–2009, et hors 1000–2099 : comme un nombre."""
    return [m.texte for m in lire_annee(str(n))]


def est_annee_par_paires(n: int) -> bool:
    return 1010 <= n <= 2099 and not 2000 <= n <= 2009


def lire_annee(chiffres: str, positions: list[int] | None = None) -> list[MotLu]:
    """Année lue par paires, alignée : « nineteen » lit 19, « oh » le zéro, « five » le 5, « hundred » les deux zéros."""
    if positions is None:
        positions = list(range(len(chiffres)))
    if len(chiffres) != 4 or not est_annee_par_paires(int(chiffres)):
        return lire_chiffres(chiffres, positions)
    return _paires4(chiffres, positions)


def _paires4(chiffres: str, positions: list[int]) -> list[MotLu]:
    tete = lire_chiffres(chiffres[:2], positions[:2])
    r = int(chiffres[2:])
    if r == 0:
        return tete + [MotLu("hundred", positions[2], positions[3] + 1)]
    if r < 10:
        return tete + [MotLu(OH, positions[2], positions[2] + 1), MotLu(UNITES[r], positions[3], positions[3] + 1)]
    return tete + lire_chiffres(chiffres[2:], positions[2:])


def lire_paires(chiffres: str, positions: list[int] | None = None) -> list[MotLu]:
    """Numéro dit par paires, à l'américaine (adresses, numéros de vol, de modèle) : 123 one twenty three, 1600
    sixteen hundred, 1905 nineteen oh five, 12345 twelve three forty five ; les milliers ronds restent des nombres."""
    if positions is None:
        positions = list(range(len(chiffres)))
    if len(chiffres) <= 2 or chiffres.startswith("0") or len(chiffres) > 5 or int(chiffres) % 1000 == 0:
        return lire_chiffres(chiffres, positions)
    if len(chiffres) == 3:
        if chiffres[1:] == "00":
            return lire_chiffres(chiffres, positions)
        tete = lire_chiffres(chiffres[0], positions[:1])
        if chiffres[1] == "0":
            return tete + [MotLu(OH, positions[1], positions[1] + 1)] + lire_chiffres(chiffres[2], positions[2:])
        return tete + lire_chiffres(chiffres[1:], positions[1:])
    if len(chiffres) == 4:
        return _paires4(chiffres, positions)
    return lire_paires(chiffres[:2], positions[:2]) + lire_paires(chiffres[2:], positions[2:])


# ── Sens inverse ───────────────────────────────────────────────────────────────


def elements(mots: list[str]) -> list[str]:
    """Éléments des mots : minuscules, traits d'union coupés (« Twenty-one » → twenty, one)."""
    return [e for m in mots for e in m.lower().split("-") if e]


def _valeur_candidate(elems: list[str]) -> int | None:
    total = courant = 0
    for e in elems:
        if e in _VALEUR_ECHELLE:
            total += (courant or 1) * _VALEUR_ECHELLE[e]
            courant = 0
        elif e == "hundred":
            courant = (courant or 1) * 100
        elif e in _VALEURS:
            courant += _VALEURS[e]
        else:
            return None
    return total + courant


def _sans_and(elems: list[str]) -> list[str] | None:
    """Ôte le « and » britannique (« one hundred and five ») ; None s'il est mal placé."""
    res = []
    for k, e in enumerate(elems):
        if e == ET:
            if not (0 < k < len(elems) - 1 and elems[k - 1] in _MULTIPLICATEURS
                    and elems[k + 1] in _VALEURS and elems[k + 1] != ZERO):
                return None
            continue
        res.append(e)
    return res


def entier_depuis_elements(elems: list[str]) -> int | None:
    """Valeur de la suite d'éléments si c'est exactement l'écriture d'un entier (« and » britannique et « a hundred »
    admis), sinon ``None``."""
    elems = list(elems)
    if len(elems) > 1 and elems[0] == "a" and elems[1] in _MULTIPLICATEURS:
        elems[0] = "one"
    bases = _sans_and(elems)
    if not bases:
        return None
    n = _valeur_candidate(bases)
    if n is None or ecrire_entier(n) != bases:
        return None
    return n


def plus_long_entier(elems: list[str], i: int, maximum: int | None = None) -> tuple[int, int] | None:
    """Plus longue suite d'éléments à partir de ``i`` qui écrit un entier : (valeur, fin)."""
    j = i
    if j + 1 < len(elems) and elems[j] == "a" and elems[j + 1] in _MULTIPLICATEURS:
        j += 1
    while j < len(elems) and (elems[j] in ELEMENTS or (elems[j] == ET and j > i)):
        j += 1
    while j > i:
        if elems[j - 1] not in (ET, "a"):
            n = entier_depuis_elements(elems[i:j])
            if n is not None and (maximum is None or n <= maximum):
                return n, j
        j -= 1
    return None


def plus_longue_annee(elems: list[str], i: int) -> tuple[int, int] | None:
    """Année dite par paires : « nineteen ninety » 1990, « nineteen oh five » 1905, « eighteen hundred » 1800,
    « ten sixty six » 1066, « twenty twenty four » 2024 (le sens direct doit la redonner)."""
    if i >= len(elems) or elems[i] not in UNITES[10:] + ["twenty"]:
        return None
    h = _VALEURS[elems[i]]
    j = i + 1
    if j >= len(elems):
        return None
    if elems[j] == "hundred":
        valeur, fin = h * 100, j + 1
    elif elems[j] == OH and j + 1 < len(elems) and elems[j + 1] in UNITES[1:10]:
        valeur, fin = h * 100 + UNITES.index(elems[j + 1]), j + 2
    else:
        reste = plus_long_entier(elems, j, maximum=99)
        if reste is None or reste[0] < 10:
            return None
        valeur, fin = h * 100 + reste[0], reste[1]
    if not est_annee_par_paires(valeur) or annee(valeur) != elems[i:fin]:
        return None
    return valeur, fin


def annee_dite(elems: list[str], i: int) -> tuple[int, int] | None:
    """Année dite de n'importe quelle façon que le sens direct produit : par paires (nineteen ninety) ou comme un
    nombre (two thousand six, one thousand)."""
    a = plus_longue_annee(elems, i)
    if a:
        return a
    n = plus_long_entier(elems, i, maximum=2099)
    if n and n[0] >= 1000 and annee(n[0]) == elems[i : n[1]]:
        return n
    return None


def paires_dites(elems: list[str], i: int) -> tuple[int, int] | None:
    """Numéro dit par paires (« four oh five » 405, « one twenty eight » 128, « sixteen hundred » 1600)."""
    tete = plus_long_entier(elems, i, maximum=99)
    if tete is None or tete[0] == 0 or tete[1] >= len(elems):
        return None
    h, j = tete
    if elems[j] == "hundred":
        n, fin = h * 100, j + 1
    elif elems[j] == OH and j + 1 < len(elems) and elems[j + 1] in UNITES[1:10]:
        n, fin = h * 100 + UNITES.index(elems[j + 1]), j + 2
    else:
        reste = plus_long_entier(elems, j, maximum=99)
        if reste is None or reste[0] < 10:
            return None
        n, fin = h * 100 + reste[0], reste[1]
    return (n, fin) if [m.texte for m in lire_paires(str(n))] == elems[i:fin] else None


def plus_long_ordinal(elems: list[str], i: int) -> tuple[int, int] | None:
    """Ordinal dit (« twenty first » 21, « one hundredth » 100) : (rang, fin)."""
    j = i
    while j < len(elems) and elems[j] in ELEMENTS:
        j += 1
    if j >= len(elems) or elems[j] not in ORDINAUX:
        return None
    n = entier_depuis_elements(elems[i:j] + [_CARDINAL_DE[elems[j]]])
    return (n, j + 1) if n is not None else None


def cardinal_de(ordinal_: str) -> str | None:
    return _CARDINAL_DE.get(ordinal_)
