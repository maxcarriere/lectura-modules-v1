# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Types de formules anglais : une définition par type, utilisée dans les deux sens.

Chaque type fournit ``motif`` et ``construire`` (forme écrite → valeur), ``lire`` (forme écrite → mots alignés sur
la source), ``reconnaitre`` (mots → valeur, sens du STT) et ``ecrire`` (valeur → forme écrite de référence).

Lectures (anglais américain usuel) : 1,905 → one thousand nine hundred five ; 3.14 → three point one four ;
-5 → minus five ; 21st → twenty first ; 5% → five percent ; 7:30 → seven thirty, 7:05 → seven oh five,
7:00 → seven o'clock, 7:30 pm → seven thirty p m, 23:45 → twenty three forty five, 13:00 → thirteen hundred ;
1990 → nineteen ninety, 1905 → nineteen oh five, 1066 → ten sixty six, 2005 → two thousand five ; 1990s → nineteen
nineties, '90s → nineties ; March 5, 2020 / 5 March 2020 / 2020-03-05 → March fifth twenty twenty ;
$3.50 → three dollars and fifty cents, $0.50 → fifty cents, $1.2 billion → one point two billion dollars.

Écriture de référence (sens inverse) : milliers séparés par une virgule dès quatre chiffres (AP : 1,905 ; une année
dite par paires s'écrit sans virgule : 1905), « March 5, 2020 », « 7:30 p.m. », « $3.50 », « 5% ».
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Callable

from .nombres import (
    ELEMENTS,
    MOINS,
    OH,
    UNITES,
    VIRGULE,
    ZERO,
    MotLu,
    annee,
    ecrire_entier,
    est_annee_par_paires,
    lire_annee,
    lire_chiffres,
    lire_ordinal,
    ordinal,
    ordinal_mot,
    plus_long_entier,
    plus_long_ordinal,
    plus_longue_annee,
    annee_dite,
    paires_dites,
)

# ── Valeurs ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Nombre:
    entier: str                # chiffres, zéros initiaux conservés
    decimales: str = ""
    negatif: bool = False
    suffixe: str = ""          # « k » (2k two thousand), « K » lu en lettre (4K four K), « x » (3x three times), « + »


@dataclass(frozen=True)
class Ordinal:
    rang: int
    feminin: bool = False
    pluriel: bool = False
    second: bool = False


@dataclass(frozen=True)
class Pourcentage:
    nombre: Nombre
    pour_mille: bool = False
    jusqua: Nombre | None = None     # plage : 5–10%


@dataclass(frozen=True)
class Heure:
    heures: int
    minutes: int | None = None
    meridien: str = ""         # « a » ou « p » (a.m., p.m.)
    secondes: int | None = None


@dataclass(frozen=True)
class Date:
    jour: int
    mois: int
    annee: int | None = None
    decennie: bool = False     # 1990s, '90s
    courte: bool = False       # année à apostrophe : '90s, '05
    jour_fin: int = 0          # plage de jours : January 10–13
    jour_dabord: bool = False  # écrite jour d'abord (5 March 2020) : lue dans l'ordre de l'écrit


@dataclass(frozen=True)
class Monnaie:
    montant: Nombre
    devise: str                # code ISO
    echelle: str = ""          # « million », « billion »…


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


def _bloc(mots: list, debut: int, fin: int, composant: int = 0) -> list[MotLu]:
    """Tous les mots lisent ensemble la même plage (partie d'une formule composée lue d'un bloc)."""
    return [MotLu(m if isinstance(m, str) else m.texte, debut, fin, composant=composant) for m in mots]


def _a_porter(elems: list[str], i: int):
    return None


_NOMBRE = r"(?:\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?:\.\d+)?"
_SIGNE = r"[-−]"
_FIN = r"(?!\d)(?![.,]\d)"
_FIN_MOT = r"(?![\w])"
_JAMAIS = re.compile(r"(?!x)x")
CHIFFRES_DITS = {**{UNITES[k]: str(k) for k in range(10)}, OH: "0"}


def _decouper(texte: str) -> tuple[str, str]:
    entier, _, dec = texte.partition(".")
    return entier.replace(",", ""), dec


def _chiffres(texte: str, debut: int) -> tuple[str, list[int], str, list[int], int | None]:
    """Chiffres de la partie entière et des décimales d'un nombre écrit, avec la place de chacun (virgules ôtées)."""
    entier, places_e, dec, places_d, point = "", [], "", [], None
    for k, c in enumerate(texte):
        if c == ".":
            point = debut + k
        elif c.isdigit():
            if point is None:
                entier, places_e = entier + c, places_e + [debut + k]
            else:
                dec, places_d = dec + c, places_d + [debut + k]
    return entier, places_e, dec, places_d, point


def lire_nombre_aligne(texte: str, debut: int, composant: int = 0) -> list[MotLu]:
    """Mots d'un nombre écrit, alignés chiffre à chiffre (« 1,905.5 » → one thousand nine hundred five point five)."""
    entier, places_e, dec, places_d, point = _chiffres(texte, debut)
    mots = lire_chiffres(entier, places_e) if entier else []
    if point is not None:
        mots.append(MotLu(VIRGULE, point, point + 1))
        mots.extend(MotLu(UNITES[int(c)], p, p + 1) for c, p in zip(dec, places_d))
    return _composant(mots, composant) if composant else mots


def lire_nombre(texte: str, debut: int = 0, fin: int = 0, composant: int = 0) -> list[str]:
    """Mots d'un nombre écrit (sans alignement)."""
    return [m.texte for m in lire_nombre_aligne(texte, debut)]


def grouper_milliers(entier: str) -> str:
    """Virgule des milliers dès quatre chiffres (AP), sauf de 2000 à 2099, dits comme des années (two thousand four)."""
    if len(entier) < 4 or entier.startswith("0") or (len(entier) == 4 and 2000 <= int(entier) <= 2099):
        return entier
    tete = len(entier) % 3 or 3
    return ",".join([entier[:tete]] + [entier[k : k + 3] for k in range(tete, len(entier), 3)])


def ecrire_nombre(v: Nombre) -> str:
    return ("-" if v.negatif else "") + grouper_milliers(v.entier) + ("." + v.decimales if v.decimales else "") + v.suffixe


# ── Nombre ─────────────────────────────────────────────────────────────────────


def _construire_nombre(m: re.Match[str]) -> Nombre:
    entier, dec = _decouper(m.group("nombre"))
    return Nombre(entier, dec, bool(m.group("signe")))


def _lire_nombre(m: re.Match[str]) -> list[MotLu]:
    mots = [MotLu(MOINS, m.start("signe"), m.end("signe"))] if m.group("signe") else []
    return mots + lire_nombre_aligne(m.group("nombre"), m.start("nombre"))


# « 4K TV », « 8K », « 5K run » : K lu comme une lettre (résolution, course), pas « thousand ».
_APRES_K_LETTRE = frozenset("run runs race races marathon resolution tv tvs video videos display displays monitor monitors "
                            "screen screens uhd hdr gaming camera cameras streaming content".split())


def _suffixe(m: re.Match[str]) -> str:
    if m.group("k"):
        if m.group("k") == "MM":
            return "MM"                    # « 15MM » : million (finance)
        if m.group("k") == "K":
            suite = re.match(r"\s*([A-Za-z]+)", m.string[m.end():])
            if m.group("nombre") in ("4", "8") or (suite and suite.group(1).lower() in _APRES_K_LETTRE):
                return "K"
        return "k"
    return "x" if m.group("fois") else "+" if m.group("plus") else ""


def _construire_nombre_seul(m: re.Match[str]) -> Nombre:
    entier, dec = _decouper(m.group("nombre"))
    return Nombre(entier, dec, bool(m.group("signe")), _suffixe(m))


def _lire_nombre_seul(m: re.Match[str]) -> list[MotLu]:
    """« 2k » two thousand (usage retenu, plutôt que « two K ») ; « 4K » four K ; « 3x faster » three times ;
    « 6,000+ » six thousand plus."""
    mots = _lire_nombre(m)
    s = _suffixe(m)
    if s:
        g = "k" if m.group("k") else "fois" if m.group("fois") else "plus"
        texte = {"k": "thousand", "MM": "million", "K": "K", "x": "times", "+": "plus"}[s]
        mots.append(MotLu(texte, m.start(g), m.end(g), composant=1, nature="lettre" if s == "K" else ""))
    return mots


# « minus » n'est un signe qu'en tête ou après un mot qui annonce une valeur ; « negative » aussi.
_AVANT_NEGATIF = frozenset("is was be are were been reached reach reaches fell falls drop dropped to at of about around "
                           "equals equal approximately = : ( , ; from by than".split())


def _reconnaitre_decimales(elems: list[str], i: int) -> tuple[str, int] | None:
    j = i
    while j < len(elems) and elems[j] in CHIFFRES_DITS:
        j += 1
    if j == i:
        return None
    return "".join(CHIFFRES_DITS[e] for e in elems[i:j]), j


_AVANT_PAIRES = frozenset("route highway interstate flight room suite apartment gate platform track bus channel "
                          "boeing airbus model exit pier".split())


def _reconnaitre_nombre_ou_paires(elems: list[str], i: int) -> tuple[Nombre, int] | None:
    r = reconnaitre_nombre(elems, i)
    if i > 0 and elems[i - 1] in _AVANT_PAIRES:
        p = paires_dites(elems, i)
        if p and (r is None or p[1] > r[1]):
            return Nombre(str(p[0])), p[1]
    return r


def reconnaitre_nombre(elems: list[str], i: int, signe: bool = True) -> tuple[Nombre, int] | None:
    negatif = elems[i] in (MOINS, "negative")
    if negatif and (not signe or (i > 0 and elems[i - 1] not in _AVANT_NEGATIF)):
        return None
    j = i + 1 if negatif else i
    if j >= len(elems):
        return None
    zeros = ""
    while j < len(elems) - 1 and elems[j] == ZERO and elems[j + 1] in UNITES[:10]:
        zeros, j = zeros + "0", j + 1
    if elems[j] == ZERO:
        entier, j = zeros + "0", j + 1
    else:
        suite = plus_long_entier(elems, j)
        if suite is None:
            if elems[j] == VIRGULE and not zeros:      # « point five »
                entier = ""
            else:
                return None
        else:
            entier, j = zeros + str(suite[0]), suite[1]
    decimales = ""
    if j < len(elems) - 1 and elems[j] == VIRGULE:
        suite = _reconnaitre_decimales(elems, j + 1)
        if suite:
            decimales, j = suite
    if not entier:
        if not decimales:
            return None
        entier = "0"
    return Nombre(entier, decimales, negatif), j


NOMBRE = TypeFormule(
    "nombre", re.compile(rf"(?P<signe>{_SIGNE})?(?P<nombre>{_NOMBRE}){_FIN}"
                         rf"(?:(?P<k>[kK]|MM)(?![\w'’])|(?P<fois>[xX×])(?=\s+[A-Za-z]|\s*[,.;:!?)]|\s*$)|(?P<plus>\+)(?![\w+]))?"),
    _construire_nombre_seul, _lire_nombre_seul, _reconnaitre_nombre_ou_paires, ecrire_nombre,
)

# ── Ordinal ────────────────────────────────────────────────────────────────────


def _suffixe_ordinal(n: int) -> str:
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _construire_ordinal(m: re.Match[str]) -> Ordinal | None:
    n = int(m.group("rang").replace(",", ""))
    return Ordinal(n) if m.group("suffixe").lower() == _suffixe_ordinal(n) and n < 10**9 else None


def _lire_ordinal(m: re.Match[str]) -> list[MotLu]:
    entier, places, *_ = _chiffres(m.group("rang"), m.start("rang"))
    return lire_ordinal(entier, places, m.end())


def _reconnaitre_ordinal(elems: list[str], i: int) -> tuple[Ordinal, int] | None:
    r = plus_long_ordinal(elems, i)
    return (Ordinal(r[0]), r[1]) if r else None


ORDINAL = TypeFormule(
    "ordinal", re.compile(r"(?P<rang>\d{1,3}(?:,\d{3})+|\d+)(?P<suffixe>st|nd|rd|th|ST|ND|RD|TH)(?![\w])"),
    _construire_ordinal, _lire_ordinal, _reconnaitre_ordinal, lambda v: f"{grouper_milliers(str(v.rang))}{_suffixe_ordinal(v.rang)}",
)

# ── Pourcentage ────────────────────────────────────────────────────────────────


def _lire_pourcentage(m: re.Match[str]) -> list[MotLu]:
    mots = _lire_nombre(m)
    if m.group("n2"):
        mots += [MotLu("to", m.end("nombre"), m.start("n2"))] + lire_nombre_aligne(m.group("n2"), m.start("n2"))
    return mots + [MotLu("percent", m.start("symbole"), m.end("symbole"), composant=1)]


def _reconnaitre_pourcentage(elems: list[str], i: int) -> tuple[Pourcentage, int] | None:
    r = reconnaitre_nombre(elems, i)
    if r is None:
        return None
    v, j = r
    jusqua = None
    if elems[j : j + 1] == ["to"] and (r2 := reconnaitre_nombre(elems, j + 1, signe=False)):
        jusqua, k = r2
        if elems[k : k + 1] == ["percent"]:
            return Pourcentage(v, jusqua=jusqua), k + 1
    if elems[j : j + 1] == ["percent"]:
        return Pourcentage(v), j + 1
    if elems[j : j + 2] == ["per", "cent"]:
        return Pourcentage(v), j + 2
    return None


POURCENTAGE = TypeFormule(
    "pourcentage", re.compile(rf"(?P<signe>{_SIGNE})?(?P<nombre>{_NOMBRE})(?:\s?[–-]\s?(?P<n2>{_NOMBRE}))?\s?(?P<symbole>%)"),
    lambda m: Pourcentage(_construire_nombre(m), jusqua=Nombre(*_decouper(m.group("n2"))) if m.group("n2") else None),
    _lire_pourcentage, _reconnaitre_pourcentage,
    lambda v: ecrire_nombre(v.nombre) + (("–" + ecrire_nombre(v.jusqua)) if v.jusqua else "") + "%",
)

# ── Heure ──────────────────────────────────────────────────────────────────────


def _ampm(nom: str) -> str:
    return rf"(?:\s?(?P<{nom}>[aApP])\.?\s?[mM]\.?(?![\w]))"


def _construire_heure(m: re.Match[str]) -> Heure | None:
    h = int(m.group("h") or m.group("h2"))
    mi = m.group("mi")
    ap = (m.group("ap") or m.group("ap2") or "").lower()
    if ap and not 1 <= h <= 12:
        return None
    if m.group("se") and not ap and len(m.group("h")) < 2:
        return None                        # « 2:03:45 » : une durée ; « 12:42:55 », « 06:00:56 » : un horodatage
    return Heure(h, int(mi) if mi is not None else None, ap, int(m.group("se")) if m.group("se") else None)


def _lire_heure(m: re.Match[str]) -> list[MotLu]:
    v = _construire_heure(m)
    g_h = "h" if m.group("h") else "h2"
    mots = _bloc(ecrire_entier(v.heures), m.start(g_h), m.end(g_h))
    if v.minutes is not None:
        debut, fin = m.start("mi"), m.end("mi")
        if v.minutes == 0:
            if v.meridien:
                pass
            elif v.heures == 0:
                mots = [MotLu("midnight", m.start(), fin)]
            elif v.heures > 12:
                mots.append(MotLu("hundred", debut, fin, composant=1))
            else:
                mots.append(MotLu("o'clock", debut, fin, composant=1))
        else:
            mots += _bloc(([OH] if v.minutes < 10 else []) + ecrire_entier(v.minutes), debut, fin, 1)
    if v.secondes is not None:             # 11:15:11 AM : eleven fifteen and eleven seconds a m
        debut, fin = m.start("se"), m.end("se")
        if v.minutes == 0:                 # 6:00:56 AM : six oh oh and fifty six seconds a m
            mots.append(MotLu(OH, m.start("mi"), m.end("mi"), composant=1))
            mots.append(MotLu(OH, m.start("mi"), m.end("mi"), composant=1))
        mots += [MotLu("and", debut - 1, debut, composant=3)] + _bloc(ecrire_entier(v.secondes), debut, fin, 3) \
            + [MotLu("second" if v.secondes == 1 else "seconds", debut, fin, composant=3)]
    if v.meridien:
        g = "ap" if m.group("ap") else "ap2"
        debut = m.start(g)
        mots += [MotLu(v.meridien, debut, debut + 1, composant=2, nature="lettre"),
                 MotLu("m", debut + 1, m.end(), composant=2, nature="lettre")]
    return mots


# Un nombre dit n'est une heure qu'après un mot qui introduit un moment, ou suivi de « o'clock », « a m », « p m ».
_AVANT_HEURE = frozenset("at by until till til from before after around about since between to past for @ - –".split())


def _reconnaitre_heure(elems: list[str], i: int) -> tuple[Heure, int] | None:
    h = plus_long_entier(elems, i, maximum=24)
    if h is None or elems[i] in ("a",):
        return None
    heures, j = h
    minutes, meridien = None, ""
    if elems[j : j + 1] == ["o'clock"] and 1 <= heures <= 12:
        minutes, j = 0, j + 1
    elif elems[j : j + 1] == ["hundred"] and 13 <= heures <= 24 and j - i == 1:
        minutes, j = 0, j + 1
    elif j < len(elems):
        if elems[j : j + 2] == [OH, OH] and elems[j + 2 : j + 3] == ["and"]:
            minutes, j = 0, j + 2
        elif elems[j] == OH and j + 1 < len(elems) and elems[j + 1] in UNITES[1:10]:
            minutes, j = UNITES.index(elems[j + 1]), j + 2
        else:
            mi = plus_long_entier(elems, j, maximum=59)
            if mi and mi[0] >= 10:
                minutes, j = mi
    secondes = None
    if minutes is not None and elems[j : j + 1] == ["and"]:
        s = plus_long_entier(elems, j + 1, maximum=59)
        if s and elems[s[1] : s[1] + 1] in (["second"], ["seconds"]) and (s[0] == 1) == (elems[s[1]] == "second"):
            secondes, j = s[0], s[1] + 1
    if elems[j : j + 2] in (["a", "m"], ["p", "m"]) and 1 <= heures <= 12:
        meridien, j = elems[j], j + 2
    if not meridien and minutes is None:
        return None
    dite = elems[j - 1] == "o'clock"
    if not meridien and not dite and ((i == 0 or elems[i - 1] not in _AVANT_HEURE)
                                      or not (1 <= heures <= 12 or elems[j - 1] == "hundred")):
        return None                        # « nineteen forty eight » : une année ; « at seven thirty » : une heure
    if secondes is not None and not meridien and heures < 10:
        return None
    if heures > 23 or (minutes is not None and heures == 24 and minutes):
        return None
    return Heure(heures, minutes, meridien, secondes), j


def ecrire_heure(v: Heure) -> str:
    texte = f"{v.heures}:{v.minutes:02d}" if v.minutes is not None else str(v.heures)
    if v.secondes is not None:
        texte += f":{v.secondes:02d}"
    return texte + (f" {v.meridien}.m." if v.meridien else "")


HEURE = TypeFormule(
    "heure",
    re.compile(rf"(?:(?P<h>[01]?\d|2[0-3]):(?P<mi>[0-5]\d)(?::(?P<se>[0-5]\d))?{_ampm('ap')}?(?![\d:])(?![.,]\d)|(?P<h2>1[0-2]|0?[1-9]){_ampm('ap2')})"),
    _construire_heure, _lire_heure, _reconnaitre_heure, ecrire_heure,
)

# ── Date : années, décennies ───────────────────────────────────────────────────


def _construire_date(m: re.Match[str]) -> Date | None:
    if m.group("decennie"):
        return Date(0, 0, int(m.group("decennie")), decennie=True)
    if m.group("dec2"):
        return Date(0, 0, int(m.group("dec2")), decennie=True, courte=True)
    if m.group("dec3"):
        return Date(0, 0, int(m.group("dec3")), decennie=True)
    if m.group("an2"):
        return Date(0, 0, int(m.group("an2")), courte=True)
    n = int(m.group("annee"))
    return Date(0, 0, n) if est_annee_par_paires(n) or 2000 <= n <= 2009 else None


def _decennie(mots: list[MotLu]) -> list[MotLu]:
    dernier = mots[-1]
    return mots[:-1] + [replace(dernier, texte=pluriel_decennie(dernier.texte), elements=())]


def pluriel_decennie(mot: str) -> str:
    return mot[:-1] + "ies" if mot.endswith("y") else mot + "s"


def _lire_date(m: re.Match[str]) -> list[MotLu]:
    if m.group("decennie"):
        g = "decennie"
        mots = lire_annee(m.group(g), list(range(m.start(g), m.end(g))))
        mots = mots[:-1] + [MotLu(mots[-1].texte, mots[-1].debut, m.end())]
        return _decennie(mots)
    if m.group("dec3"):          # 20s → twenties (âge, décennie sans siècle)
        return _decennie([MotLu(ecrire_entier(int(m.group("dec3")))[0], m.start(), m.end())])
    if m.group("dec2"):          # '90s → nineties
        n = int(m.group("dec2"))
        mots = [MotLu(UNITES[n] if n < 20 else ecrire_entier(n)[0], m.start(), m.end())] if n else [MotLu("hundred", m.start(), m.end())]
        return _decennie(mots) if n else [MotLu("two", m.start(), m.end()), MotLu("thousands", m.start(), m.end())]
    if m.group("an2"):           # '05 → oh five ; '99 → ninety nine
        n = int(m.group("an2"))
        mots = ([OH, UNITES[n]] if n < 10 else ecrire_entier(n))
        return _bloc(mots, m.start(), m.end())
    g = "annee"
    return lire_annee(m.group(g), list(range(m.start(g), m.end(g))))


def _reconnaitre_date(elems: list[str], i: int) -> tuple[Date, int] | None:
    mois = _reconnaitre_date_mois(elems, i)
    if mois:
        return mois
    # Décennie : « nineteen nineties », « eighteen hundreds », « two thousands »
    for j in range(i + 1, min(i + 4, len(elems)) + 1):
        dernier = elems[j - 1]
        singulier = dernier[:-3] + "y" if dernier.endswith("ies") else dernier[:-1] if dernier.endswith("s") else None
        if not singulier or singulier not in ELEMENTS:
            continue
        essai = elems[i : j - 1] + [singulier]
        a = plus_longue_annee(essai, 0)
        if a and a[1] == len(essai) and a[0] % 10 == 0:
            return Date(0, 0, a[0], decennie=True), j
        if essai == ["two", "thousand"]:
            return Date(0, 0, 2000, decennie=True), j
    a = plus_longue_annee(elems, i)
    if a:
        return Date(0, 0, a[0]), a[1]
    return None


def ecrire_date(v: Date) -> str:
    if v.mois:
        return ecrire_date_mois(v)
    if v.courte:
        return f"'{v.annee:02d}" + ("s" if v.decennie else "")
    return f"{v.annee}" + ("s" if v.decennie else "")


DATE = TypeFormule(
    "date",
    re.compile(r"(?:(?P<decennie>1\d\d0|20\d0)['’]?s(?![\w])|(?<![\d.,])(?P<dec3>[1-9]0)['’]?s(?![\w])|['’](?P<dec2>\d0)s(?![\w])|['’](?P<an2>\d\d)(?![\w'’\"″])"
               r"|(?P<annee>1\d\d\d|20\d\d)(?!\d)(?![.,]\d))"),
    _construire_date, _lire_date, _reconnaitre_date, ecrire_date,
)

# ── Monnaie ────────────────────────────────────────────────────────────────────

# symbole → (code, singulier, pluriel, centime singulier, centime pluriel)
DEVISES = {"$": ("USD", "dollar", "dollars", "cent", "cents"), "US$": ("USD", "dollar", "dollars", "cent", "cents"),
           "£": ("GBP", "pound", "pounds", "penny", "pence"), "€": ("EUR", "euro", "euros", "cent", "cents"),
           "¥": ("JPY", "yen", "yen", "", ""), "₹": ("INR", "rupee", "rupees", "paisa", "paise")}
_SYMBOLE_DE = {"USD": "$", "GBP": "£", "EUR": "€", "JPY": "¥", "INR": "₹"}
# Noms de devise reconnus en sens inverse (« pounds » est aussi une masse : non reconnu).
_DEVISE_DU_MOT = {"dollar": "USD", "dollars": "USD", "euro": "EUR", "euros": "EUR", "yen": "JPY", "rupees": "INR",
                  "rupee": "INR"}
_ECHELLES = {"thousand": "thousand", "million": "million", "billion": "billion", "trillion": "trillion",
             "k": "thousand", "K": "thousand", "m": "million", "M": "million", "mn": "million", "bn": "billion",
             "B": "billion", "b": "billion", "tn": "trillion", "T": "trillion"}
_MOTIF_ECHELLE = "|".join(sorted(_ECHELLES, key=len, reverse=True))


def _construire_monnaie(m: re.Match[str]) -> Monnaie | None:
    if m.group("cents"):
        return Monnaie(Nombre("0", m.group("cents").zfill(2)), "USD") if len(m.group("cents")) <= 2 else None
    entier, dec = _decouper(m.group("montant"))
    echelle = _ECHELLES[m.group("echelle")] if m.group("echelle") else ""
    return Monnaie(Nombre(entier, dec, bool(m.group("signe"))), DEVISES[m.group("devise")][0], echelle)


def _lire_monnaie(m: re.Match[str]) -> list[MotLu]:
    v = _construire_monnaie(m)
    if m.group("cents"):
        n = int(m.group("cents"))
        return lire_chiffres(m.group("cents"), debut=m.start("cents")) + \
            [MotLu("cent" if n == 1 else "cents", m.end("cents"), m.end(), composant=1)]
    code, sing, plur, csing, cplur = DEVISES[m.group("devise")]
    symbole = (m.start("devise"), m.end("devise"))
    mots = [MotLu(MOINS, m.start("signe"), m.end("signe"))] if v.montant.negatif else []
    texte, debut = m.group("montant"), m.start("montant")
    entier, places_e, dec, places_d, point = _chiffres(texte, debut)
    if v.echelle:
        mots += lire_nombre_aligne(texte, debut)
        mots.append(MotLu(v.echelle, m.start("echelle"), m.end("echelle")))
        return mots + [MotLu(plur, *symbole, composant=1)]
    n = int(entier)
    if dec and (len(dec) != 2 or not csing):
        return mots + lire_nombre_aligne(texte, debut) + [MotLu(plur, *symbole, composant=1)]
    c = int(dec) if dec else 0
    # $3.50 three dollars fifty ; $3.05 three dollars and five cents ; $0.50 fifty cents
    dire_cents = not n or c < 10
    if n or not c:
        mots += lire_chiffres(entier, places_e) + [MotLu(sing if n == 1 else plur, *symbole, composant=1)]
        if c and dire_cents:
            mots.append(MotLu("and", point, point + 1, composant=2))
    if c:
        mots += _composant(lire_chiffres(dec.lstrip("0") or "0", places_d[len(dec) - len(dec.lstrip("0")):]), 2)
        if dire_cents:
            mots.append(MotLu(csing if c == 1 else cplur, places_d[0], places_d[-1] + 1, composant=2))
    return mots


def _reconnaitre_monnaie(elems: list[str], i: int) -> tuple[Monnaie, int] | None:
    r = reconnaitre_nombre(elems, i)
    if r is None:
        return None
    # « five million dollars » → $5 million (échelle gardée en lettres)
    for s in range(i + 1, min(len(elems) - 1, i + 12)):
        if elems[s] in ("million", "billion", "trillion") and elems[s + 1] in _DEVISE_DU_MOT:
            avant = reconnaitre_nombre(elems[:s], i)
            if avant and avant[1] == s:
                return Monnaie(avant[0], _DEVISE_DU_MOT[elems[s + 1]], elems[s]), s + 2
            break
        if elems[s] not in ELEMENTS and elems[s] not in ("point", "and", "minus"):
            break
    v, j = r
    if j >= len(elems):
        return None
    if elems[j] in ("cent", "cents") and not v.decimales and not v.negatif and int(v.entier) < 100:
        if (int(v.entier) == 1) != (elems[j] == "cent"):
            return None
        return Monnaie(Nombre("0", f"{int(v.entier):02d}"), "USD"), j + 1
    echelle = ""
    if elems[j] in ("thousand", "million", "billion", "trillion") and j + 1 < len(elems) and elems[j + 1] in _DEVISE_DU_MOT:
        echelle, j = elems[j], j + 1
    devise = _DEVISE_DU_MOT.get(elems[j])
    if devise is None:
        return None
    j += 1
    if echelle or v.decimales:
        return Monnaie(v, devise, echelle), j
    # « three dollars and fifty cents », « three dollars fifty »
    k = j + 1 if elems[j : j + 1] == ["and"] else j
    centimes = plus_long_entier(elems, k, maximum=99) if k < len(elems) else None
    if centimes and centimes[0] and devise != "JPY":
        fin = centimes[1]
        if elems[fin : fin + 1] in (["cent"], ["cents"]):
            fin += 1
        elif k != j or centimes[0] < 10 or (fin < len(elems) and (elems[fin] in _DEVISE_DU_MOT or elems[fin] in ELEMENTS)):
            return Monnaie(v, devise), j       # « and fifty » sans « cents », « six dollars one dollar » : on n'y touche pas
        return Monnaie(replace(v, decimales=f"{centimes[0]:02d}"), devise), fin
    return Monnaie(v, devise), j


def ecrire_monnaie(v: Monnaie) -> str:
    signe = "-" if v.montant.negatif else ""
    return signe + _SYMBOLE_DE[v.devise] + ecrire_nombre(replace(v.montant, negatif=False)) + (f" {v.echelle}" if v.echelle else "")


MONNAIE = TypeFormule(
    "monnaie",
    re.compile(rf"(?:(?P<signe>{_SIGNE})?(?P<devise>US\$|[$£€¥₹])\s?(?P<montant>{_NOMBRE}){_FIN}"
               rf"(?:\s?(?P<echelle>{_MOTIF_ECHELLE})(?![\w]))?|(?P<cents>\d{{1,3}})\s?¢)"),
    _construire_monnaie, _lire_monnaie, _reconnaitre_monnaie, ecrire_monnaie,
)

# ── Date avec mois : « April 8, 2020 », « 8 April 2020 », « 2020-04-08 », « 4/8/2020 » ─────────────────────────────

MOIS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"]
_ABREGES_EN = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Sept": 9, "Oct": 10,
               "Nov": 11, "Dec": 12}
_MOIS_ECRITS = {**{m: k for k, m in enumerate(MOIS_EN, 1)}, **_ABREGES_EN}
_MOTIF_MOIS_EN = "|".join(sorted((re.escape(m) for m in _MOIS_ECRITS), key=len, reverse=True))
_JOUR = r"(?:[12]\d|3[01]|0?[1-9])(?:st|nd|rd|th)?"
_AN = r"1\d\d\d|20\d\d"
_MOIS_DITS = {m.lower(): k for k, m in enumerate(MOIS_EN, 1)}


def _groupe(m: re.Match[str], *noms: str) -> str | None:
    return next((g for g in noms if m.group(g)), None)


def _construire_date_mois(m: re.Match[str]) -> Date | None:
    if m.group("iso_a"):
        mo, j = int(m.group("iso_m")), int(m.group("iso_j"))
        return Date(j, mo, int(m.group("iso_a"))) if 1 <= mo <= 12 and 1 <= j <= 31 else None
    if m.group("eu_a"):
        mo, j = int(m.group("eu_m")), int(m.group("eu_j"))
        return Date(j, mo, int(m.group("eu_a")))
    if m.group("us_a"):
        mo, j = int(m.group("us_m")), int(m.group("us_j"))
        return Date(j, mo, int(m.group("us_a"))) if 1 <= mo <= 12 and 1 <= j <= 31 else None
    jour = _groupe(m, "j1", "j2")
    an = _groupe(m, "a1", "a2", "a3")
    if not jour and not an:
        return None
    j = int(re.match(r"\d+", m.group(jour)).group()) if jour else 0
    suffixe = m.group(jour)[len(str(j)) + (m.group(jour).startswith("0")):] if jour else ""
    if suffixe and suffixe != _suffixe_ordinal(j):
        return None
    mois = _MOIS_ECRITS[m.group(_groupe(m, "m1", "m2"))]
    g_fin = _groupe(m, "j1b", "j2b")
    jour_fin = int(re.match(r"\d+", m.group(g_fin)).group()) if g_fin else 0
    if g_fin and jour_fin <= j:
        return None
    return Date(j, mois, int(m.group(an)) if an else None, jour_fin=jour_fin, jour_dabord=bool(m.group("j2")))


def lire_jour(jour: int, debut: int, fin: int, composant: int = 0) -> list[MotLu]:
    return _bloc(ordinal(ecrire_entier(jour)), debut, fin, composant)


def _lire_date_mois(m: re.Match[str]) -> list[MotLu]:
    v = _construire_date_mois(m)
    if m.group("iso_a") or m.group("us_a") or m.group("eu_a"):
        p = "iso_" if m.group("iso_a") else "us_" if m.group("us_a") else "eu_"
        mots = [MotLu(MOIS_EN[v.mois - 1], m.start(p + "m"), m.end(p + "m"), composant=1)]
        mots += lire_jour(v.jour, m.start(p + "j"), m.end(p + "j"))
        g = p + "a"
        return mots + _composant(lire_annee(m.group(g), list(range(m.start(g), m.end(g)))), 2)
    g_mois = _groupe(m, "m1", "m2")
    g_jour = _groupe(m, "j1", "j2")
    g_an = _groupe(m, "a1", "a2", "a3")
    if v.jour_dabord:
        # « 5 March 2020 » : the fifth of March twenty twenty (ordre de l'écrit, validé le 12/10)
        mots = [MotLu("the", m.start("j2"), m.end("j2"))] + lire_jour(v.jour, m.start("j2"), m.end("j2"))
        if m.group("j2b"):
            mots += [MotLu("to", m.end("j2"), m.start("j2b"), composant=3), MotLu("the", m.start("j2b"), m.end("j2b"), composant=3)]
            mots += lire_jour(v.jour_fin, m.start("j2b"), m.end("j2b"), 3)
        mots += [MotLu("of", m.start("m2"), m.end("m2"), composant=1), MotLu(MOIS_EN[v.mois - 1], m.start("m2"), m.end("m2"), composant=1)]
        if g_an:
            mots += _composant(lire_annee(m.group(g_an), list(range(m.start(g_an), m.end(g_an)))), 2)
        return mots
    mots = [MotLu(MOIS_EN[v.mois - 1], m.start(g_mois), m.end(g_mois), composant=1)]
    if g_jour:
        mots += lire_jour(v.jour, m.start(g_jour), m.end(g_jour))
    g_fin = _groupe(m, "j1b", "j2b")
    if g_fin:
        mots.append(MotLu("to", m.end(g_jour), m.start(g_fin), composant=3))
        mots += lire_jour(v.jour_fin, m.start(g_fin), m.end(g_fin), 3)
    if g_an:
        mots += _composant(lire_annee(m.group(g_an), list(range(m.start(g_an), m.end(g_an)))), 2)
    return mots


def _reconnaitre_date_mois(elems: list[str], i: int) -> tuple[Date, int] | None:
    """« March fifth twenty twenty », « March fifth », « March twenty twenty », « the fifth of March ». »"""
    if elems[i] in _MOIS_DITS:
        mois, j = _MOIS_DITS[elems[i]], i + 1
        jour = 0
        o = plus_long_ordinal(elems, j)
        jour_fin = 0
        if o and 1 <= o[0] <= 31:
            jour, j = o
            if elems[j : j + 1] == ["to"] and (o2 := plus_long_ordinal(elems, j + 1)) and jour < o2[0] <= 31:
                jour_fin, j = o2
        a = _annee_avant_heure(elems, j)
        if a:
            return Date(jour, mois, a[0], jour_fin=jour_fin), a[1]
        if jour:
            return Date(jour, mois, jour_fin=jour_fin), j
        return None
    if elems[i] == "the":
        o = plus_long_ordinal(elems, i + 1)
        jour_fin, k = 0, o[1] if o else 0
        if o and elems[k : k + 2] == ["to", "the"] and (o2 := plus_long_ordinal(elems, k + 2)) and o[0] < o2[0] <= 31:
            jour_fin, k = o2
        if o and 1 <= o[0] <= 31 and elems[k : k + 1] == ["of"] and k + 1 < len(elems) and elems[k + 1] in _MOIS_DITS:
            j = k + 2
            a = _annee_avant_heure(elems, j)
            v = Date(o[0], _MOIS_DITS[elems[k + 1]], a[0] if a else None, jour_fin=jour_fin, jour_dabord=True)
            return v, (a[1] if a else j)
    return None


def _annee_avant_heure(elems: list[str], j: int) -> tuple[int, int] | None:
    """Année d'une date ; si elle mange le début d'une heure qui suit (« two thousand four eighteen p m »), l'année
    la plus courte qui laisse l'heure entière (two thousand | four eighteen p m)."""
    a = annee_dite(elems, j)
    if a is None or _reconnaitre_heure(elems, a[1]) is not None:
        return a
    for k in range(a[1] - 1, j, -1):
        court = annee_dite(elems[:k], j)
        h = _reconnaitre_heure(elems, k) if court and court[1] == k else None
        if h and (h[0].meridien or h[0].secondes is not None):
            return court
    return a


def ecrire_date_mois(v: Date) -> str:
    if v.jour_dabord and v.jour:
        return f"{v.jour}" + (f"–{v.jour_fin}" if v.jour_fin else "") + f" {MOIS_EN[v.mois - 1]}" + \
            (f" {v.annee}" if v.annee is not None else "")
    texte = MOIS_EN[v.mois - 1] + (f" {v.jour}" if v.jour else "") + (f"–{v.jour_fin}" if v.jour_fin else "")
    if v.annee is not None:
        texte += (", " if v.jour else " ") + str(v.annee)
    return texte


DATE_MOIS = TypeFormule(
    "date",
    re.compile(rf"(?:(?P<m1>{_MOTIF_MOIS_EN})\.?\s(?:(?P<j1>{_JOUR})(?:\s?[–-]\s?(?P<j1b>{_JOUR}))?(?![\d\w:])(?:,?\s(?P<a1>{_AN}))?|(?P<a2>{_AN}))"
               rf"|(?P<j2>{_JOUR})(?:\s?[–-]\s?(?P<j2b>{_JOUR}))?\s(?P<m2>{_MOTIF_MOIS_EN})\.?(?:,?\s(?P<a3>{_AN}))?"
               rf"|(?P<iso_a>{_AN})-(?P<iso_m>[01]\d)-(?P<iso_j>[0-3]\d)"
               rf"|(?P<us_m>1[0-2]|0?[1-9])/(?P<us_j>[12]\d|3[01]|0?[1-9])/(?P<us_a>{_AN})"
               rf"|(?P<eu_j>1[3-9]|2\d|3[01])/(?P<eu_m>1[0-2]|0?[1-9])/(?P<eu_a>{_AN}))(?![\d\w])"),
    _construire_date_mois, _lire_date_mois, _a_porter, ecrire_date_mois,
)
