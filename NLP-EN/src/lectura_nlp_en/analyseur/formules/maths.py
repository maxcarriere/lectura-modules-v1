# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Expressions mathématiques ↔ mots anglais (analyseur du français, lectures américaines usuelles).

La valeur d'une expression est son arbre (somme, produit, puissance, appel de fonction…), construit par le même
analyseur dans les deux sens : depuis la forme écrite, ou depuis les mots ramenés à leur forme écrite (le sens
inverse vérifie que l'écriture obtenue se relit avec exactement les mêmes mots). La lecture suit l'ordre de
l'écriture, un composant par signe.

Lectures : x + 1 = 3 « x plus one equals three » ; 2x² « two x squared » ; x^4 « x to the fourth » ; 10^-3 « ten to
the minus three » ; x^n « x to the n » ; x^(n+1) « x to the power of open parenthesis n plus one close parenthesis » ;
f(x) « f of x » ; sin(x) « sine of x » ; √2 « the square root of two » ; x_1 « x sub one » ; a ≤ b « a is less than
or equal to b » ; 3! « three factorial » (avec une autre opération) ; 2x4 « two by four » ; 1.5e-3 « one point five
times ten to the minus three ».

Garde-fous contre la prose : deux lettres ne se suivent jamais (``km``, ``Mr`` ne sont pas des produits) ; une
expression doit contenir au moins une opération qui ne soit pas un trait d'union collé (``F-16``, ``I-5``, ``3-D``,
``1990-2000``, ``978-3-16`` ne sont pas des différences) ni une barre entre lettres seules (``w/o``, ``I/O``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

from .autres_types import LETTRE
from .nombres import MotLu, elements, lire_ordinal, plus_long_ordinal, ordinal_mot, ecrire_entier
from .types import NOMBRE, Nombre, TypeFormule, _composant, lire_nombre_aligne, reconnaitre_nombre

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
_ADDITIFS = frozenset("+-±∓")
_MULTIPLICATIFS = frozenset("×÷/x")
_BINAIRES = _RELATIONS | _ADDITIFS | (_MULTIPLICATIFS - {"x"})
_EQUIVALENTS = {"−": "-", "*": "×", "·": "×", "⋅": "×", "<=": "≤", ">=": "≥", "!=": "≠", "–": "-"}
_LETTRES_FONCTIONS = frozenset("fgh")
_EXPOSANTS = {"²": "2", "³": "3"}
_NOMBRE_SIMPLE = re.compile(r"\d+(?:\.\d+)?")

_GRECQUES = dict(zip("αβγδεζηθικλμνξοπρστυφχψω",
                     "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma "
                     "sigma tau upsilon phi chi psi omega".split()))
_GRECQUES.pop("ς", None)
_GRECQUES.update({c.upper(): n for c, n in list(_GRECQUES.items()) if c != "ς"})
_GRECQUES["ς"] = "sigma"

# signe → (nature, lecture)
_SIGNES = {
    "+": (OPERATEUR, "plus"), "-": (OPERATEUR, "minus"), "×": (OPERATEUR, "times"), "x": (OPERATEUR, "by"),
    "÷": (OPERATEUR, "divided by"), "/": (OPERATEUR, "over"), "=": (OPERATEUR, "equals"),
    "≠": (OPERATEUR, "does not equal"), "<": (OPERATEUR, "is less than"), ">": (OPERATEUR, "is greater than"),
    "≤": (OPERATEUR, "is less than or equal to"), "≥": (OPERATEUR, "is greater than or equal to"),
    "≈": (OPERATEUR, "is approximately equal to"), "±": (OPERATEUR, "plus or minus"), "∓": (OPERATEUR, "minus or plus"),
    "√": (OPERATEUR, "the square root of"), "!": (OPERATEUR, "factorial"), "(": (OPERATEUR, "open parenthesis"),
    ")": (OPERATEUR, "close parenthesis"), "^": (OPERATEUR, "to the power of"), "_": (OPERATEUR, "sub"),
    "²": (OPERATEUR, "squared"), "³": (OPERATEUR, "cubed"), "∞": (VARIABLE, "infinity"),
    "sin": (FONCTION, "sine"), "cos": (FONCTION, "cosine"), "tan": (FONCTION, "tangent"), "log": (FONCTION, "log"),
    "ln": (FONCTION, "natural log"), "exp": (FONCTION, "exponential"), "sqrt": (FONCTION, "square root"),
    "arcsin": (FONCTION, "arc sine"), "arccos": (FONCTION, "arc cosine"), "arctan": (FONCTION, "arc tangent"),
    **{c: (VARIABLE, n) for c, n in _GRECQUES.items()},
}


def _table() -> dict[str, tuple[str, tuple[str, ...]]]:
    return {s: (n, tuple(lecture.split())) for s, (n, lecture) in _SIGNES.items()}


@dataclass(frozen=True)
class Jeton:
    nature: str
    texte: str                 # signe de référence
    debut: int
    fin: int
    espace_avant: bool = False


_FONCTIONS = sorted((s for s, (n, _l) in _SIGNES.items() if n == FONCTION), key=len, reverse=True)


def _jetons(texte: str, position: int) -> list[Jeton]:
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
        fonction = next((f for f in _FONCTIONS if texte.startswith(f + "(", i)), None)
        if m:
            jeton = Jeton(NOMBRE_, m.group(), i, m.end(), espace)
        elif fonction:
            jeton = Jeton(FONCTION, fonction, i, i + len(fonction), espace)
        elif c == "x" and jetons and jetons[-1].nature == NOMBRE_ and re.match(r"x(?P<e> ?)\d", texte[i:]) \
                and bool(re.match(r"x \d", texte[i:])) == espace:
            jeton = Jeton(OPERATEUR, "x", i, i + 1, espace)          # 2x4 : dimension
        elif texte[i : i + 2] in _EQUIVALENTS:
            jeton = Jeton(OPERATEUR, _EQUIVALENTS[texte[i : i + 2]], i, i + 2, espace)
        elif c in _EQUIVALENTS:
            jeton = Jeton(OPERATEUR, _EQUIVALENTS[c], i, i + 1, espace)
        elif c in _SIGNES and c != "x":
            jeton = Jeton(_SIGNES[c][0], c, i, i + 1, espace)
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


# Rôles donnés à certains jetons par l'analyse.
_DE, _DE_OUVRE, _MUETTE = "of", "of_ouvre", "muette"
_A_LA, _ORDINAL, _CARRE, _CUBE = "to_the", "ordinal", "squared", "cubed"


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
            return avant.nature not in (VARIABLE,) and not (avant.nature == OPERATEUR and avant.texte == ")")
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
                debut = i + 1
                exposant, i = self.unaire_simple(i + 1)
                self._roles_exposant(debut - 1, exposant)
                base = Puissance(base, exposant)
            elif signe == "_":
                indice, i = self.atome(i + 1)
                base = Indice(base, indice)
            elif signe == "!":
                base, i = Factorielle(base), i + 1
            else:
                break
        return base, i

    def _roles_exposant(self, k: int, exposant) -> None:
        """« ^ » : squared, cubed, to the fourth, to the minus three, to the n, to the power of (…)."""
        if isinstance(exposant, Num) and not exposant.nombre.decimales:
            n = int(exposant.nombre.entier)
            if n in (2, 3):
                self.roles[k], self.roles[k + 1] = _MUETTE, _CARRE if n == 2 else _CUBE
            else:
                self.roles[k], self.roles[k + 1] = _A_LA, _ORDINAL
        elif isinstance(exposant, (Neg, Var)):
            self.roles[k] = _A_LA

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
            entier, _, decimales = jeton.texte.partition(".")
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
    if isinstance(arbre, (Neg, Groupe)):
        return _est_une_expression(arbre.operande if isinstance(arbre, Neg) else arbre.contenu)
    if isinstance(arbre, Factorielle):
        return _est_une_expression(arbre.operande)          # « 3! » seul : une exclamation
    return isinstance(arbre, (Puissance, Indice, Racine, Appel))


def _prose(jetons: list[Jeton]) -> bool:
    """Écritures de la prose qui ressemblent à une expression : traits d'union collés seuls (F-16, 3-D, 978-3-16),
    barre entre lettres seules (w/o, I/O), lettre seule et nombre (A4, B12 : pas un produit)."""
    operateurs = [j for j in jetons if j.nature == OPERATEUR and j.texte not in "()"]
    if operateurs and all(j.texte == "-" and not j.espace_avant for j in operateurs):
        k = jetons.index(operateurs[0])
        if k + 1 < len(jetons) and not jetons[k + 1].espace_avant:
            return True
    if operateurs and all(j.texte == "/" for j in operateurs) and not any(j.nature == NOMBRE_ for j in jetons):
        return True
    if len(operateurs) == 1 and operateurs[0].texte == "/" and len(jetons) == 3 and jetons[2].nature == NOMBRE_ \
            and (jetons[2].texte.startswith("0") or len(jetons[0].texte) == 4):
        return True                       # « 3/03 » (date), « 2001/02 » (année scolaire)
    if len(operateurs) >= 2 and all(j.texte == "/" for j in operateurs):
        return True                       # 26/09/2000, 10/31/00 : des dates
    for k, j in enumerate(jetons[:-1]):
        if j.texte == "-" and jetons[k + 1].texte == "-" and jetons[k + 1].nature == OPERATEUR:
            return True                   # « a -- b » : un tiret
        if j.texte == "<" and jetons[k + 1].texte == "3" and not jetons[k + 1].espace_avant and k + 2 == len(jetons):
            return True                   # « I <3 » : un cœur
    return False


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
        if _prose(jetons[:n]):
            return None
        if n == 2 and jetons[0].nature == NOMBRE_ and jetons[1].texte in ("x", "X", "k", "K") and not jetons[1].espace_avant:
            return None                   # « 3x faster », « 2k », « 4K » : au type nombre
        return _Analyse(arbre, tuple(jetons[:n]), tuple((k, r) for k, r in analyseur.roles.items() if k < n))


# ── Lecture ────────────────────────────────────────────────────────────────────


def _lire(a: _Analyse) -> list[MotLu]:
    table = _table()
    roles = dict(a.roles)
    mots: list[MotLu] = []
    for k, jeton in enumerate(a.jetons):
        plage = (jeton.debut, jeton.fin)
        role = roles.get(k)
        if role == _MUETTE:
            continue
        if jeton.nature == NOMBRE_:
            if role == _ORDINAL:
                entier = jeton.texte
                lus = lire_ordinal(entier, list(range(jeton.debut, jeton.fin)))
                if int(entier) == 1:
                    lus = [MotLu("first", *plage)]
                mots.extend(_composant(lus, k))
            elif role in (_CARRE, _CUBE):
                mots.append(MotLu(role, *plage, composant=k))
            else:
                mots.extend(_composant(lire_nombre_aligne(jeton.texte, jeton.debut), k))
            continue
        if role == _DE:
            lecture = ("of",)
        elif role == _DE_OUVRE:
            lecture = ("of",) + table["("][1]
        elif role == _A_LA:
            lecture = ("to", "the")
        elif jeton.nature == VARIABLE and (jeton.texte not in table or table[jeton.texte][0] != VARIABLE):
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
        return arbre.nombre.entier + ("." + arbre.nombre.decimales if arbre.nombre.decimales else "")
    if isinstance(arbre, Var):
        return arbre.nom
    if isinstance(arbre, Bin):
        if arbre.op in _RELATIONS or arbre.op in ("+", "-", "±", "∓"):
            return e(arbre.gauche) + " " + arbre.op + " " + e(arbre.droite)
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

# Lettres admises comme variables dans le sens mots → formule : celles qui ne sont pas aussi des mots courants.
_VARIABLES_DITES = frozenset("bcdefghjklmnpqrstuvwxyz")


@cache
def _signes_des_mots() -> list[tuple[tuple[str, ...], str, str]]:
    """Lectures (suites de mots) → signe et nature, les plus longues d'abord."""
    lectures: dict[tuple[str, ...], tuple[str, str]] = {}
    for signe, (nature, lecture) in _table().items():
        cle = tuple(elements(list(lecture)))
        if signe in ("²", "³", "^") or (cle in lectures and not signe.islower()):
            continue
        lectures[cle] = (signe, nature)
    return sorted(((c, s, n) for c, (s, n) in lectures.items()), key=lambda x: len(x[0]), reverse=True)


def _reconnaitre(elems: list[str], i: int) -> tuple[object, int] | None:
    pieces: list[tuple[str, int]] = []
    ecrit = ""
    j = i
    appel = False
    fermer = False
    while j < len(elems):
        atome = False
        nombre = reconnaitre_nombre(elems, j, signe=False) if elems[j] not in ("minus", "a") else None
        signe = next(((c, s, n) for c, s, n in _signes_des_mots() if tuple(elems[j : j + len(c)]) == c), None)
        if elems[j] in ("squared", "cubed") and ecrit:
            ecrit += "²" if elems[j] == "squared" else "³"
            j += 1
        elif elems[j : j + 4] == ["to", "the", "power", "of"] and ecrit:
            ecrit += "^"
            j += 4
            pieces.append((ecrit, j))
            continue
        elif elems[j : j + 2] == ["to", "the"] and ecrit and j + 2 < len(elems):
            k = j + 2
            o = plus_long_ordinal(elems, k)
            if o:
                ecrit += f"^{o[0]}"
                j = o[1]
            elif elems[k] == "minus" and (n := reconnaitre_nombre(elems, k + 1, signe=False)):
                ecrit += f"^-{n[0].entier}"
                j = n[1]
            elif elems[k] in _VARIABLES_DITES:
                ecrit += "^" + elems[k]
                j = k + 1
            else:
                break
            atome = True
        elif nombre:
            v, j = nombre
            ecrit += v.entier + ("." + v.decimales if v.decimales else "")
            atome, appel = True, False
        elif elems[j] == "of" and appel:
            ouvrante = ("open", "parenthesis")
            if tuple(elems[j + 1 : j + 3]) == ouvrante:
                j += 2
            else:
                fermer = True
            ecrit += "("
            j += 1
            appel = False
        elif signe:
            cle, texte, nature = signe
            ecrit += (" " + texte + " ") if texte in _RELATIONS or texte in ("+", "-", "±", "∓") else texte
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
        pieces.append((ecrit.strip(), j))
    for ecrit, fin in reversed(pieces):
        a = MATHS.motif.match(ecrit)
        if a and a.end() == len(ecrit) and elements([m.texte for m in _lire(a)]) == elems[i:fin]:
            return a.arbre, fin
    return None


MATHS = TypeFormule("maths", _Motif(), lambda a: a.arbre, _lire, _reconnaitre, ecrire_expression)


_DEBUT_EXPRESSION = re.compile(r"^(?:[a-zA-Zα-ωΑ-Ω](?:[(_^²³]|$)|(?:" + "|".join(_FONCTIONS) + r")\(|[(√])")


def debute_une_expression(mot, suivant) -> bool:
    """Un mot du document peut-il ouvrir une expression qui ne commence pas par un chiffre ?"""
    forme = mot.forme
    if forme in ("(", "√") or forme.startswith("√"):
        return True
    if not _DEBUT_EXPRESSION.match(forme):
        return False
    if len(forme) > 1:
        return True                       # « f(x) », « x² », « x_1 », « sin(x) »
    if suivant is None:
        return False
    if suivant.espace_avant and suivant.forme[:1] not in _BINAIRES:
        return False
    return suivant.forme[:1] in _BINAIRES or suivant.forme[:1] in "(^_²³!"


# ── Notation scientifique ──────────────────────────────────────────────────────
# « 1.5e10 » est une autre écriture de « 1.5×10^10 » : même arbre, même lecture.

_SCIENTIFIQUE = re.compile(r"(?P<mantisse>\d+(?:\.\d+)?)(?P<e>[eE])(?P<exposant>[-−+]?\d+)(?![\w])")


def _en_maths(m: re.Match[str]) -> str:
    return f"{m.group('mantisse')}×10^{m.group('exposant').lstrip('+').replace(chr(0x2212), '-')}"


def _construire_scientifique(m: re.Match[str]):
    a = MATHS.motif.match(_en_maths(m))
    return a.arbre if a else None


def _lire_scientifique(m: re.Match[str]) -> list[MotLu]:
    """Lecture de l'écriture développée, replacée sur la source : mantisse, « e », exposant."""
    plages = [(m.start("mantisse"), m.end("mantisse")), (m.start("e"), m.end("e")),
              (m.start("exposant"), m.end("exposant"))]
    mots = []
    for mot in _lire(MATHS.motif.match(_en_maths(m))):
        partie = 0 if mot.composant == 0 else 1 if mot.composant <= 3 else 2
        if partie == 0:
            mots.append(MotLu(mot.texte, mot.debut + m.start(), mot.fin + m.start()))
        else:
            mots.append(MotLu(mot.texte, *plages[partie], composant=partie))
    return mots


SCIENTIFIQUE = TypeFormule("scientifique", _SCIENTIFIQUE, _construire_scientifique, _lire_scientifique,
                           lambda elems, i: None, ecrire_expression)
