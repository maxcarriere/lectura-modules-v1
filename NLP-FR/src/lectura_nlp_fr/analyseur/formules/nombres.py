# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Nombres ↔ mots français, dans les deux sens.

Le sens direct écrit un entier en mots, chaque mot portant la plage de chiffres qu'il lit.
Le sens inverse n'a pas de grammaire propre : il calcule une valeur candidate puis
vérifie qu'elle se réécrit avec les mêmes mots. Une suite de mots est donc un nombre
si et seulement si le sens direct la produit.

Orthographe traditionnelle : trait d'union entre éléments inférieurs à cent, sauf autour
de « et » (``vingt et un``, ``quatre-vingt-dix-sept``, ``deux mille vingt-quatre``).
"""

from __future__ import annotations

from dataclasses import dataclass

_UNITES = (
    "zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize".split()
)
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}
_ECHELLES = {2: "million", 3: "milliard", 4: "billion"}
# Au-delà (plus de quinze chiffres), le nombre est lu chiffre à chiffre.
_MAX_CHIFFRES = 15

ET, ZERO, VIRGULE, MOINS = "et", "zéro", "virgule", "moins"

_VALEURS = {mot: v for v, mot in enumerate(_UNITES)}
_VALEURS.update({mot: 10 * d for d, mot in _DIZAINES.items()})
_VALEUR_ECHELLE = {"mille": 10**3, "million": 10**6, "milliard": 10**9, "billion": 10**12}
# Formes accordées ramenées à l'élément de base.
# « mil » : graphie de « mille » dans les dates (« mil neuf cent »).
_BASES = {"une": "un", "vingts": "vingt", "cents": "cent", "mil": "mille"}
_BASES.update({nom + "s": nom for nom in _ECHELLES.values()})
ELEMENTS = frozenset(_VALEURS) | frozenset(_VALEUR_ECHELLE) | frozenset(_BASES) | {"cent"}


@dataclass(frozen=True)
class Element:
    """Un élément de lecture (« vingt », « cinq », « mille ») et la plage de la source qu'il lit."""

    texte: str
    debut: int
    fin: int
    colle: bool = False      # relié au précédent par un trait d'union


@dataclass(frozen=True)
class MotLu:
    """Un mot de la lecture, la plage de la source qu'il lit et ses éléments.

    ``composant`` numérote les parties d'une formule composée (jour, mois, année) : la
    plage d'un composant est l'union de celles de ses mots (surlignage par bloc).
    """

    texte: str
    debut: int
    fin: int
    elements: tuple[Element, ...] = ()
    composant: int = 0
    # « lettre » : le mot est une lettre épelée, à prononcer par son nom (« H » → /aʃ/) et
    # non comme l'abréviation ou l'unité de même forme (« h » = heure).
    nature: str = ""

    def __post_init__(self) -> None:
        # Un mot sans décomposition est son propre élément.
        if not self.elements:
            object.__setattr__(self, "elements", (Element(self.texte, self.debut, self.fin),))


# ── Alignement ─────────────────────────────────────────────────────────────────
#
# Un mot ne s'aligne pas sur une formule comme sur un mot écrit : plusieurs éléments
# lisent le même chiffre, et un chiffre nul n'est lu par personne. Règles reprises du
# module Formules d'origine (span_num) :
#
# - dizaines et unités : le dernier élément lit le chiffre des unités (avec « et »), les
#   autres celui des dizaines (97 : quatre, vingt, dix → 9 ; sept → 7) ; un nombre rond
#   ou inférieur à dix-sept est lu d'un bloc (80, 16) ;
# - centaines : « deux » et « cent » lisent le chiffre des centaines, ou les trois
#   chiffres si la centaine est ronde (200) ;
# - échelle : « mille », « million » lisent le séparateur de milliers s'il est écrit
#   (12 000), sinon leur groupe ; dans un nombre rond de moins de cinq chiffres, le
#   groupe des milliers lit tout le nombre (2000) ;
# - les zéros intérieurs ne sont lus par aucun élément (1025 : vingt → 2, cinq → 5).


def _mots_0_99(n: int, feminin: bool, s_final: bool) -> list[str]:
    un = "une" if feminin else "un"
    if n == 1:
        return [un]
    if n < 17:
        return [_UNITES[n]]
    if n < 20:
        return ["dix-" + _UNITES[n - 10]]
    d, u = divmod(n, 10)
    if d in (7, 9):
        d, u = d - 1, u + 10
    if d == 8:
        if u == 0:
            return ["quatre-vingts" if s_final else "quatre-vingt"]
        return ["quatre-vingt-" + (un if u == 1 else _mots_0_99(u, False, False)[0])]
    dizaine = _DIZAINES[d]
    if u == 0:
        return [dizaine]
    if u == 1:
        return [dizaine, ET, un]
    if u == 11:
        return [dizaine, ET, "onze"]
    return [dizaine + "-" + _mots_0_99(u, False, False)[0]]


def _lire_groupe(g: int, positions: list[int], feminin: bool, s_final: bool) -> list[Element]:
    """Lit un groupe de un à trois chiffres ; ``positions`` donne la place de chaque chiffre."""
    fin = positions[-1] + 1
    c, r = divmod(g, 100)
    elems = []
    if c:
        plage = (positions[-3], positions[-3] + 1) if r else (positions[-3], fin)
        if c > 1:
            elems.append(Element(_UNITES[c], *plage))
        elems.append(Element("cents" if c > 1 and r == 0 and s_final else "cent", *plage))
    if r:
        bloc = (positions[-2] if r >= 10 else positions[-1], fin)
        dizaine, unite = (positions[-2], positions[-2] + 1) if r >= 10 else bloc, (positions[-1], fin)
        partage = r >= 17 and r % 10 != 0
        textes = [(e, k > 0) for mot in _mots_0_99(r, feminin, s_final) for k, e in enumerate(mot.split("-"))]
        for k, (texte, colle) in enumerate(textes):
            if not partage:
                plage = bloc
            elif k == len(textes) - 1 or texte == ET:
                plage = unite
            else:
                plage = dizaine
            elems.append(Element(texte, *plage, colle))
    return elems


def _assembler(elems: list[Element]) -> list[MotLu]:
    mots: list[MotLu] = []
    for e in elems:
        if e.colle and mots:
            m = mots[-1]
            mots[-1] = MotLu(m.texte + "-" + e.texte, min(m.debut, e.debut), max(m.fin, e.fin), m.elements + (e,))
        else:
            mots.append(MotLu(e.texte, e.debut, e.fin, (e,)))
    return mots


def lire_chiffres(chiffres: str, positions: list[int] | None = None, feminin: bool = False) -> list[MotLu]:
    """Lit une suite de chiffres comme un entier ; les zéros initiaux sont dits un à un."""
    if positions is None:
        positions = list(range(len(chiffres)))
    elems = []
    k = 0
    while k < len(chiffres) - 1 and chiffres[k] == "0":
        elems.append(Element(ZERO, positions[k], positions[k] + 1))
        k += 1
    chiffres, positions = chiffres[k:], positions[k:]
    if chiffres == "0":
        return _assembler(elems + [Element(ZERO, positions[0], positions[0] + 1)])
    if len(chiffres) > _MAX_CHIFFRES:
        return _assembler(elems + [Element(_UNITES[int(c)], p, p + 1) for c, p in zip(chiffres, positions)])
    rang = (len(chiffres) - 1) // 3
    tete = len(chiffres) - 3 * rang
    fin_du_nombre = positions[-1] + 1
    debut = 0
    for fin in range(tete, len(chiffres) + 1, 3):
        g, places = int(chiffres[debut:fin]), positions[debut:fin]
        if g and rang == 0:
            elems.extend(_lire_groupe(g, places, feminin, s_final=True))
        elif g:
            lus = _lire_groupe(g, places, False, s_final=rang > 1) if (g > 1 or rang > 1) else []
            if rang == 1 and len(chiffres) < 5 and int(chiffres[fin:]) == 0:
                # Millier rond : tout le groupe lit tout le nombre (2000).
                etendue = (places[0], fin_du_nombre)
                lus = [Element(e.texte, *etendue, e.colle) for e in lus]
            elif positions[fin] - places[-1] > 1:
                # Séparateur de milliers écrit ; « mille » seul lit aussi son chiffre (1 200).
                etendue = (places[-1] + 1 if lus else places[0], positions[fin])
            else:
                etendue = (places[0], places[-1] + 1)
            nom = "mille" if rang == 1 else _ECHELLES[rang] + ("s" if g > 1 else "")
            elems.extend(lus + [Element(nom, *etendue)])
        debut = fin
        rang -= 1
    return _assembler(elems)


def ecrire_entier(n: int, feminin: bool = False) -> list[str]:
    return [m.texte for m in lire_chiffres(str(n), feminin=feminin)]


# ── Sens inverse ───────────────────────────────────────────────────────────────


def elements(mots: list[str]) -> list[str]:
    """Décompose des mots en éléments de nombre : minuscules, traits d'union coupés."""
    return [e for mot in mots for e in mot.lower().split("-") if e]


def _base(element: str) -> str:
    return _BASES.get(element, element)


def _canonique(mots: list[str]) -> list[str]:
    return [_base(e) for e in elements(mots) if e != ET]


def _valeur_candidate(bases: list[str]) -> int | None:
    total = courant = 0
    for b in bases:
        if b in _VALEUR_ECHELLE:
            total += (courant or 1) * _VALEUR_ECHELLE[b]
            courant = 0
        elif b == "cent":
            courant = (courant or 1) * 100
        elif b == "vingt" and courant % 100 == 4:
            courant += 76
        elif b in _VALEURS:
            courant += _VALEURS[b]
        else:
            return None
    return total + courant


def entier_depuis_elements(elems: list[str]) -> int | None:
    """Valeur de la suite d'éléments si c'est exactement l'écriture d'un entier, sinon ``None``."""
    bases = [_base(e) for e in elems if e != ET]
    if not bases:
        return None
    n = _valeur_candidate(bases)
    if n is None or _canonique(ecrire_entier(n)) != bases:
        return None
    return n


def plus_long_entier(elems: list[str], i: int, maximum: int | None = None) -> tuple[int, int] | None:
    """Plus longue suite d'éléments à partir de ``i`` qui écrit un entier : (valeur, fin)."""
    centaines = _par_centaines(elems, i)
    if centaines is not None and (maximum is None or centaines[0] <= maximum):
        return centaines
    j = i
    while j < len(elems) and (elems[j] in ELEMENTS or _est_et(elems, j)):
        j += 1
    while j > i:
        if elems[j - 1] != ET:
            n = entier_depuis_elements(elems[i:j])
            if n is not None and (maximum is None or n <= maximum):
                return n, j
        j -= 1
    return None


def _par_centaines(elems: list[str], i: int) -> tuple[int, int] | None:
    """Nombre dit par centaines, surtout les années : « dix-neuf cent quatre-vingt-dix » = 1990 (11 à 19 suivi de
    « cent », puis un entier de 0 à 99 facultatif). Seulement de 11 à 19 : « deux cent » reste 200."""
    for k in (i + 2, i + 1):            # « dix-neuf » (deux éléments) ou « seize » (un élément)
        if k >= len(elems) or _base(elems[k]) != "cent":
            continue
        tete = entier_depuis_elements(elems[i:k])
        if tete is None or not 11 <= tete <= 19:
            continue
        valeur, fin = tete * 100, k + 1
        reste = plus_long_entier(elems, fin, maximum=99) if fin < len(elems) and _base(elems[fin]) != "cent" else None
        if reste is not None:
            valeur, fin = valeur + reste[0], reste[1]
        return valeur, fin
    return None


def _est_et(elems: list[str], j: int) -> bool:
    return (
        elems[j] == ET
        and 0 < j < len(elems) - 1
        and elems[j - 1] in _DIZAINES.values()
        and elems[j + 1] in ("un", "une", "onze")
    )
