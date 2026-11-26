# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Autres types de formules anglais : téléphone, fraction, mesure, angle, plage, version, nombre romain, sigle, durée,
intervalle.

Lectures (américain usuel) : (555) 123-4567 chiffre à chiffre ; 3/4 three quarters, 2 1/2 two and a half, 3/8 three
eighths, 24/7 twenty four seven ; 10 km ten kilometers, 5 m five meters (unité d'une lettre : m g s V W L), 5'10"
five foot ten, -5 °C minus five degrees Celsius, 5–10 km five to ten kilometers ; 40°42′N forty degrees forty two
minutes north ; 1990–95 nineteen ninety to ninety five, 3–1 three to one ; v2.0 version two point oh,
192.168.1.1 one ninety two dot one sixty eight dot one dot one ; 2:03:45 two hours three minutes forty five
seconds ; [0, 1] from zero to one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from functools import cache

from ..abregements import table as table_abregements
from .nombres import OH, UNITES, ZERO, Element, MotLu, ecrire_entier, elements, lire_annee, lire_chiffres, \
    lire_paires, ordinal, ordinal_mot, plus_long_entier, plus_longue_annee, annee_dite
from .types import (
    _FIN,
    _JAMAIS,
    _NOMBRE,
    _SIGNE,
    CHIFFRES_DITS,
    Nombre,
    TypeFormule,
    _a_porter,
    _bloc,
    _chiffres,
    _composant,
    _construire_nombre,
    _decouper,
    ecrire_nombre,
    lire_nombre,
    lire_nombre_aligne,
    reconnaitre_nombre,
)

LETTRE = "lettre"


@dataclass(frozen=True)
class Telephone:
    numero: str
    indicatif: str = ""        # « 1 » pour +1 ou 1-800, « 44 » pour +44
    plus: bool = False


@dataclass(frozen=True)
class Fraction:
    numerateur: int
    denominateur: int
    negatif: bool = False
    entier: int = 0            # nombre fractionnaire : 2 1/2
    unicode: bool = False      # ½


@dataclass(frozen=True)
class Mesure:
    nombre: Nombre
    unite: str
    jusqua: Nombre | None = None     # plage : 5–10 km
    complement: Nombre | None = None  # pouces de 5'10"


@dataclass(frozen=True)
class Angle:
    degres: Nombre
    minutes: Nombre | None = None
    secondes: Nombre | None = None
    direction: str = ""


@dataclass(frozen=True)
class Romain:
    valeur: int
    ordinal: bool = False


@dataclass(frozen=True)
class Sigle:
    lettres: str


@dataclass(frozen=True)
class Duree:
    heures: int | None = None
    minutes: int | None = None
    secondes: int | None = None
    fraction: str = ""          # décimales des secondes (3:43.13)


@dataclass(frozen=True)
class Plage:
    debut: str
    fin: str
    signe: str = "–"           # « : » pour un rapport (16:9)


@dataclass(frozen=True)
class Intervalle:
    gauche: str
    droite: str
    ouvert_gauche: bool = False
    ouvert_droite: bool = False


@dataclass(frozen=True)
class Version:
    parties: tuple[str, ...]
    prefixe: bool = True       # « v2.0 »
    ip: bool = False           # adresse IP : « dot »


def _verifie(t: TypeFormule, valeur, elems: list[str]) -> bool:
    """La valeur se relit-elle exactement avec ces éléments ?"""
    m = t.motif.match(t.ecrire(valeur))
    if m is None or t.construire(m) is None:
        return False
    return elements([mot.texte for mot in t.lire(m)]) == elems


# ── Téléphone : chiffre à chiffre, un composant par groupe ─────────────────────


def _construire_telephone(m: re.Match[str]) -> Telephone | None:
    if m.group("intl") and not m.group("plus"):
        return None
    return Telephone(re.sub(r"\D", "", m.group("numero")), m.group("indicatif") or m.group("indicatif_") or "",
                     bool(m.group("plus")))


def _lire_telephone(m: re.Match[str]) -> list[MotLu]:
    res, groupe = [], 0
    if m.group("plus"):
        res.append(MotLu("plus", m.start("plus"), m.end("plus")))
    g_ind = "indicatif" if m.group("indicatif") else "indicatif_" if m.group("indicatif_") else None
    if g_ind:
        res += [MotLu(UNITES[int(c)], m.start(g_ind) + k, m.start(g_ind) + k + 1) for k, c in enumerate(m.group(g_ind))]
        groupe = 1
    debut = m.start("numero")
    for k, c in enumerate(m.group("numero")):
        if c.isdigit():
            res.append(MotLu(UNITES[int(c)], debut + k, debut + k + 1, composant=groupe))
        elif res and res[-1].composant == groupe:
            groupe += 1
    # numéro vert : 1-800-… se dit « one eight hundred »
    chiffres = [x for x in res if x.composant == (1 if g_ind else 0)]
    if g_ind and len(re.sub(r"\D", "", m.group("numero"))) == 10 and "".join(
            str(UNITES.index(x.texte)) for x in chiffres[:3]) == "800":
        k = res.index(chiffres[0])
        res[k : k + 3] = [MotLu("eight", chiffres[0].debut, chiffres[2].fin, composant=chiffres[0].composant),
                          MotLu("hundred", chiffres[0].debut, chiffres[2].fin, composant=chiffres[0].composant)]
    return res


def _reconnaitre_telephone(elems: list[str], i: int) -> tuple[Telephone, int] | None:
    j, indicatif, plus = i, "", False
    if elems[j] == "plus":
        plus, j = True, j + 1
    if elems[j : j + 3] == ["one", "eight", "hundred"]:          # « one eight hundred » : 1-800
        k = j + 3
        while k < len(elems) and elems[k] in CHIFFRES_DITS:
            k += 1
        if k - j - 3 == 7:
            valeur = Telephone("800" + "".join(CHIFFRES_DITS[e] for e in elems[j + 3 : k]), "1", plus)
            return (valeur, k) if _verifie(TELEPHONE, valeur, elems[i:k]) else None
        return None
    k = j
    while k < len(elems) and elems[k] in CHIFFRES_DITS:
        k += 1
    n = k - j
    if plus:
        if n == 11 and elems[j] == "one":
            indicatif, j, n = "1", j + 1, 10
        elif 8 <= n <= 15:                 # international : « plus » et les chiffres
            return Telephone("".join(CHIFFRES_DITS[e] for e in elems[j:k]), "", True), k
        else:
            return None
    elif n == 11 and elems[j] == "one":
        indicatif, j, n = "1", j + 1, 10
    elif n not in (7, 10):
        # deux numéros dits à la suite : le premier fait dix (ou sept) chiffres
        n = 10 if n - 10 in (7, 10, 11) else 7 if n - 7 in (7, 10, 11) else 0
    if n not in (7, 10) or (indicatif and n != 10):
        return None
    return Telephone("".join(CHIFFRES_DITS[e] for e in elems[j : j + n]), indicatif, plus), j + n


def ecrire_telephone(v: Telephone) -> str:
    c = v.numero
    texte = f"{c[:3]}-{c[3:6]}-{c[6:]}" if len(c) == 10 else f"{c[:3]}-{c[3:]}" if len(c) == 7 else c
    if v.plus and not v.indicatif:
        return "+" + c
    if v.plus:
        return f"+{v.indicatif} {texte}"
    return f"{v.indicatif}-{texte}" if v.indicatif else texte


TELEPHONE = TypeFormule(
    "telephone",
    re.compile(r"(?<![\d-])(?:(?P<plus>\+)(?P<indicatif>1|[2-9]\d{0,2})[\s.-]?|(?P<indicatif_>1)-(?=\d{3}-))?"
               r"(?P<numero>(?:\(\d{3}\)\s?|\d{3}[-.])\d{3}[-.]\d{4}(?![\d-])|\d{3}-\d{4}(?![\d-])"
               r"|(?P<intl>(?:\d{1,4}[\s.-]){1,4}\d{2,4}(?![\d-])))"),
    _construire_telephone, _lire_telephone, _reconnaitre_telephone, ecrire_telephone,
)

# ── Fraction ───────────────────────────────────────────────────────────────────

_NOMS_FRACTION = {2: ("half", "halves"), 4: ("quarter", "quarters")}
_DENOMINATEURS_ORDINAUX = frozenset(range(3, 11)) | {12, 16, 20, 32, 64, 100, 1000}
_FRACTIONS_UNICODE = {"½": (1, 2), "⅓": (1, 3), "⅔": (2, 3), "¼": (1, 4), "¾": (3, 4), "⅕": (1, 5), "⅖": (2, 5),
                      "⅗": (3, 5), "⅘": (4, 5), "⅙": (1, 6), "⅚": (5, 6), "⅛": (1, 8), "⅜": (3, 8), "⅝": (5, 8),
                      "⅞": (7, 8)}
_UNICODE_DE = {v: k for k, v in _FRACTIONS_UNICODE.items()}
# Fractions qui n'en sont pas : lues nombre par nombre (« 24/7 », « 9/11 », « 50/50 »).
_LUES_NOMBRE_A_NOMBRE = frozenset({(24, 7), (9, 11), (50, 50), (20, 20), (7, 11)})
_DENOMINATEUR_DU_MOT = {}
for _d in _DENOMINATEURS_ORDINAUX | set(_NOMS_FRACTION):
    for _k, _nom in enumerate(_NOMS_FRACTION.get(_d) or (ordinal(ecrire_entier(_d))[-1], ordinal(ecrire_entier(_d))[-1] + "s")):
        _DENOMINATEUR_DU_MOT.setdefault(_nom, _d)
_DENOMINATEUR_DU_MOT.update({"fourth": 4, "fourths": 4})


def _construire_fraction(m: re.Match[str]) -> Fraction | None:
    entier = int(m.group("entier") or m.group("entier2") or 0)
    if m.group("u"):
        a, b = _FRACTIONS_UNICODE[m.group("u")]
        return Fraction(a, b, bool(m.group("signe")), entier, True)
    a, b = int(m.group("a")), int(m.group("b"))
    if b < 2 or a == 0 or (entier and a >= b) or m.group("b").startswith("0"):
        return None                        # « 3/03 » : une date (mois / année), pas une fraction
    return Fraction(a, b, bool(m.group("signe")), entier)


def _nom_denominateur(a: int, b: int) -> list[str] | None:
    if b in _NOMS_FRACTION:
        return [_NOMS_FRACTION[b][a > 1]]
    if b not in _DENOMINATEURS_ORDINAUX:
        return None
    mots = ordinal(ecrire_entier(b))
    if b >= 100 and mots[0] == "one":
        mots = mots[1:]                    # « hundredth » : one hundredth, three hundredths
    return mots[:-1] + [mots[-1] + ("s" if a > 1 else "")]


def _lire_fraction(m: re.Match[str]) -> list[MotLu]:
    v = _construire_fraction(m)
    mots = [MotLu("minus", m.start("signe"), m.end("signe"))] if v.negatif else []
    g_entier = "entier" if m.group("entier") else "entier2" if m.group("entier2") else None
    comp = 0
    if m.group("u"):
        da = db = m.start("u")
        fa = fb = m.end("u")
    else:
        da, fa, db, fb = m.start("a"), m.end("a"), m.start("b"), m.end("b")
    if g_entier:
        mots += lire_chiffres(m.group(g_entier), debut=m.start(g_entier))
        mots.append(MotLu("and", m.end(g_entier), da, composant=1))
        comp = 1
    a, b = v.numerateur, v.denominateur
    nom = _nom_denominateur(a, b)
    if g_entier and a == 1 and b in (2, 3, 4):
        numerateur = [MotLu("a", da, fa, composant=comp)]
    elif m.group("u"):
        numerateur = _bloc(ecrire_entier(a), da, fa, comp)
    else:
        numerateur = _composant(lire_chiffres(str(a), debut=da), comp)
    if (a, b) in _LUES_NOMBRE_A_NOMBRE and not g_entier:
        return mots + numerateur + _composant(lire_chiffres(str(b), debut=db), comp + 1)
    if nom is None or a >= b:
        return (mots + numerateur + [MotLu("over", fa, db, composant=comp + 1)]
                + _composant(lire_chiffres(str(b), debut=db), comp + 1))
    return mots + numerateur + _bloc(nom, db - (not m.group("u")), fb, comp + 1)


def _reconnaitre_fraction(elems: list[str], i: int) -> tuple[Fraction, int] | None:
    negatif = elems[i] == "minus"
    j = i + 1 if negatif else i
    num = plus_long_entier(elems, j) if j < len(elems) else None
    if num is None or num[1] >= len(elems):
        return None
    entier = 0
    if elems[num[1]] == "and" and num[1] + 1 < len(elems):
        k = num[1] + 1
        if elems[k] == "a" and k + 1 < len(elems) and elems[k + 1] in ("half", "third", "quarter"):
            valeur = Fraction(1, _DENOMINATEUR_DU_MOT[elems[k + 1]], negatif, num[0])
            return (valeur, k + 2) if _verifie(FRACTION, valeur, elems[i : k + 2]) else None
        entier = num[0]
        num = plus_long_entier(elems, k)
        if num is None or num[1] >= len(elems):
            return None
    a, j = num
    if a < 2 and not entier:
        return None                    # « one third », « one half » : laissés en lettres
    candidats = []
    if elems[j] == "over":
        den = plus_long_entier(elems, j + 1) if j + 1 < len(elems) else None
        if den:
            candidats.append(den)
    else:
        for longueur in (3, 2, 1):
            fin = j + longueur
            if fin <= len(elems) and elems[fin - 1] in _DENOMINATEUR_DU_MOT:
                candidats.append((_DENOMINATEUR_DU_MOT[elems[fin - 1]], fin))
    for den, fin in candidats:
        valeur = Fraction(a, den, negatif, entier)
        if den >= 2 and _verifie(FRACTION, valeur, elems[i:fin]):
            return valeur, fin
    return None


def ecrire_fraction(v: Fraction) -> str:
    signe = "-" if v.negatif else ""
    if v.unicode and (v.numerateur, v.denominateur) in _UNICODE_DE:
        return signe + (str(v.entier) if v.entier else "") + _UNICODE_DE[(v.numerateur, v.denominateur)]
    return signe + (f"{v.entier} " if v.entier else "") + f"{v.numerateur}/{v.denominateur}"


FRACTION = TypeFormule(
    "fraction",
    re.compile(rf"(?P<signe>{_SIGNE})?(?:(?:(?P<entier>\d+)\s?)?(?P<u>[{''.join(_FRACTIONS_UNICODE)}])"
               r"|(?:(?P<entier2>\d+)\s)?(?<![\d/])(?P<a>\d{1,3})/(?P<b>\d{1,3})(?![\d/]))(?![\w])"),
    _construire_fraction, _lire_fraction, _reconnaitre_fraction, ecrire_fraction,
)

# ── Mesure : nombre + unité ────────────────────────────────────────────────────

# symbole → (singulier, pluriel). Complète la table des abrègements (unités « ambigu = unite »).
_UNITES_EN = {
    "m": ("meter", "meters"), "g": ("gram", "grams"), "s": ("second", "seconds"), "V": ("volt", "volts"),
    "W": ("watt", "watts"), "L": ("liter", "liters"), "K": ("kelvin", "kelvins"),
    "ms": ("millisecond", "milliseconds"), "μs": ("microsecond", "microseconds"), "µs": ("microsecond", "microseconds"),
    "ns": ("nanosecond", "nanoseconds"), "nm": ("nanometer", "nanometers"), "μm": ("micrometer", "micrometers"),
    "µm": ("micrometer", "micrometers"), "mL": ("milliliter", "milliliters"), "cL": ("centiliter", "centiliters"),
    "dL": ("deciliter", "deciliters"), "kL": ("kiloliter", "kiloliters"), "μg": ("microgram", "micrograms"),
    "µg": ("microgram", "micrograms"), "t": ("tonne", "tonnes"),
    "km/h": ("kilometer per hour", "kilometers per hour"), "kph": ("kilometer per hour", "kilometers per hour"),
    "m/s": ("meter per second", "meters per second"), "km/s": ("kilometer per second", "kilometers per second"),
    "ft/s": ("foot per second", "feet per second"), "mpg": ("mile per gallon", "miles per gallon"),
    "kW": ("kilowatt", "kilowatts"), "MW": ("megawatt", "megawatts"), "GW": ("gigawatt", "gigawatts"),
    "kWh": ("kilowatt hour", "kilowatt hours"), "MWh": ("megawatt hour", "megawatt hours"),
    "GWh": ("gigawatt hour", "gigawatt hours"), "TWh": ("terawatt hour", "terawatt hours"),
    "kV": ("kilovolt", "kilovolts"), "mV": ("millivolt", "millivolts"), "mA": ("milliampere", "milliamperes"),
    "mAh": ("milliampere hour", "milliampere hours"), "Hz": ("hertz", "hertz"), "kHz": ("kilohertz", "kilohertz"),
    "MHz": ("megahertz", "megahertz"), "GHz": ("gigahertz", "gigahertz"), "kB": ("kilobyte", "kilobytes"),
    "KB": ("kilobyte", "kilobytes"), "MB": ("megabyte", "megabytes"), "GB": ("gigabyte", "gigabytes"),
    "TB": ("terabyte", "terabytes"), "kbps": ("kilobit per second", "kilobits per second"),
    "Mbps": ("megabit per second", "megabits per second"), "Gbps": ("gigabit per second", "gigabits per second"),
    "Mbit/s": ("megabit per second", "megabits per second"), "dB": ("decibel", "decibels"),
    "ha": ("hectare", "hectares"), "psi": ("pound per square inch", "pounds per square inch"),
    "hp": ("horsepower", "horsepower"), "kcal": ("kilocalorie", "kilocalories"), "cal": ("calorie", "calories"),
    "nmi": ("nautical mile", "nautical miles"), "ly": ("light year", "light years"), "ppm": ("part per million", "parts per million"),
    "ppb": ("part per billion", "parts per billion"), "kN": ("kilonewton", "kilonewtons"), "kPa": ("kilopascal", "kilopascals"),
    "hPa": ("hectopascal", "hectopascals"), "MPa": ("megapascal", "megapascals"), "Pa": ("pascal", "pascals"),
    "mmHg": ("millimeter of mercury", "millimeters of mercury"), "bbl": ("barrel", "barrels"),
    "sq mi": ("square mile", "square miles"), "sq ft": ("square foot", "square feet"), "sq km": ("square kilometer", "square kilometers"),
    "cu ft": ("cubic foot", "cubic feet"), "mi²": ("square mile", "square miles"), "ft²": ("square foot", "square feet"),
    "in²": ("square inch", "square inches"), "ft³": ("cubic foot", "cubic feet"),
    "°C": ("degree Celsius", "degrees Celsius"), "°F": ("degree Fahrenheit", "degrees Fahrenheit"),
    "° C": ("degree Celsius", "degrees Celsius"), "° F": ("degree Fahrenheit", "degrees Fahrenheit"),
    "°": ("degree", "degrees"), "Ω": ("ohm", "ohms"), "kΩ": ("kilohm", "kilohms"),
    "min": ("minute", "minutes"), "mins": ("minute", "minutes"), "sec": ("second", "seconds"), "secs": ("second", "seconds"),
    "hr": ("hour", "hours"), "hrs": ("hour", "hours"), "h": ("hour", "hours"), "lb": ("pound", "pounds"),
    "lbs": ("pound", "pounds"), "ft": ("foot", "feet"), "in.": ("inch", "inches"), "yd": ("yard", "yards"),
    "mi": ("mile", "miles"), "mph": ("mile per hour", "miles per hour"), "oz": ("ounce", "ounces"),
    "km": ("kilometer", "kilometers"), "cm": ("centimeter", "centimeters"), "mm": ("millimeter", "millimeters"),
    "kg": ("kilogram", "kilograms"), "mg": ("milligram", "milligrams"), "ml": ("milliliter", "milliliters"),
    "gal": ("gallon", "gallons"), "pt": ("pint", "pints"), "qt": ("quart", "quarts"),
}
# Unités d'une lettre (ou très courtes) qui sont aussi des mots ou des lettres : seulement après un nombre, et pas
# devant un mot qui ferait de la lettre autre chose (voir ``detection``).
UNITES_COURTES = frozenset("m g s V W L K t h".split())
# Unités jamais collées au nombre : « 33-66K » (milliers), « 22s », « 3s » (pluriel d'un chiffre).
_JAMAIS_COLLEES = frozenset("s K".split())
_EXPOSANTS = {"²": "square", "³": "cubic"}
# Unités converties en sens inverse (« ten kilometers » → « 10 km ») : symboles d'usage dans un texte courant.
_UNITES_RECONNUES = frozenset("km cm mm kg mg km/h mph °C °F kW MW kWh GHz MHz kHz GB MB TB".split())


def _pluriel_unite(dev: str) -> str:
    mots = dev.split()
    tete = 0 if "per" in mots or "of" in mots else len(mots) - 1
    irreguliers = {"foot": "feet", "inch": "inches", "hertz": "hertz", "horsepower": "horsepower"}
    mot = mots[tete]
    mots[tete] = irreguliers.get(mot, mot if mot.endswith("s") else mot + ("es" if mot.endswith("ch") else "s"))
    return " ".join(mots)


@cache
def _unites() -> dict[str, tuple[str, str]]:
    unites = {}
    for f, a in table_abregements().items():
        if a.ambigu == "unite" and a.developpement:
            dev = a.developpement
            sing = dev[:-1] if dev.endswith("s") and f.endswith("s") else dev
            unites[f] = (sing, _pluriel_unite(sing))
    unites.update(_UNITES_EN)
    for u, (sing, plur) in list(unites.items()):
        if u in ("m", "km", "cm", "mm", "ft", "mi", "in", "yd") or u.endswith("m") and len(u) == 2:
            for exp, adj in _EXPOSANTS.items():
                unites.setdefault(u + exp, (f"{adj} {sing}", f"{adj} {plur}"))
    return unites


@cache
def _motif_mesure() -> re.Pattern[str]:
    alt = "|".join(re.escape(u) for u in sorted(_unites(), key=len, reverse=True))
    return re.compile(
        rf"(?P<signe>{_SIGNE})?(?P<nombre>{_NOMBRE}){_FIN}(?:\s?[–-]\s?(?P<nombre2>{_NOMBRE}){_FIN})?"
        rf"(?:\s?(?P<unite>{alt})(?![\w])(?!\.\w)"
        rf"|(?P<pieds>['′])(?:\s?(?P<pouces>\d{{1,2}}(?:\.\d+)?)(?:\"|″|''))?(?![\w'])"
        rf"|(?P<pouces_seuls>″)(?![\w]))"
    )


class _MotifParesseux:
    """Motif construit à la première utilisation (la table des abrègements est lue à la demande)."""

    def __init__(self, fabrique):
        self._fabrique = fabrique

    def match(self, texte: str, position: int = 0):
        return self._fabrique().match(texte, position)


def _construire_mesure(m: re.Match[str]) -> Mesure | None:
    nombre = _construire_nombre(m)
    jusqua = Nombre(*_decouper(m.group("nombre2"))) if m.group("nombre2") else None
    if m.group("pieds"):
        if jusqua:
            return None
        pouces = Nombre(*_decouper(m.group("pouces"))) if m.group("pouces") else None
        if pouces is None and m.group("pieds") == "'":
            return None                    # « 6' » : trop souvent une apostrophe
        if pouces is not None and float(m.group("pouces")) >= 12:
            return None
        return Mesure(nombre, "ft", None, pouces) if pouces else Mesure(nombre, "′")
    if m.group("pouces_seuls"):
        return None if jusqua else Mesure(nombre, "″")
    if m.group("unite") in _JAMAIS_COLLEES and m.start("unite") == m.end("nombre2" if jusqua else "nombre"):
        return None
    return Mesure(nombre, m.group("unite"), jusqua)


def _un(nombre: str) -> bool:
    return nombre.replace(",", "") == "1"


def _lire_mesure(m: re.Match[str]) -> list[MotLu]:
    v = _construire_mesure(m)
    mots = [MotLu("minus", m.start("signe"), m.end("signe"))] if v.nombre.negatif else []
    mots += lire_nombre_aligne(m.group("nombre"), m.start("nombre"))
    if m.group("nombre2"):
        mots.append(MotLu("to", m.end("nombre"), m.start("nombre2")))
        mots += lire_nombre_aligne(m.group("nombre2"), m.start("nombre2"))
    dernier = m.group("nombre2") or m.group("nombre")
    if m.group("pieds"):
        if v.complement is None:
            return mots + [MotLu("foot" if _un(dernier) else "feet", m.start("pieds"), m.end(), composant=1)]
        mots.append(MotLu("foot", m.start("pieds"), m.end("pieds"), composant=0))      # « five foot ten »
        return mots + _composant(lire_nombre_aligne(m.group("pouces"), m.start("pouces")), 1)
    if m.group("pouces_seuls"):
        return mots + [MotLu("inch" if _un(dernier) else "inches", m.start("pouces_seuls"), m.end(), composant=1)]
    sing, plur = _unites()[m.group("unite")]
    dev = sing if _un(dernier) else plur
    return mots + _bloc(dev.split(), m.start("unite"), m.end("unite"), 1)


@cache
def _noms_d_unites() -> dict[tuple[str, ...], str]:
    noms = {}
    for u in _UNITES_RECONNUES:
        sing, plur = _unites()[u]
        noms[tuple(sing.lower().split())] = noms[tuple(plur.lower().split())] = u
    return noms


def _reconnaitre_mesure(elems: list[str], i: int) -> tuple[Mesure, int] | None:
    r = reconnaitre_nombre(elems, i)
    if r is None:
        return None
    v, j = r
    if elems[j : j + 1] == ["foot"] and not v.decimales:             # « five foot ten »
        p = plus_long_entier(elems, j + 1, maximum=11)
        if p:
            valeur = Mesure(v, "ft", None, Nombre(str(p[0])))
            return (valeur, p[1]) if _verifie(MESURE, valeur, elems[i : p[1]]) else None
    noms = _noms_d_unites()
    for longueur in (4, 3, 2, 1):
        suite = tuple(elems[j : j + longueur])
        if len(suite) == longueur and suite in noms:
            valeur = Mesure(v, noms[suite])
            return (valeur, j + longueur) if _verifie(MESURE, valeur, elems[i : j + longueur]) else None
    return None


def ecrire_mesure(v: Mesure) -> str:
    n = ecrire_nombre(v.nombre) + (("–" + ecrire_nombre(v.jusqua)) if v.jusqua else "")
    if v.complement is not None:
        return f"{n}'{ecrire_nombre(v.complement)}\""
    if v.unite in ("°", "′", "″"):
        return n + v.unite
    return f"{n} {v.unite}"


MESURE = TypeFormule("mesure", _MotifParesseux(_motif_mesure), _construire_mesure, _lire_mesure, _reconnaitre_mesure,
                     ecrire_mesure)

# ── Angle et coordonnées : 40°42′46″N ──────────────────────────────────────────

_DIRECTIONS = {"N": "north", "S": "south", "E": "east", "W": "west"}
_N_SIMPLE = r"\d{1,3}(?:\.\d+)?"


def _construire_angle(m: re.Match[str]) -> Angle | None:
    if not m.group("mi") and not m.group("dir"):
        return None                        # « 45° » seul : une mesure
    nb = lambda g: Nombre(*_decouper(m.group(g))) if m.group(g) else None
    return Angle(nb("deg"), nb("mi"), nb("se"), m.group("dir") or "")


def _lire_angle(m: re.Match[str]) -> list[MotLu]:
    mots = []
    for k, (g, sing, plur, signe) in enumerate((("deg", "degree", "degrees", "sd"), ("mi", "minute", "minutes", "sm"),
                                                ("se", "second", "seconds", "ss"))):
        if m.group(g):
            mots += _composant(lire_nombre_aligne(m.group(g), m.start(g)), k)
            mots.append(MotLu(sing if _un(m.group(g)) else plur, m.start(signe), m.end(signe), composant=k))
    if m.group("dir"):
        mots.append(MotLu(_DIRECTIONS[m.group("dir")], m.start("dir"), m.end("dir"), composant=3))
    return mots


def ecrire_angle(v: Angle) -> str:
    texte = ecrire_nombre(v.degres) + "°"
    if v.minutes:
        texte += ecrire_nombre(v.minutes) + "′"
    if v.secondes:
        texte += ecrire_nombre(v.secondes) + "″"
    return texte + v.direction


ANGLE = TypeFormule(
    "angle",
    re.compile(rf"(?P<deg>{_N_SIMPLE})(?P<sd>°)\s?(?:(?P<mi>{_N_SIMPLE})(?P<sm>['′])\s?(?:(?P<se>{_N_SIMPLE})(?P<ss>[\"″]|'')\s?)?)?"
               r"(?P<dir>[NSEW])?(?![\w])"),
    _construire_angle, _lire_angle, _a_porter, ecrire_angle,
)

# ── Plage : 1990–1995, 1990–95, 10–20, 3–1 ─────────────────────────────────────


def _construire_plage(m: re.Match[str]) -> Plage | None:
    if m.group("ra"):
        a, b = m.group("ra"), m.group("rb")
        if len(b) == 2 and int(a) <= 24 and int(b) < 60:
            return None                    # « 5:30 » : une heure
        return Plage(a, b, ":")
    if m.group("ya"):                      # « 2001/02 », « 2001/2002 » : année scolaire ou budgétaire
        a, b = m.group("ya"), m.group("yb")
        suite = (int(a) + 1) % (100 if len(b) == 2 else 10000)
        return Plage(a, b, "/") if int(b) == suite else None
    a, b = m.group("a"), m.group("b")
    if len(a) == 4 and len(b) == 4 and int(b) <= int(a):
        return None
    if len(a) == 4 and len(b) == 2 and int(a[:2] + b) <= int(a):
        return None
    return Plage(a, b)


def _lire_plage(m: re.Match[str]) -> list[MotLu]:
    if m.group("ra"):                      # rapport 16:9 sixteen to nine
        return (lire_chiffres(m.group("ra"), debut=m.start("ra")) + [MotLu("to", m.end("ra"), m.start("rb"), composant=1)]
                + _composant(lire_chiffres(m.group("rb"), debut=m.start("rb")), 2))
    if m.group("ya"):
        a, b, ga, gb = m.group("ya"), m.group("yb"), "ya", "yb"
    else:
        a, b, ga, gb = m.group("a"), m.group("b"), "a", "b"
    pa, pb = list(range(m.start(ga), m.end(ga))), list(range(m.start(gb), m.end(gb)))
    if len(a) == 4 and len(b) in (2, 4) and 1000 <= int(a) <= 2099:
        mots_a = lire_annee(a, pa)
        if len(b) == 4:
            mots_b = lire_annee(b, pb)
        elif b.startswith("0"):
            mots_b = [MotLu(OH, pb[0], pb[0] + 1)] + lire_chiffres(b[1], pb[1:])
        else:
            mots_b = lire_chiffres(b, pb)
    else:
        mots_a, mots_b = lire_chiffres(a, pa), lire_chiffres(b, pb)
    return mots_a + [MotLu("to", m.end(ga), m.start(gb), composant=1)] + _composant(mots_b, 2)


def _reconnaitre_plage(elems: list[str], i: int) -> tuple[Plage, int] | None:
    """« nineteen ninety to ninety five » → 1990–95 ; « three to one » → 3–1. Pas après « from », « between » : là,
    « from 10 to 20 » s'écrit avec « to »."""
    if i > 0 and elems[i - 1] in ("from", "between", "to"):
        return None
    a = annee_dite(elems, i)
    annee_ = a is not None and elems[a[1] : a[1] + 1] == ["to"]
    if not annee_:
        a = plus_long_entier(elems, i, maximum=9999)
    if a is None or elems[a[1] : a[1] + 1] != ["to"]:
        return None
    k = a[1] + 1
    if annee_:
        b = plus_longue_annee(elems, k)
        if b:
            texte_b = str(b[0])
        elif elems[k : k + 1] == [OH] and k + 1 < len(elems) and elems[k + 1] in UNITES[1:10]:
            b, texte_b = (UNITES.index(elems[k + 1]), k + 2), "0" + str(UNITES.index(elems[k + 1]))
        else:
            b = plus_long_entier(elems, k, maximum=99)
            texte_b = str(b[0]) if b else ""
    else:
        b = plus_long_entier(elems, k, maximum=9999)
        texte_b = str(b[0]) if b else ""
    if b is None or (a[0] == 1 and b[0] == 1):
        return None
    valeur = Plage(str(a[0]), texte_b)
    m = PLAGE.motif.match(PLAGE.ecrire(valeur))
    if m is None or _construire_plage(m) is None or elements([x.texte for x in _lire_plage(m)]) != elems[i : b[1]]:
        return None
    return valeur, b[1]


PLAGE = TypeFormule(
    "plage", re.compile(r"(?<![\d.,/])(?:(?P<a>\d{1,4})\s?[–—-]\s?(?P<b>\d{1,4})|(?P<ra>\d{1,3}):(?P<rb>\d{1,3})"
                        r"|(?P<ya>1\d{3}|20\d\d)/(?P<yb>\d\d(?:\d\d)?))"
                        r"(?!\d)(?![.,:/-]\d)(?![\w])"),
    _construire_plage, _lire_plage, lambda e, i: _reconnaitre_plage(e, i), lambda v: f"{v.debut}{v.signe}{v.fin}",
)

# ── Version et adresse IP : v2.0, 14.2.1, 192.168.1.1 ──────────────────────────


def _construire_version(m: re.Match[str]) -> Version | None:
    parties = tuple(m.group("num").split("."))
    prefixe = bool(m.group("v"))
    if not prefixe and len(parties) < 3:
        return None
    ip = not prefixe and len(parties) == 4 and all(int(p) <= 255 for p in parties)
    if not prefixe and not ip and (len(parties) > 3 or any(len(p) > 3 for p in parties)):
        return None
    if not prefixe and not ip and all(len(p) == 3 for p in parties[1:]):
        return None                        # « 10.000.000 » : milliers à l'européenne
    return Version(parties, prefixe, ip)


def _lire_version(m: re.Match[str]) -> list[MotLu]:
    v = _construire_version(m)
    mots = [MotLu("version", m.start("v"), m.end("v"))] if v.prefixe else []
    position = m.start("num")
    for k, p in enumerate(v.parties):
        if k:
            mots.append(MotLu("dot" if v.ip else "point", position - 1, position, composant=k))
        places = list(range(position, position + len(p)))
        if v.ip:
            lus = lire_paires(p, places)
        elif k and p == "0":
            lus = [MotLu(OH, position, position + 1)]
        else:
            lus = lire_chiffres(p, places)
        mots += _composant(lus, k)
        position += len(p) + 1
    return mots


def _reconnaitre_version(elems: list[str], i: int) -> tuple[Version, int] | None:
    """« version two point oh » → v2.0 ; « six point two point one » → 6.2.1 (trois parties au moins)."""
    prefixe = elems[i] == "version"
    parties, j = [], i + 1 if prefixe else i
    while j < len(elems):
        if parties:
            if elems[j] != "point" or j + 1 >= len(elems):
                break
            j += 1
        if elems[j] == OH and parties:
            parties.append("0")
            j += 1
            continue
        n = plus_long_entier(elems, j)
        if n is None:
            if parties:
                j -= 1
            break
        parties.append(str(n[0]))
        j = n[1]
    if len(parties) < (2 if prefixe else 3):
        return None
    valeur = Version(tuple(parties), prefixe)
    return (valeur, j) if _verifie(VERSION, valeur, elems[i:j]) else None


VERSION = TypeFormule(
    "version", re.compile(r"(?<![\w.])(?:(?P<v>[vV])\.?\s?)?(?P<num>\d+(?:\.\d+)+)(?![\w])(?!\.\d)"),
    _construire_version, _lire_version, _reconnaitre_version,
    lambda v: ("v" if v.prefixe else "") + ".".join(v.parties),
)

# ── Nombre romain : World War II (two), Henry VIII (the eighth, voir detection) ─

_VALEURS_ROMAINES = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
                     (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))


def en_romain(n: int) -> str:
    res = ""
    for v, s in _VALEURS_ROMAINES:
        while n >= v:
            res, n = res + s, n - v
    return res


def depuis_romain(texte: str) -> int | None:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for k, c in enumerate(texte):
        v = vals[c]
        total += -v if k + 1 < len(texte) and vals[texte[k + 1]] > v else v
    return total if total and en_romain(total) == texte else None


def _construire_romain(m: re.Match[str]) -> Romain | None:
    v = depuis_romain(m.group(0))
    return Romain(v) if v and v < 4000 else None


ROMAIN = TypeFormule(
    "romain", re.compile(r"[IVXLCDM]{1,8}(?![\w])"), _construire_romain,
    lambda m: _bloc(ecrire_entier(depuis_romain(m.group(0))), m.start(), m.end()), _a_porter, lambda v: en_romain(v.valeur),
)

# ── Sigle en capitales (hors table) : épelé s'il est court ou sans voyelle ─────


def _construire_sigle(m: re.Match[str]) -> Sigle | None:
    lettres = re.sub(r"[^A-Z]", "", m.group(0))
    if "." in m.group(0):
        return Sigle(lettres)
    if m.group("chiffres"):                # « Q1 », « A4 », « AS400 », « MP3 » : lettres épelées, puis le nombre
        if m.group("chiffres").startswith("0") and len(m.group("chiffres")) > 1:
            return None
        return Sigle(m.group(0)) if len(lettres) <= 3 or not set(lettres) & set("AEIOUY") else None
    if len(lettres) <= 3 or not set(lettres) & set("AEIOUY"):
        return Sigle(lettres)
    return None


def _lire_sigle(m: re.Match[str]) -> list[MotLu]:
    mots = [MotLu(c, m.start() + k, m.start() + k + 1, composant=n, nature=LETTRE)
            for n, (k, c) in enumerate((k, c) for k, c in enumerate(m.group(0)) if c.isalpha())]
    if m.group("chiffres"):
        mots += _composant(lire_chiffres(m.group("chiffres"), debut=m.start("chiffres")), len(mots))
    return mots


SIGLE = TypeFormule(
    "sigle", re.compile(r"(?:[A-Z]\.){2,}|[A-Z]{1,4}(?P<chiffres>\d{1,4})(?![\w])(?![.,]\d)|[A-Z]{2,6}(?![\w])"),
    _construire_sigle, _lire_sigle, _a_porter,
    lambda v: v.lettres,
)

# ── Durée : 2:03:45, 3:43.13, 1h30, 2 hr 15 min ────────────────────────────────

_PARTIES = (("h", "hour", "hours"), ("mi", "minute", "minutes"), ("s", "second", "seconds"))


def _groupes_duree(m: re.Match[str]) -> dict[str, str]:
    return {p: g for p, *_n in _PARTIES for g in (p, p + "2", p + "3", p + "4") if g in m.re.groupindex and m.group(g)}


def _construire_duree(m: re.Match[str]) -> Duree | None:
    g = _groupes_duree(m)
    v = {p: int(m.group(x)) for p, x in g.items()}
    frac = m.group("frac") or m.group("frac2") or ""
    if v.get("mi", 0) >= 60 and "h" in v or v.get("s", 0) >= 60:
        return None
    return Duree(v.get("h"), v.get("mi"), v.get("s"), frac)


def _lire_duree(m: re.Match[str]) -> list[MotLu]:
    v = _construire_duree(m)
    g = _groupes_duree(m)
    mots = []
    for k, (p, sing, plur) in enumerate(_PARTIES):
        if p not in g:
            continue
        x = g[p]
        n = int(m.group(x))
        if p == "s" and v.fraction:
            debut_f = m.start("frac") if m.group("frac") else m.start("frac2")
            mots += _composant(lire_chiffres(str(n), debut=m.start(x)), k)
            mots.append(MotLu("point", debut_f - 1, debut_f, composant=k))
            mots += [MotLu(UNITES[int(c)], debut_f + q, debut_f + q + 1, composant=k) for q, c in enumerate(v.fraction)]
            fin = debut_f + len(v.fraction)
            mots.append(MotLu(plur, fin, fin, composant=k))
            continue
        mots += _bloc(ecrire_entier(n), m.start(x), m.end(x), k)
        mots.append(MotLu(sing if n == 1 else plur, m.start(x), m.end(x), composant=k))
    return mots


def _reconnaitre_duree(elems: list[str], i: int) -> tuple[Duree, int] | None:
    valeurs: dict[str, int] = {}
    j = i
    for p, sing, plur in _PARTIES:
        n = plus_long_entier(elems, j) if j < len(elems) else None
        if n and n[1] < len(elems) and elems[n[1]] in (sing, plur):
            valeurs[p], j = n[0], n[1] + 1
            if j < len(elems) - 1 and elems[j] == "and" and p != "s":
                j += 1
    if len(valeurs) < 2 or "mi" not in valeurs:
        return None
    if elems[j - 1] == "and":
        j -= 1
    valeur = Duree(valeurs.get("h"), valeurs.get("mi"), valeurs.get("s"))
    return (valeur, j) if _verifie(DUREE, valeur, elems[i:j]) else None


def ecrire_duree(v: Duree) -> str:
    if v.heures is not None and v.secondes is not None:
        return f"{v.heures}:{v.minutes or 0:02d}:{v.secondes:02d}" + (f".{v.fraction}" if v.fraction else "")
    if v.heures is None and v.fraction:
        return f"{v.minutes}:{v.secondes:02d}.{v.fraction}"
    parties = [(v.heures, "h"), (v.minutes, "min"), (v.secondes, "s")]
    return " ".join(f"{n} {s}" for n, s in parties if n is not None)


DUREE = TypeFormule(
    "duree",
    re.compile(r"(?:(?P<h>\d{1,2}):(?P<mi>[0-5]\d):(?P<s>[0-5]\d)(?:\.(?P<frac>\d+))?"
               r"|(?P<mi2>\d{1,2}):(?P<s2>[0-5]\d)\.(?P<frac2>\d{1,3})"
               r"|(?P<h3>\d{1,2})\s?(?:h|hr|hrs)\s?(?P<mi3>[0-5]?\d)(?:\s?(?:m|min|mins)(?:\s?(?P<s3>[0-5]?\d)\s?(?:s|sec))?)?"
               r"|(?P<mi4>\d{1,3})\s?min\s?(?P<s4>[0-5]?\d)\s?(?:s|sec))(?![\w:])(?!\.\d)"),
    _construire_duree, _lire_duree, _reconnaitre_duree, ecrire_duree,
)

# ── Intervalle : [0, 1], (0, 1], [a, b) ────────────────────────────────────────

_BORNE = r"[-+−]?(?:\d+(?:\.\d+)?|∞|[a-zA-Z])"


def _lire_borne(m: re.Match[str], g: str, composant: int) -> list[MotLu]:
    texte, debut = m.group(g), m.start(g)
    mots = []
    if texte[0] in "-−+":
        mots.append(MotLu("minus" if texte[0] != "+" else "plus", debut, debut + 1))
        texte, debut = texte[1:], debut + 1
    if texte == "∞":
        mots.append(MotLu("infinity", debut, debut + 1))
    elif texte.isalpha():
        mots.append(MotLu(texte, debut, debut + 1, nature=LETTRE))
    else:
        mots += lire_nombre_aligne(texte, debut)
    return _composant(mots, composant)


def _construire_intervalle(m: re.Match[str]) -> Intervalle | None:
    if "[" not in m.group("g") + m.group("d") and "]" not in m.group("g") + m.group("d"):
        return None
    return Intervalle(m.group("a"), m.group("b"), m.group("g") in "](", m.group("d") in "[)")


def _lire_intervalle(m: re.Match[str]) -> list[MotLu]:
    """« [0, 1] » : from zero to one. L'ouverture des crochets n'est pas dite (comme en français)."""
    return ([MotLu("from", m.start("g"), m.end("g"))] + _lire_borne(m, "a", 0)
            + [MotLu("to", m.start("sep"), m.end("sep"), composant=1)] + _lire_borne(m, "b", 2))


INTERVALLE = TypeFormule(
    "intervalle",
    re.compile(rf"(?P<g>[\[\](])\s?(?P<a>{_BORNE})\s?(?P<sep>[,;])\s?(?P<b>{_BORNE})\s?(?P<d>[\[\])])"),
    _construire_intervalle, _lire_intervalle, _a_porter,
    lambda v: ("(" if v.ouvert_gauche else "[") + f"{v.gauche}, {v.droite}" + (")" if v.ouvert_droite else "]"),
)


# ── Symbole seul : & and, @ at, + plus, = equals, # number (devant un nombre) ───
# Référence de prononciation : NLP_EN/Lexique/dist/speciaux.tsv, sous-table Symboles (type « symbole »). $ £ € % ° ne se
# lisent qu'avec un nombre (monnaie, pourcentage, mesure). Courriels, @mention et #mot-dièse sont des mots du tokeniseur,
# jamais un symbole seul ; « < » (« I <3 ») n'est pas dans la table.

_SYMBOLES = {"&": "and", "@": "at", "+": "plus", "=": "equals", "#": "number"}


@dataclass(frozen=True)
class Symbole:
    signe: str


SYMBOLE = TypeFormule(
    "symbole", re.compile(r"(?<![\w@#&+=])(?:(?P<s>[&@+=])(?![\w@&+=#])|(?P<s2>#)(?=\s?\d))"),
    lambda m: Symbole(m.group(0)), lambda m: [MotLu(_SYMBOLES[m.group(0)], m.start(), m.end())], _a_porter,
    lambda v: v.signe,
)


def lire_mots(mots: list[str]) -> list[MotLu]:
    return [MotLu(m, 0, 0) for m in mots]
