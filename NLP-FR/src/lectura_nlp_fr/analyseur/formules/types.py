# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Types de formules : une définition par type, utilisée dans les deux sens.

Chaque type fournit :

- ``motif`` et ``construire`` : forme écrite → valeur ;
- ``lire`` : forme écrite → mots, chacun aligné sur la plage de la source qu'il lit ;
- ``reconnaitre`` : mots → valeur ;
- ``ecrire`` : valeur → forme écrite de référence.

La lecture produit des mots orthographiques ; leur prononciation vient ensuite du
lexique et des modèles, comme pour n'importe quel mot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Callable

from .briques import briques
from .nombres import (
    ELEMENTS,
    ET,
    MOINS,
    VIRGULE,
    ZERO,
    MotLu,
    ecrire_entier,
    entier_depuis_elements,
    lire_chiffres,
    plus_long_entier,
)

# ── Valeurs ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Nombre:
    entier: str                # chiffres, zéros initiaux conservés
    decimales: str = ""
    negatif: bool = False


@dataclass(frozen=True)
class Ordinal:
    rang: int
    feminin: bool = False
    pluriel: bool = False
    second: bool = False       # « 2nd » plutôt que « 2e »


@dataclass(frozen=True)
class Pourcentage:
    nombre: Nombre
    pour_mille: bool = False


@dataclass(frozen=True)
class Heure:
    heures: int
    minutes: int | None = None


@dataclass(frozen=True)
class Date:
    jour: int
    mois: int
    annee: int | None = None


@dataclass(frozen=True)
class Monnaie:
    montant: Nombre
    devise: str                # code ISO




@dataclass(frozen=True)
class TypeFormule:
    nom: str
    motif: re.Pattern[str]
    construire: Callable[[re.Match[str]], object | None]
    lire: Callable[[re.Match[str]], list[MotLu]]
    reconnaitre: Callable[[list[str], int], tuple[object, int] | None]
    ecrire: Callable[[object], str]


def _composant(mots: list[MotLu], k: int) -> list[MotLu]:
    return [replace(m, composant=k) for m in mots]


def _bloc(mots: list[MotLu], debut: int, fin: int, composant: int = 0) -> list[MotLu]:
    """Tous les mots lisent ensemble la même plage : partie d'une formule composée
    (jour, année, heures, groupe d'un numéro), lue d'un bloc et non chiffre à chiffre."""
    return [
        MotLu(m.texte, debut, fin, tuple(replace(e, debut=debut, fin=fin) for e in m.elements), composant)
        for m in mots
    ]


# ── Nombre ─────────────────────────────────────────────────────────────────────

# Espaces possibles dans un nombre ou entre un nombre et son symbole : ordinaire, insécable, fine insécable, fine
# (U+2009 : séparateur de milliers de FLEURS et de nombreux textes typographiés).
_ESPACES = "    "
_NOMBRE = rf"(?:\d{{1,3}}(?:[{_ESPACES}']\d{{3}})+(?!\d)|\d+)(?:[,.]\d+)?"
_SIGNE = r"[-−+]"
# Une formule ne se termine pas au milieu d'un mot ou d'un nombre.
_FIN = r"(?![\w])"
_CHIFFRES_0_9 = [ecrire_entier(n)[0] for n in range(10)]


def _chiffres(m: re.Match[str], groupe: str) -> tuple[str, list[int]]:
    """Chiffres d'un groupe et place de chacun dans la source (séparateurs de milliers ôtés)."""
    debut = m.start(groupe)
    paires = [(c, debut + k) for k, c in enumerate(m.group(groupe)) if c.isdigit() or c in ",."]
    return "".join(c for c, _ in paires), [p for _, p in paires]


def _couper_decimales(chiffres: str, places: list[int]) -> tuple[str, list[int], str, list[int], int | None]:
    for k, c in enumerate(chiffres):
        if c in ",.":
            return chiffres[:k], places[:k], chiffres[k + 1 :], places[k + 1 :], places[k]
    return chiffres, places, "", [], None


def _nombre_du_groupe(m: re.Match[str], groupe: str = "nombre", signe: str | None = "signe") -> Nombre:
    entier, _, decimales, _, _ = _couper_decimales(*_chiffres(m, groupe))
    negatif = bool(signe) and m.group(signe) in ("-", "−")
    return Nombre(entier, decimales, negatif)


def _lire_decimales(decimales: str, places: list[int]) -> list[MotLu]:
    """Zéros initiaux dits un à un, puis le reste comme un nombre s'il a trois chiffres au plus."""
    k = len(decimales) - len(decimales.lstrip("0"))
    mots = [MotLu(ZERO, p, p + 1) for p in places[:k]]
    reste, places = decimales[k:], places[k:]
    if not reste:
        return mots
    if len(reste) <= 3:
        return mots + lire_chiffres(reste, places)
    return mots + [MotLu(_CHIFFRES_0_9[int(c)], p, p + 1) for c, p in zip(reste, places)]


def _lire_groupe_nombre(
    m: re.Match[str], groupe: str = "nombre", signe: str | None = "signe", feminin: bool = False
) -> list[MotLu]:
    entier, places_e, decimales, places_d, virgule = _couper_decimales(*_chiffres(m, groupe))
    mots = []
    if signe and m.group(signe) in ("-", "−"):
        mots.append(MotLu(MOINS, m.start(signe), m.end(signe)))
    mots.extend(lire_chiffres(entier, places_e, feminin=feminin and not decimales))
    if decimales:
        mots.append(MotLu(VIRGULE, virgule, virgule + 1))
        mots.extend(_lire_decimales(decimales, places_d))
    return mots


def _reconnaitre_chiffres(elems: list[str], i: int) -> tuple[str, int] | None:
    """Zéros initiaux puis entier : renvoie les chiffres tels qu'ils s'écrivent."""
    j = i
    while j < len(elems) and elems[j] == ZERO:
        j += 1
    zeros = "0" * (j - i)
    suite = plus_long_entier(elems, j)
    if suite is None or suite[0] == 0:
        return (zeros, j) if zeros else None
    return zeros + str(suite[0]), suite[1]


def _reconnaitre_decimales(elems: list[str], i: int) -> tuple[str, int] | None:
    j = i
    while j < len(elems) and elems[j] == ZERO:
        j += 1
    zeros = "0" * (j - i)
    # Quatre chiffres ou plus : dits un à un.
    k = j
    while k < len(elems) and elems[k] in _CHIFFRES_0_9:
        k += 1
    if k - j >= 4:
        return zeros + "".join(str(_CHIFFRES_0_9.index(e)) for e in elems[j:k]), k
    suite = plus_long_entier(elems, j, maximum=999)
    if suite is None or suite[0] == 0:
        return (zeros, j) if zeros else None
    return zeros + str(suite[0]), suite[1]


# « moins » n'est un signe qu'après un mot qui annonce une valeur (« il fait moins cinq », « égal à moins trois ») ou
# en tête ; ailleurs c'est l'adverbe (« au moins deux fois », « encore moins un reniement »).
_AVANT_NEGATIF = frozenset("fait faisait fera ferait à a est était sera égal égale égaux vaut valait valent "
                           "atteint atteignait descend descendu jusqu'à environ entre et de = : ( , ;".split())


def _reconnaitre_nombre(elems: list[str], i: int) -> tuple[Nombre, int] | None:
    negatif = elems[i] == MOINS
    if negatif and i > 0 and elems[i - 1] not in _AVANT_NEGATIF:
        return None
    j = i + 1 if negatif else i
    if j >= len(elems):
        return None
    entier = _reconnaitre_chiffres(elems, j)
    if entier is None:
        return None
    chiffres, j = entier
    decimales = ""
    if j < len(elems) - 1 and elems[j] == VIRGULE:
        suite = _reconnaitre_decimales(elems, j + 1)
        if suite:
            decimales, j = suite
    return Nombre(chiffres, decimales, negatif), j


def _grouper_milliers(entier: str) -> str:
    if len(entier) <= 4 or entier.startswith("0"):
        return entier
    tete = len(entier) % 3 or 3
    return " ".join([entier[:tete]] + [entier[k : k + 3] for k in range(tete, len(entier), 3)])


def _ecrire_nombre(v: Nombre) -> str:
    return ("-" if v.negatif else "") + _grouper_milliers(v.entier) + ("," + v.decimales if v.decimales else "")


NOMBRE = TypeFormule(
    "nombre",
    re.compile(rf"(?P<signe>{_SIGNE})?(?P<nombre>{_NOMBRE}){_FIN}"),
    _nombre_du_groupe,
    _lire_groupe_nombre,
    _reconnaitre_nombre,
    _ecrire_nombre,
)

# ── Ordinal ────────────────────────────────────────────────────────────────────

_SUFFIXES_ORDINAUX = {
    "er": (False, False), "ers": (False, True), "re": (True, False), "res": (True, True),
    "ère": (True, False), "ères": (True, True), "e": (False, False), "es": (False, True),
    "ème": (False, False), "èmes": (False, True), "nd": (False, False), "nds": (False, True),
    "nde": (True, False), "ndes": (True, True),
}
_PREMIERS = {"premier": (False, False), "premiers": (False, True), "première": (True, False), "premières": (True, True)}
_SECONDS = {"second": (False, False), "seconds": (False, True), "seconde": (True, False), "secondes": (True, True)}


def _ordinal_de(element: str) -> str:
    """Dernier élément d'un cardinal → élément ordinal (« cinq » → « cinquième »)."""
    if element in ("vingts", "cents"):
        element = element[:-1]
    if element == "cinq":
        return "cinquième"
    if element == "neuf":
        return "neuvième"
    return element.rstrip("e") + "ième"


def _mots_ordinal(v: Ordinal) -> list[str]:
    s = "s" if v.pluriel else ""
    if v.rang == 1:
        return [("première" if v.feminin else "premier") + s]
    if v.rang == 2 and v.second:
        return [("seconde" if v.feminin else "second") + s]
    mots = ecrire_entier(v.rang)
    *debut, dernier = mots[-1].split("-")
    mots[-1] = "-".join(debut + [_ordinal_de(dernier) + s])
    return mots


def _construire_ordinal(m: re.Match[str]) -> Ordinal | None:
    rang, suffixe = int(m.group("rang")), m.group("suffixe")
    feminin, pluriel = _SUFFIXES_ORDINAUX[suffixe]
    if (suffixe.rstrip("s") in ("er", "re", "ère")) != (rang == 1) or (suffixe.startswith("nd") and rang != 2):
        return None
    return Ordinal(rang, feminin, pluriel, second=suffixe.startswith("nd"))


def _lire_ordinal(m: re.Match[str]) -> list[MotLu]:
    v = _construire_ordinal(m)
    if v.rang == 1 or v.second:
        return [MotLu(mot, m.start(), m.end()) for mot in _mots_ordinal(v)]
    # Alignement du cardinal ; le dernier élément prend la forme ordinale et lit aussi le suffixe.
    mots = lire_chiffres(m.group("rang"), list(range(m.start("rang"), m.end("rang"))))
    dernier = mots[-1]
    forme = _ordinal_de(dernier.elements[-1].texte) + ("s" if v.pluriel else "")
    element = replace(dernier.elements[-1], texte=forme, fin=m.end())
    texte = "-".join([e.texte for e in dernier.elements[:-1]] + [forme])
    mots[-1] = MotLu(texte, dernier.debut, m.end(), dernier.elements[:-1] + (element,))
    return mots


def _reconnaitre_ordinal(elems: list[str], i: int) -> tuple[Ordinal, int] | None:
    e = elems[i]
    if e in _PREMIERS:
        return Ordinal(1, *_PREMIERS[e]), i + 1
    if e in _SECONDS:
        return Ordinal(2, *_SECONDS[e], second=True), i + 1
    # Le dernier élément d'un ordinal est le seul à finir en « -ième ».
    j = i
    while j < len(elems) and (elems[j] in ELEMENTS or elems[j] == ET):
        j += 1
    if j >= len(elems) or not elems[j].rstrip("s").endswith("ième"):
        return None
    for rang in _rangs_possibles(elems[i:j], elems[j]):
        pluriel = elems[j].endswith("s")
        if [x for mot in _mots_ordinal(Ordinal(rang, pluriel=pluriel)) for x in mot.split("-")] == elems[i : j + 1]:
            return Ordinal(rang, pluriel=pluriel), j + 1
    return None


def _rangs_possibles(debut: list[str], dernier: str) -> list[int]:
    rangs = []
    for cardinal in ELEMENTS:
        if _ordinal_de(cardinal) == dernier.rstrip("s"):
            n = entier_depuis_elements(debut + [cardinal])
            if n is not None and n > 1:
                rangs.append(n)
    return rangs


def _ecrire_ordinal(v: Ordinal) -> str:
    s = "s" if v.pluriel else ""
    if v.rang == 1:
        return "1" + ("re" if v.feminin else "er") + s
    if v.second:
        return "2" + ("nde" if v.feminin else "nd") + s
    return f"{v.rang}e{s}"


ORDINAL = TypeFormule(
    "ordinal",
    re.compile(rf"(?P<rang>\d+)(?P<suffixe>{'|'.join(sorted(_SUFFIXES_ORDINAUX, key=len, reverse=True))}){_FIN}"),
    _construire_ordinal,
    _lire_ordinal,
    _reconnaitre_ordinal,
    _ecrire_ordinal,
)

# ── Pourcentage ────────────────────────────────────────────────────────────────


def _lire_pourcentage(m: re.Match[str]) -> list[MotLu]:
    symbole = (m.start("symbole"), m.end("symbole"))
    return _lire_groupe_nombre(m) + [
        MotLu("pour", *symbole, composant=1),
        MotLu("mille" if m.group("symbole") == "‰" else "cent", *symbole, composant=1),
    ]


def _reconnaitre_pourcentage(elems: list[str], i: int) -> tuple[Pourcentage, int] | None:
    nombre = _reconnaitre_nombre(elems, i)
    if nombre is None:
        return None
    v, j = nombre
    if elems[j : j + 2] == ["pour", "cent"] or elems[j : j + 2] == ["pour", "mille"]:
        return Pourcentage(v, elems[j + 1] == "mille"), j + 2
    return None


POURCENTAGE = TypeFormule(
    "pourcentage",
    re.compile(rf"(?P<signe>{_SIGNE})?(?P<nombre>{_NOMBRE})[{_ESPACES}]?(?P<symbole>[%‰])"),
    lambda m: Pourcentage(_nombre_du_groupe(m), m.group("symbole") == "‰"),
    _lire_pourcentage,
    _reconnaitre_pourcentage,
    lambda v: _ecrire_nombre(v.nombre) + " " + ("‰" if v.pour_mille else "%"),
)

# ── Heure ──────────────────────────────────────────────────────────────────────


def _construire_heure(m: re.Match[str]) -> Heure | None:
    h = int(m.group("h"))
    minutes = int(m.group("min")) if m.group("min") else None
    if h > 24 or (minutes or 0) > 59:
        return None
    return Heure(h, minutes)


def _lire_heure(m: re.Match[str]) -> list[MotLu]:
    v = _construire_heure(m)
    mots = _bloc(lire_chiffres(str(v.heures), feminin=True), m.start("h"), m.end("h"))
    mots.append(MotLu("heures" if v.heures > 1 else "heure", m.start("sep"), m.end("sep")))
    if v.minutes:
        mots.extend(_bloc(lire_chiffres(str(v.minutes), feminin=True), m.start("min"), m.end("min"), 1))
    return mots


_AVANT_HEURE = frozenset("à a vers dès dés jusqu'à avant après de entre et est était sera sonne sonnent sonnaient "
                         "midi minuit".split())


def _reconnaitre_heure(elems: list[str], i: int) -> tuple[Heure, int] | None:
    h = plus_long_entier(elems, i, maximum=24)
    if h is None or h[1] >= len(elems) or elems[h[1]] not in ("heure", "heures"):
        return None
    j = h[1] + 1
    # « et quart », « et demie », « moins le quart », « moins dix » (minutes avant l'heure).
    suite = elems[j : j + 3]
    if suite[:2] in (["et", "quart"], ["et", "demie"]):
        return Heure(h[0], 15 if suite[1] == "quart" else 30), j + 2
    if suite == ["moins", "le", "quart"] and h[0] >= 1:
        return Heure(h[0] - 1, 45), j + 3
    if suite[:1] == ["moins"] and h[0] >= 1:
        avant = plus_long_entier(elems, j + 1, maximum=30)
        if avant and avant[0] and elems[avant[1] : avant[1] + 1] not in (["minute"], ["minutes"]):
            return Heure(h[0] - 1, 60 - avant[0]), avant[1]
    minutes = plus_long_entier(elems, j, maximum=59) if j < len(elems) else None
    # « trois heures vingt minutes » est une durée, pas une heure.
    if minutes and minutes[0] and elems[minutes[1] : minutes[1] + 1] not in (["minute"], ["minutes"]):
        return Heure(h[0], minutes[0]), minutes[1]
    # Sans minutes, « une heure de route », « trois heures de marche » sont des durées : une heure n'est reconnue
    # qu'après un mot qui introduit un moment (« à dix heures », « il est midi », « de neuf heures à midi »).
    if i == 0 or elems[i - 1] not in _AVANT_HEURE:
        return None
    return Heure(h[0]), j


HEURE = TypeFormule(
    "heure",
    re.compile(
        rf"(?P<h>\d{{1,2}})(?P<sep>[{_ESPACES}]?[hH][{_ESPACES}]?(?=\d{{2}}{_FIN})|[{_ESPACES}]?[hH]{_FIN}|:(?=\d{{2}}{_FIN}))"
        rf"(?P<min>\d{{2}})?{_FIN}"
    ),
    _construire_heure,
    _lire_heure,
    _reconnaitre_heure,
    lambda v: f"{v.heures}h" + (f"{v.minutes:02d}" if v.minutes else ""),
)

# ── Date ───────────────────────────────────────────────────────────────────────

MOIS = [b.lecture for _n, b in sorted(briques("mois").items(), key=lambda x: int(x[0]))]


# Mois écrits en lettres, en entier ou abrégés (« janv. », « sept. »), pour les dates en toutes lettres.
_MOIS_ABREGES = {"janv": 1, "févr": 2, "fév": 2, "avr": 4, "juil": 7, "sept": 9, "oct": 10, "nov": 11, "déc": 12}
_MOIS_ECRITS = {**{nom: k for k, nom in enumerate(MOIS, 1)}, **_MOIS_ABREGES}
_MOTIF_MOIS = "|".join(
    [re.escape(x) for x in sorted(MOIS, key=len, reverse=True)]
    + [re.escape(x) + r"\." for x in sorted(_MOIS_ABREGES, key=len, reverse=True)]
)


def _groupes_date(m: re.Match[str]) -> tuple[str, str, str]:
    """Noms des groupes jour, mois, année selon l'écriture (JJ/MM/AAAA, AAAA-MM-JJ, « 3 mars 2024 »)."""
    if m.group("j"):
        return ("j", "m", "a")
    if m.group("j2"):
        return ("j2", "m2", "a2")
    return ("j3", "m3", "a3")


def _mois_de(m: re.Match[str], groupe: str) -> int:
    ecrit = m.group(groupe)
    return _MOIS_ECRITS[ecrit.lower().rstrip(".")] if groupe == "m3" else int(ecrit)


def _construire_date(m: re.Match[str]) -> Date | None:
    j, mo, a = _groupes_date(m)
    jour, mois = int(m.group(j).removesuffix("er")), _mois_de(m, mo)
    annee = int(m.group(a)) if m.group(a) else None
    if not (1 <= jour <= 31 and 1 <= mois <= 12):
        return None
    return Date(jour, mois, annee)


def _lire_date(m: re.Match[str]) -> list[MotLu]:
    v = _construire_date(m)
    j, mo, a = _groupes_date(m)
    if v.jour == 1:
        mots = [MotLu("premier", m.start(j), m.end(j))]
    else:
        mots = _bloc(lire_chiffres(str(v.jour)), m.start(j), m.end(j))
    mots.append(MotLu(MOIS[v.mois - 1], m.start(mo), m.end(mo), composant=1))
    if not m.group(a):
        return mots
    return mots + _bloc(lire_chiffres(m.group(a)), m.start(a), m.end(a), 2)


def _reconnaitre_date(elems: list[str], i: int) -> tuple[Date, int] | None:
    if elems[i] == "premier":
        jour = (1, i + 1)
    else:
        jour = plus_long_entier(elems, i, maximum=31)
    if jour is None or jour[0] < 1 or jour[1] >= len(elems) or elems[jour[1]] not in MOIS:
        return None
    mois = MOIS.index(elems[jour[1]]) + 1
    j = jour[1] + 1
    annee = plus_long_entier(elems, j, maximum=9999) if j < len(elems) else None
    if annee and annee[0] >= 1000:
        return Date(jour[0], mois, annee[0]), annee[1]
    return Date(jour[0], mois), j


def ecrire_date(v: Date, longue: bool = False) -> str:
    if longue or v.annee is None:
        jour = "1er" if v.jour == 1 else str(v.jour)
        return f"{jour} {MOIS[v.mois - 1]}" + (f" {v.annee}" if v.annee is not None else "")
    return f"{v.jour:02d}/{v.mois:02d}/{v.annee}"


DATE = TypeFormule(
    "date",
    re.compile(
        rf"(?:(?P<j>\d{{1,2}})(?P<s>[/.-])(?P<m>\d{{1,2}})(?P=s)(?P<a>\d{{4}}|\d{{2}})"
        rf"|(?P<a2>\d{{4}})-(?P<m2>\d{{2}})-(?P<j2>\d{{2}})"
        # « 3 mars 2024 », « 1er janvier », « 14 juil. 1789 »
        rf"|(?P<j3>1er|\d{{1,2}})\s+(?P<m3>(?i:{_MOTIF_MOIS}))(?:\s+(?P<a3>\d{{3,4}}))?){_FIN}"
    ),
    _construire_date,
    _lire_date,
    _reconnaitre_date,
    ecrire_date,
)

# ── Monnaie ────────────────────────────────────────────────────────────────────

# Code de chaque devise ; « trois livres » est trop ambigu pour être reconnu en sens inverse.
_CODES_DEVISES = {"€": "EUR", "$": "USD", "£": "GBP", "¥": "JPY"}
_DEVISES_NON_RECONNUES = frozenset({"£"})
# symbole → (code, singulier, pluriel, reconnu dans le sens inverse) ; noms tirés du lexique.
_DEVISES = {
    s: (_CODES_DEVISES[s], b.lecture, b.lecture_pluriel or b.lecture, s not in _DEVISES_NON_RECONNUES)
    for s, b in briques("devise").items()
    if s in _CODES_DEVISES
}
# Codes écrits en lettres (« 3500 FF », « CHF 20 ») : lus en toutes lettres à côté d'un nombre seulement (le lexique ne
# les a qu'épelés), jamais reconnus dans le sens inverse (« trois francs » reste écrit en lettres).
_CODES_EN_LETTRES = {
    "EUR": ("EUR", "euro", "euros"), "USD": ("USD", "dollar", "dollars"),
    "GBP": ("GBP", "livre sterling", "livres sterling"), "CHF": ("CHF", "franc suisse", "francs suisses"),
    "CAD": ("CAD", "dollar canadien", "dollars canadiens"), "JPY": ("JPY", "yen", "yens"),
    "FF": ("FRF", "franc", "francs"), "FRF": ("FRF", "franc", "francs"), "FB": ("BEF", "franc belge", "francs belges"),
    "FCFA": ("XOF", "franc CFA", "francs CFA"), "XOF": ("XOF", "franc CFA", "francs CFA"),
    "DH": ("MAD", "dirham", "dirhams"), "MAD": ("MAD", "dirham", "dirhams"),
    "DA": ("DZD", "dinar", "dinars"), "DZD": ("DZD", "dinar", "dinars"), "TND": ("TND", "dinar", "dinars"),
}
_DEVISES.update({s: (code, sg, pl, False) for s, (code, sg, pl) in _CODES_EN_LETTRES.items()})
CODES_EN_LETTRES = frozenset(_CODES_EN_LETTRES)
_NOMS_D_ECHELLE = ("million", "milliard", "billion")
# Écriture canonique d'un code : son symbole s'il en a un, sinon la première écriture en lettres.
_SYMBOLE_DE: dict[str, str] = {}
for _s, (_code, *_r) in _DEVISES.items():
    _SYMBOLE_DE.setdefault(_code, _s)
_DEVISE_DU_MOT = {mot: code for code, s, p, inverse in _DEVISES.values() if inverse for mot in (s, p)}


def _groupes_monnaie(m: re.Match[str]) -> tuple[str, str, str]:
    """Noms des groupes signe, nombre, symbole selon l'écriture (« 25 € » ou « $25 »)."""
    return ("signe", "nombre", "symbole") if m.group("symbole") else ("signe2", "nombre2", "symbole2")


def _construire_monnaie(m: re.Match[str]) -> Monnaie:
    signe, nombre, symbole = _groupes_monnaie(m)
    montant = _nombre_du_groupe(m, nombre, signe)
    if m.group("cent"):
        montant = replace(montant, decimales=m.group("cent"))
    return Monnaie(montant, _DEVISES[m.group(symbole)][0])


def _lire_monnaie(m: re.Match[str]) -> list[MotLu]:
    g_signe, g_nombre, g_symbole = _groupes_monnaie(m)
    v = _construire_monnaie(m)
    _, singulier, pluriel, _ = _DEVISES[m.group(g_symbole)]
    symbole = (m.start(g_symbole), m.end(g_symbole))
    entier, places_e, decimales, places_d, _ = _couper_decimales(*_chiffres(m, g_nombre))
    if m.group("cent"):
        decimales, places_d = m.group("cent"), list(range(m.start("cent"), m.end("cent")))
    if len(decimales) not in (0, 2):
        # Montant à précision inhabituelle : lu comme un nombre suivi de la devise.
        return _lire_groupe_nombre(m, g_nombre, g_signe) + _lire_devise(pluriel, symbole)
    mots = [MotLu(MOINS, m.start(g_signe), m.end(g_signe))] if v.montant.negatif else []
    centimes = int(decimales or 0)
    partie_entiere = (places_e[0], places_e[-1] + 1)
    partie_decimale = (places_d[0], places_d[-1] + 1) if places_d else None
    if int(entier) or not centimes:
        mots.extend(_bloc(lire_chiffres(entier), *partie_entiere))
        if mots[-1].texte.rstrip("s") in _NOMS_D_ECHELLE:
            mots.append(MotLu("de", *symbole))  # « deux millions de dollars »
        mots.extend(_lire_devise(pluriel if int(entier) > 1 else singulier, symbole))
        if centimes:
            mots.extend(_bloc(lire_chiffres(str(centimes)), *partie_decimale, 1))
    else:
        mots.extend(_bloc(lire_chiffres(str(centimes)), *partie_decimale))
        mots.append(MotLu("centimes" if centimes > 1 else "centime", *symbole))
    return mots


def _lire_devise(nom: str, symbole: tuple[int, int]) -> list[MotLu]:
    """« francs suisses » : un mot lu par mot du nom, tous rattachés au signe."""
    return [MotLu(mot, *symbole) for mot in nom.split()]


def _reconnaitre_monnaie(elems: list[str], i: int) -> tuple[Monnaie, int] | None:
    negatif = elems[i] == MOINS
    j = i + 1 if negatif else i
    entier = plus_long_entier(elems, j) if j < len(elems) else None
    if entier is None or entier[1] >= len(elems):
        return None
    n, j = entier
    if elems[j] in ("centime", "centimes") and n < 100:
        return Monnaie(Nombre("0", f"{n:02d}", negatif), "EUR"), j + 1
    if elems[j] == "de" and elems[j - 1].rstrip("s") in _NOMS_D_ECHELLE and j + 1 < len(elems):
        j += 1
    devise = _DEVISE_DU_MOT.get(elems[j])
    if devise is None:
        return None
    j += 1
    centimes = plus_long_entier(elems, j, maximum=99) if j < len(elems) else None
    if centimes and centimes[0]:
        fin = centimes[1] + (elems[centimes[1] : centimes[1] + 1] in (["centime"], ["centimes"]))
        return Monnaie(Nombre(str(n), f"{centimes[0]:02d}", negatif), devise), fin
    return Monnaie(Nombre(str(n), "", negatif), devise), j


_SYMBOLES_DEVISE = "".join(re.escape(s) for s in _DEVISES if len(s) == 1)
# Signe : un symbole, ou un code en lettres isolé (« 20 CHF », pas « 20 CHFS »).
_DEVISE = (rf"[{_SYMBOLES_DEVISE}]|(?<![\w])(?:"
           + "|".join(sorted((re.escape(s) for s in _DEVISES if len(s) > 1), key=len, reverse=True)) + r")(?![\w])")

MONNAIE = TypeFormule(
    "monnaie",
    re.compile(
        rf"(?P<signe>{_SIGNE})?(?P<nombre>{_NOMBRE})[{_ESPACES}]?(?P<symbole>{_DEVISE})(?:(?P<cent>\d{{2}}){_FIN})?"
        rf"|(?P<signe2>{_SIGNE})?(?P<symbole2>{_DEVISE})[{_ESPACES}]?(?P<nombre2>{_NOMBRE}){_FIN}"
    ),
    _construire_monnaie,
    _lire_monnaie,
    _reconnaitre_monnaie,
    lambda v: _ecrire_nombre(v.montant) + " " + _SYMBOLE_DE[v.devise],
)

