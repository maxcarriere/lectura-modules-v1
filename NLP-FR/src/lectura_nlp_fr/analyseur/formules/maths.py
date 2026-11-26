# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Expressions mathématiques ↔ mots.

La valeur d'une expression est son arbre (somme, produit, puissance, appel de fonction…),
construit par le même analyseur dans les deux sens : depuis la forme écrite, ou depuis
les mots ramenés à leur forme écrite. La lecture suit l'ordre de l'écriture, un composant
par signe.

Garde-fous contre la prose : deux lettres ne se suivent jamais (``km``, ``Mme`` ne sont
pas des produits), et une expression doit contenir au moins une opération autre qu'une
soustraction de deux nombres (``1990-2000`` est une plage, pas une différence).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from .autres_types import LETTRE
from .briques import briques
from .nombres import MOINS, MotLu, elements
from .types import NOMBRE, Nombre, TypeFormule, _composant, _reconnaitre_nombre

# ── Arbre ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Num:
    nombre: Nombre


@dataclass(frozen=True)
class Var:
    nom: str


@dataclass(frozen=True)
class Bin:
    op: str                    # « + », « - », « × », « = »… ; « » pour un produit implicite (2x)
    gauche: object
    droite: object


@dataclass(frozen=True)
class Neg:
    operande: object


@dataclass(frozen=True)
class Puissance:
    base: object
    exposant: object


@dataclass(frozen=True)
class Indice:
    base: object
    indice: object


@dataclass(frozen=True)
class Racine:
    operande: object


@dataclass(frozen=True)
class Factorielle:
    operande: object


@dataclass(frozen=True)
class Appel:
    fonction: str
    argument: object


@dataclass(frozen=True)
class Groupe:
    contenu: object


# ── Signes ─────────────────────────────────────────────────────────────────────

NOMBRE_, VARIABLE, FONCTION, OPERATEUR = "nombre", "variable", "fonction", "operateur"

_RELATIONS = frozenset("=≠<>≤≥≈")
_ADDITIFS = frozenset("+-±")
_MULTIPLICATIFS = frozenset("×÷/")
_BINAIRES = _RELATIONS | _ADDITIFS | _MULTIPLICATIFS
# Écritures ramenées à un signe de référence.
_EQUIVALENTS = {"−": "-", "*": "×", "·": "×", "<=": "≤", ">=": "≥", "!=": "≠"}
# Lettres qui, suivies d'une parenthèse, nomment une fonction.
_LETTRES_FONCTIONS = frozenset("fgh")
_EXPOSANTS = {"²": "2", "³": "3"}
_NOMBRE_SIMPLE = re.compile(r"\d+(?:[,.]\d+)?")


@cache
def _table() -> dict[str, tuple[str, tuple[str, ...]]]:
    """Signe → (nature, mots de sa lecture)."""
    return {s: (b.categorie.split(":")[1], tuple(b.lecture.split())) for s, b in briques("maths").items()}


@dataclass(frozen=True)
class Jeton:
    nature: str
    texte: str                 # signe de référence
    debut: int
    fin: int
    espace_avant: bool = False


def _jetons(texte: str, position: int) -> list[Jeton]:
    table = _table()
    fonctions = sorted((s for s, (n, _l) in table.items() if n == FONCTION), key=len, reverse=True)
    jetons: list[Jeton] = []
    i = position
    espace = False
    while i < len(texte):
        c = texte[i]
        if c == " ":
            espace = True
            i += 1
            continue
        m = _NOMBRE_SIMPLE.match(texte, i)
        fonction = next((f for f in fonctions if texte.startswith(f + "(", i)), None)
        if m:
            jeton = Jeton(NOMBRE_, m.group(), i, m.end(), espace)
        elif fonction:
            jeton = Jeton(FONCTION, fonction, i, i + len(fonction), espace)
        elif texte[i : i + 2] in _EQUIVALENTS:
            jeton = Jeton(OPERATEUR, _EQUIVALENTS[texte[i : i + 2]], i, i + 2, espace)
        elif c in _EQUIVALENTS:
            jeton = Jeton(OPERATEUR, _EQUIVALENTS[c], i, i + 1, espace)
        elif c in table:
            jeton = Jeton(table[c][0], c, i, i + 1, espace)
        elif c.isascii() and c.isalpha():
            jeton = Jeton(VARIABLE, c, i, i + 1, espace)
        else:
            break
        jetons.append(jeton)
        espace = False
        i = jeton.fin
    return jetons


# ── Analyse ────────────────────────────────────────────────────────────────────


class _Echec(Exception):
    pass


# Rôles donnés à certaines parenthèses par l'analyse.
_DE, _DE_OUVRE, _MUETTE = "de", "de_ouvre", "muette"


class _Analyseur:
    def __init__(self, jetons: list[Jeton]):
        self.j = jetons
        self.roles: dict[int, str] = {}

    def _est(self, i: int, textes) -> bool:
        return i < len(self.j) and self.j[i].nature == OPERATEUR and self.j[i].texte in textes

    def _suite(self, i: int, operateurs, suivant):
        gauche, i = suivant(i)
        while self._est(i, operateurs):
            try:
                droite, k = suivant(i + 1)
            except _Echec:
                break
            gauche, i = Bin(self.j[i].texte, gauche, droite), k
        return gauche, i

    def relation(self, i: int):
        return self._suite(i, _RELATIONS, self.somme)

    def somme(self, i: int):
        return self._suite(i, _ADDITIFS, self.produit)

    def produit(self, i: int):
        gauche, i = self.unaire(i)
        while i < len(self.j):
            try:
                if self._est(i, _MULTIPLICATIFS):
                    droite, k = self.unaire(i + 1)
                    gauche, i = Bin(self.j[i].texte, gauche, droite), k
                elif self._implicite(i):
                    droite, k = self.postfixe(i)
                    gauche, i = Bin("", gauche, droite), k
                else:
                    break
            except _Echec:
                break
        return gauche, i

    def _implicite(self, i: int) -> bool:
        """Produit sans signe : ``2x``, ``2(x+1)``, ``2√3`` ; jamais deux lettres de suite."""
        jeton, avant = self.j[i], self.j[i - 1]
        if jeton.espace_avant:
            return False
        if jeton.nature in (VARIABLE, FONCTION):
            return avant.nature != VARIABLE
        return self._est(i, "(√")

    def unaire(self, i: int):
        if self._est(i, "-"):
            operande, i = self.unaire(i + 1)
            return Neg(operande), i
        return self.postfixe(i)

    def postfixe(self, i: int):
        base, i = self.atome(i)
        while i < len(self.j) and self.j[i].nature == OPERATEUR and not self.j[i].espace_avant:
            signe = self.j[i].texte
            if signe in _EXPOSANTS:
                base, i = Puissance(base, Num(Nombre(_EXPOSANTS[signe]))), i + 1
            elif signe == "^":
                exposant, i = self.unaire_simple(i + 1)
                base = Puissance(base, exposant)
            elif signe == "_":
                indice, i = self.atome(i + 1)
                base = Indice(base, indice)
            elif signe == "!":
                base, i = Factorielle(base), i + 1
            else:
                break
        return base, i

    def unaire_simple(self, i: int):
        if self._est(i, "-"):
            operande, i = self.atome(i + 1)
            return Neg(operande), i
        return self.atome(i)

    def atome(self, i: int):
        if i >= len(self.j):
            raise _Echec
        jeton = self.j[i]
        if jeton.nature == NOMBRE_:
            entier, _, decimales = jeton.texte.replace(".", ",").partition(",")
            return Num(Nombre(entier, decimales)), i + 1
        appel = jeton.nature == FONCTION or (jeton.nature == VARIABLE and jeton.texte in _LETTRES_FONCTIONS)
        if appel and self._est(i + 1, "(") and not self.j[i + 1].espace_avant:
            argument, k = self.relation(i + 2)
            if not self._est(k, ")"):
                raise _Echec
            atomique = isinstance(argument, (Num, Var))
            self.roles[i + 1] = _DE if atomique else _DE_OUVRE
            if atomique:
                self.roles[k] = _MUETTE
            return Appel(jeton.texte, argument), k + 1
        if jeton.nature == VARIABLE:
            return Var(jeton.texte), i + 1
        if self._est(i, "("):
            contenu, k = self.relation(i + 1)
            if not self._est(k, ")"):
                raise _Echec
            return Groupe(contenu), k + 1
        if self._est(i, "√"):
            operande, k = self.postfixe(i + 1)
            return Racine(operande), k
        raise _Echec


def _est_une_expression(arbre) -> bool:
    """Au moins une opération, et pas une simple différence de deux nombres."""
    if isinstance(arbre, Bin):
        if arbre.op == "-" and isinstance(arbre.gauche, Num) and isinstance(arbre.droite, Num):
            return False
        return bool(arbre.op) or _est_une_expression(arbre.gauche) or _est_une_expression(arbre.droite)
    if isinstance(arbre, (Neg, Factorielle, Groupe)):
        fils = arbre.operande if not isinstance(arbre, Groupe) else arbre.contenu
        return _est_une_expression(fils)
    return isinstance(arbre, (Puissance, Indice, Racine, Appel))


@dataclass(frozen=True)
class _Analyse:
    """Résultat d'analyse, avec l'interface d'un résultat de motif (``start``, ``end``)."""

    arbre: object
    jetons: tuple[Jeton, ...]
    roles: tuple[tuple[int, str], ...]

    def start(self) -> int:
        return self.jetons[0].debut

    def end(self) -> int:
        return self.jetons[-1].fin


class _Motif:
    def match(self, texte: str, position: int = 0) -> _Analyse | None:
        jetons = _jetons(texte, position)
        if not jetons:
            return None
        analyseur = _Analyseur(jetons)
        try:
            arbre, n = analyseur.relation(0)
        except _Echec:
            return None
        fin = jetons[n - 1].fin
        if not _est_une_expression(arbre) or (fin < len(texte) and (texte[fin].isalnum() or texte[fin] == "_")):
            return None
        return _Analyse(arbre, tuple(jetons[:n]), tuple((k, r) for k, r in analyseur.roles.items() if k < n))


# ── Lecture ────────────────────────────────────────────────────────────────────


def _lire(a: _Analyse, texte: str | None = None) -> list[MotLu]:
    table = _table()
    roles = dict(a.roles)
    mots: list[MotLu] = []
    for k, jeton in enumerate(a.jetons):
        plage = (jeton.debut, jeton.fin)
        if jeton.nature == NOMBRE_:
            source = " " * jeton.debut + jeton.texte
            mots.extend(_composant(NOMBRE.lire(NOMBRE.motif.match(source, jeton.debut)), k))
            continue
        role = roles.get(k)
        if role == _MUETTE:
            continue
        if role == _DE:
            lecture = ("de",)
        elif role == _DE_OUVRE:
            lecture = ("de",) + table["("][1]
        elif jeton.nature == VARIABLE and jeton.texte not in table:
            mots.append(MotLu(jeton.texte, *plage, composant=k, nature=LETTRE))
            continue
        else:
            lecture = table[jeton.texte][1]
        mots.extend(MotLu(mot, *plage, composant=k) for mot in lecture)
    return mots


# ── Écriture ───────────────────────────────────────────────────────────────────


def ecrire_expression(arbre) -> str:
    e = ecrire_expression
    if isinstance(arbre, Num):
        return arbre.nombre.entier + ("," + arbre.nombre.decimales if arbre.nombre.decimales else "")
    if isinstance(arbre, Var):
        return arbre.nom
    if isinstance(arbre, Bin):
        return e(arbre.gauche) + arbre.op + e(arbre.droite)
    if isinstance(arbre, Neg):
        return "-" + e(arbre.operande)
    if isinstance(arbre, Puissance):
        exposant = e(arbre.exposant)
        signe = next((s for s, n in _EXPOSANTS.items() if n == exposant), None)
        return e(arbre.base) + (signe or "^" + exposant)
    if isinstance(arbre, Indice):
        return e(arbre.base) + "_" + e(arbre.indice)
    if isinstance(arbre, Racine):
        return "√" + e(arbre.operande)
    if isinstance(arbre, Factorielle):
        return e(arbre.operande) + "!"
    if isinstance(arbre, Appel):
        return arbre.fonction + "(" + e(arbre.argument) + ")"
    return "(" + e(arbre.contenu) + ")"


# ── Reconnaissance ─────────────────────────────────────────────────────────────

# Lettres admises comme variables dans le sens mots → formule : celles qui ne sont pas
# aussi des mots courants (« a », « y », « l »…).
_VARIABLES_DITES = frozenset("xyznkt") | _LETTRES_FONCTIONS


@cache
def _signes_des_mots() -> list[tuple[tuple[str, ...], str, str]]:
    """Lectures (suites de mots) → signe et nature, les plus longues d'abord."""
    lectures: dict[tuple[str, ...], tuple[str, str]] = {}
    for signe, (nature, lecture) in _table().items():
        cle = tuple(elements(list(lecture)))
        # Plusieurs signes pour une lecture (minuscule et majuscule grecques, × et *) :
        # la minuscule et le signe de référence l'emportent.
        if signe in _EQUIVALENTS or (cle in lectures and not signe.islower()):
            continue
        lectures[cle] = (signe, nature)
    lectures[("égal",)] = ("=", OPERATEUR)
    return sorted(((c, s, n) for c, (s, n) in lectures.items()), key=lambda x: len(x[0]), reverse=True)


def _reconnaitre(elems: list[str], i: int) -> tuple[object, int] | None:
    pieces: list[tuple[str, int]] = []      # écriture cumulée, position atteinte dans les mots
    ecrit = ""
    j = i
    appel = False          # la pièce précédente nomme une fonction
    fermer = False         # parenthèse d'un appel à argument simple, à refermer après l'atome
    while j < len(elems):
        atome = False
        nombre = _reconnaitre_nombre(elems, j) if elems[j] != MOINS else None
        signe = next(((c, s, n) for c, s, n in _signes_des_mots() if tuple(elems[j : j + len(c)]) == c), None)
        if nombre:
            v, j = nombre
            ecrit += v.entier + ("," + v.decimales if v.decimales else "")
            atome, appel = True, False
        elif elems[j] == "de" and appel:
            ouvrante = tuple(elements(list(_table()["("][1])))
            if tuple(elems[j + 1 : j + 1 + len(ouvrante)]) == ouvrante:
                j += len(ouvrante)
            else:
                fermer = True
            ecrit += "("
            j += 1
            appel = False
        elif signe:
            cle, texte, nature = signe
            ecrit += texte
            j += len(cle)
            atome, appel = nature == VARIABLE, nature == FONCTION
        elif elems[j] in _VARIABLES_DITES:
            ecrit += elems[j]
            appel = elems[j] in _LETTRES_FONCTIONS
            j += 1
            atome = True
        else:
            break
        if atome and fermer:
            ecrit += ")"
            fermer = False
        pieces.append((ecrit, j))
    for ecrit, fin in reversed(pieces):
        a = MATHS.motif.match(ecrit)
        # L'écriture obtenue doit se relire avec exactement les mots reçus.
        if a and a.end() == len(ecrit) and _relu(a) == [_reference(e) for e in elems[i:fin]]:
            return a.arbre, fin
    return None


def _relu(a: _Analyse) -> list[str]:
    return [_reference(e) for e in elements([m.texte for m in _lire(a)])]


def _reference(element: str) -> str:
    return "égal" if element == "égale" else element


MATHS = TypeFormule(
    "maths",
    _Motif(),
    lambda a: a.arbre,
    _lire,
    _reconnaitre,
    ecrire_expression,
)


def debute_une_expression(mot, suivant) -> bool:
    """Un mot du document peut-il ouvrir une expression qui ne commence pas par un chiffre ?"""
    table = _table()
    if mot.forme == "(":
        return True
    if suivant is None or suivant.espace_avant and suivant.forme[:1] not in _BINAIRES:
        return False
    nom = mot.forme in table and table[mot.forme][0] in (VARIABLE, FONCTION)
    lettre = len(mot.forme) == 1 and mot.forme.isalpha()
    return (nom or lettre) and (suivant.forme[:1] in _BINAIRES or suivant.forme[:1] in "(^_²³!")


# ── Notation scientifique ──────────────────────────────────────────────────────
# « 1,5e10 » est une autre écriture de « 1,5×10^10 » : même arbre, même lecture.

_SCIENTIFIQUE = re.compile(r"(?P<mantisse>\d+(?:[,.]\d+)?)(?P<e>[eE])(?P<exposant>[-\u2212+]?\d+)(?![\w])")


def _construire_scientifique(m: re.Match[str]):
    return MATHS.motif.match(_en_maths(m)).arbre


def _en_maths(m: re.Match[str]) -> str:
    return f"{m.group('mantisse')}×10^{m.group('exposant').lstrip('+').replace(chr(0x2212), '-')}"


def _lire_scientifique(m: re.Match[str]) -> list[MotLu]:
    """Lecture de l'écriture développée, replacée sur la source : mantisse, « e », exposant."""
    plages = [(m.start("mantisse"), m.end("mantisse")), (m.start("e"), m.end("e")), (m.start("exposant"), m.end("exposant"))]
    mots = []
    for mot in _lire(MATHS.motif.match(_en_maths(m))):
        # Jetons de l'écriture développée : mantisse, ×, 10, ^, puis l'exposant.
        partie = 0 if mot.composant == 0 else 1 if mot.composant <= 3 else 2
        debut, fin = plages[partie]
        if partie == 0:
            mots.append(mot)        # la mantisse garde son alignement au chiffre
        else:
            mots.append(MotLu(mot.texte, debut, fin, composant=partie))
    return mots


SCIENTIFIQUE = TypeFormule(
    "scientifique",
    _SCIENTIFIQUE,
    _construire_scientifique,
    _lire_scientifique,
    lambda elems, i: None,
    ecrire_expression,
)
