# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Téléphone, fraction, mesure, chiffres romains, sigle.

Sigles et abréviations connus (SNCF, M., etc.) relèvent du lexique, qui en donne la
prononciation ; le type ``SIGLE`` n'épelle que ceux qu'aucun lexique ne peut connaître.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from functools import cache
from .briques import briques
from .nombres import MOINS, ZERO, Element, MotLu, ecrire_entier, elements, lire_chiffres, plus_long_entier
from .types import (
    NOMBRE,
    _CHIFFRES_0_9,
    _ESPACES,
    _FIN,
    _NOMBRE,
    _SIGNE,
    Nombre,
    TypeFormule,
    _bloc,
    _composant,
    _ecrire_nombre,
    _lire_groupe_nombre,
    _nombre_du_groupe,
    _ordinal_de,
    _reconnaitre_nombre,
)

# ── Valeurs ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Telephone:
    chiffres: str              # numéro national : dix chiffres
    indicatif: str = ""        # « 33 » pour +33, le numéro perd alors son zéro initial


@dataclass(frozen=True)
class Fraction:
    numerateur: int
    denominateur: int
    negatif: bool = False


@dataclass(frozen=True)
class Mesure:
    nombre: Nombre
    unite: str                 # symbole : « km », « km/h », « m² »


@dataclass(frozen=True)
class Romain:
    valeur: int
    ordinal: bool = False
    feminin: bool = False


@dataclass(frozen=True)
class Sigle:
    texte: str


def _verifie(t: TypeFormule, valeur, elems: list[str]) -> bool:
    """La valeur se relit-elle avec ces éléments ? (accords de nombre ignorés)"""
    m = t.motif.match(t.ecrire(valeur))
    if m is None:
        return False
    relus = elements([mot.texte for mot in t.lire(m)])
    return [e.rstrip("s") for e in relus] == [e.rstrip("s") for e in elems]


# ── Téléphone ──────────────────────────────────────────────────────────────────

_SEP_TEL = rf"[{_ESPACES}.-]?"


def _numero(m: re.Match[str]) -> str:
    return "numero" if m.group("numero") else "numero2"


def _construire_telephone(m: re.Match[str]) -> Telephone:
    chiffres = "".join(c for c in m.group(_numero(m)) if c.isdigit())
    return Telephone(chiffres, "33") if m.group("indicatif") else Telephone(chiffres)


def _lire_paire(texte: str, debut: int, composant: int) -> list[MotLu]:
    """Un groupe de chiffres d'un numéro : « 06 » → zéro six, « 78 » → soixante-dix-huit."""
    fin = debut + len(texte)
    if texte.startswith("0") and len(texte) == 2:
        mots = [MotLu(ZERO, debut, fin), MotLu(_CHIFFRES_0_9[int(texte[1])], debut, fin)]
    else:
        mots = lire_chiffres(texte)
    return _bloc(mots, debut, fin, composant)


def _lire_telephone(m: re.Match[str]) -> list[MotLu]:
    mots = []
    composant = 0
    if m.group("indicatif"):
        debut = m.start("indicatif")
        mots.append(MotLu("plus", debut, debut + 1))
        mots.extend(_lire_paire("33", debut + 1, 0))
        composant = 1
    numero = _numero(m)
    for groupe in re.finditer(r"\d\d?", m.group(numero)):
        mots.extend(_lire_paire(groupe.group(), m.start(numero) + groupe.start(), composant))
        composant += 1
    return mots


def _reconnaitre_telephone(elems: list[str], i: int) -> tuple[Telephone, int] | None:
    chiffres = ""
    j = i
    for _ in range(5):
        if j < len(elems) - 1 and elems[j] == ZERO and elems[j + 1] in _CHIFFRES_0_9:
            chiffres += "0" + str(_CHIFFRES_0_9.index(elems[j + 1]))
            j += 2
            continue
        paire = plus_long_entier(elems, j, maximum=99) if j < len(elems) else None
        if paire is None or paire[0] < 10 or not chiffres:
            return None
        chiffres += str(paire[0])
        j = paire[1]
    valeur = Telephone(chiffres)
    return (valeur, j) if chiffres[1] != "0" and _verifie(TELEPHONE, valeur, elems[i:j]) else None


def _ecrire_telephone(v: Telephone) -> str:
    if v.indicatif:
        return f"+{v.indicatif} {v.chiffres[0]} " + " ".join(v.chiffres[k : k + 2] for k in range(1, 9, 2))
    return " ".join(v.chiffres[k : k + 2] for k in range(0, 10, 2))


TELEPHONE = TypeFormule(
    "telephone",
    re.compile(
        rf"(?:(?P<indicatif>\+33){_SEP_TEL}(?P<numero>[1-9](?:{_SEP_TEL}\d{{2}}){{4}})"
        rf"|(?P<numero2>0[1-9](?:{_SEP_TEL}\d{{2}}){{4}})){_FIN}"
    ),
    _construire_telephone,
    _lire_telephone,
    _reconnaitre_telephone,
    _ecrire_telephone,
)

# ── Fraction ───────────────────────────────────────────────────────────────────

_DENOMINATEURS = {2: ("demi", "demis"), 3: ("tiers", "tiers"), 4: ("quart", "quarts")}
# Dénominateurs dits par leur ordinal ; les autres se disent « sur ».
_ORDINAUX_DE_FRACTION = frozenset(range(5, 17)) | {100, 1000}
_NOM_DE_DENOMINATEUR = {nom: d for d, noms in _DENOMINATEURS.items() for nom in noms}


def _construire_fraction(m: re.Match[str]) -> Fraction | None:
    den = int(m.group("den"))
    return Fraction(int(m.group("num")), den, bool(m.group("signe"))) if den > 1 else None


def _lire_fraction(m: re.Match[str]) -> list[MotLu]:
    v = _construire_fraction(m)
    mots = [MotLu(MOINS, m.start("signe"), m.end("signe"))] if v.negatif else []
    mots.extend(lire_chiffres(m.group("num"), list(range(m.start("num"), m.end("num")))))
    den = (m.start("den"), m.end("den"))
    pluriel = v.numerateur > 1
    if v.denominateur in _DENOMINATEURS:
        mots.append(MotLu(_DENOMINATEURS[v.denominateur][pluriel], *den, composant=1))
    elif v.denominateur in _ORDINAUX_DE_FRACTION:
        *debut, dernier = ecrire_entier(v.denominateur)[-1].split("-")
        ordinal = "-".join(debut + [_ordinal_de(dernier) + ("s" if pluriel else "")])
        mots.append(MotLu(ordinal, *den, composant=1))
    else:
        mots.append(MotLu("sur", m.end("num"), m.start("den"), composant=1))
        mots.extend(_composant(lire_chiffres(m.group("den"), list(range(*den))), 2))
    return mots


def _reconnaitre_fraction(elems: list[str], i: int) -> tuple[Fraction, int] | None:
    negatif = elems[i] == MOINS
    j = i + 1 if negatif else i
    num = plus_long_entier(elems, j) if j < len(elems) else None
    # « un tiers », « un quart » : trop courants comme noms pour être convertis.
    if num is None or num[0] < 2 or num[1] >= len(elems):
        return None
    j = num[1]
    candidats = []
    if elems[j] in _NOM_DE_DENOMINATEUR:
        candidats.append((_NOM_DE_DENOMINATEUR[elems[j]], j + 1))
    elif elems[j] == "sur":
        den = plus_long_entier(elems, j + 1) if j + 1 < len(elems) else None
        if den:
            candidats.append(den)
    else:
        # Dénominateur ordinal : toujours au pluriel après un numérateur supérieur à un.
        candidats.extend((d, j + len(elements(ecrire_entier(d)))) for d in _ORDINAUX_DE_FRACTION)
    for den, fin in candidats:
        if den < 2 or fin > len(elems) or not (elems[j] == "sur" or elems[fin - 1].endswith("s")):
            continue
        valeur = Fraction(num[0], den, negatif)
        if _verifie(FRACTION, valeur, elems[i:fin]):
            return valeur, fin
    return None


FRACTION = TypeFormule(
    "fraction",
    re.compile(rf"(?P<signe>[-−])?(?P<num>\d+)/(?P<den>\d+){_FIN}"),
    _construire_fraction,
    _lire_fraction,
    _reconnaitre_fraction,
    lambda v: ("-" if v.negatif else "") + f"{v.numerateur}/{v.denominateur}",
)

# ── Mesure ─────────────────────────────────────────────────────────────────────

_EXPOSANTS = {"²": ("carré", "carrés"), "³": ("cube", "cubes")}


@dataclass(frozen=True)
class _Unite:
    symbole: str
    singulier: str
    pluriel: str
    feminin: bool
    inverse: bool


# Unités converties en sens inverse (« douze kilomètres » → « 12 km ») : celles dont le symbole est
# d'usage dans un texte courant et dont le nom n'a pas d'autre sens.
_UNITES_RECONNUES = frozenset(
    "km cm mm m kg mg g L mL cL ha °C kW kWh Hz kHz MHz GHz ko Mo Go To dB hPa kcal".split()
)


@cache
def _unites() -> dict[str, _Unite]:
    return {
        s: _Unite(s, b.lecture, b.lecture_pluriel or b.lecture, b.genre == "f", s in _UNITES_RECONNUES)
        for s, b in briques("unite").items()
    }


def _motif_mesure() -> re.Pattern[str]:
    symboles = "|".join(re.escape(s) for s in sorted(_unites(), key=len, reverse=True))
    return re.compile(
        rf"(?P<signe>{_SIGNE})?(?P<nombre>{_NOMBRE})[{_ESPACES}]?"
        rf"(?P<unite>(?P<u1>{symboles})(?P<exp>[²³])?(?:/(?P<u2>{symboles}))?){_FIN}"
    )


def _pluriel(nombre: Nombre) -> bool:
    return int(nombre.entier) >= 2


def _lire_mesure(m: re.Match[str]) -> list[MotLu]:
    nombre = _nombre_du_groupe(m)
    unite = _unites()[m.group("u1")]
    pluriel = _pluriel(nombre)
    mots = _lire_groupe_nombre(m, feminin=unite.feminin)
    u1 = (m.start("u1"), m.end("u1"))
    mots.extend(MotLu(mot, *u1, composant=1) for mot in (unite.pluriel if pluriel else unite.singulier).split())
    if m.group("exp"):
        mots.append(MotLu(_EXPOSANTS[m.group("exp")][pluriel], m.start("exp"), m.end("exp"), composant=1))
    if m.group("u2"):
        mots.append(MotLu("par", m.start("u2") - 1, m.start("u2"), composant=2))
        mots.extend(MotLu(mot, m.start("u2"), m.end("u2"), composant=2) for mot in _unites()[m.group("u2")].singulier.split())
    return mots


@cache
def _noms_d_unites() -> dict[tuple[str, ...], str]:
    """Suites de mots (au singulier) → symbole, pour les unités reconnues en sens inverse."""
    unites = _unites()
    noms = {}
    for u in unites.values():
        if u.inverse:
            noms[tuple(elements(u.singulier.split()))] = noms[tuple(elements(u.pluriel.split()))] = u.symbole
    for kilometre in ("kilomètre", "kilomètres"):
        noms[(kilometre, "par", "heure")] = "km/h"
    for exposant, (singulier, pluriel) in _EXPOSANTS.items():
        for symbole in ("m", "km", "cm", "mm"):
            noms[(unites[symbole].singulier, singulier)] = symbole + exposant
            noms[(unites[symbole].pluriel, pluriel)] = symbole + exposant
    return noms


def _reconnaitre_mesure(elems: list[str], i: int) -> tuple[Mesure, int] | None:
    nombre = _reconnaitre_nombre(elems, i)
    if nombre is None:
        return None
    v, j = nombre
    noms = _noms_d_unites()
    for longueur in (3, 2, 1):
        suite = tuple(elems[j : j + longueur])
        symbole = noms.get(suite) if len(suite) == longueur else None
        if symbole:
            return Mesure(v, symbole), j + longueur
    return None


MESURE = TypeFormule(
    "mesure",
    _motif_mesure(),
    lambda m: Mesure(_nombre_du_groupe(m), m.group("unite")),
    _lire_mesure,
    _reconnaitre_mesure,
    lambda v: _ecrire_nombre(v.nombre) + " " + v.unite,
)

# ── Chiffres romains ───────────────────────────────────────────────────────────

_VALEURS_ROMAINES = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
    (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)
_SUFFIXES_ROMAINS = {"er": False, "re": True, "ère": True, "e": False, "ème": False}


def en_romain(n: int) -> str:
    resultat = ""
    for valeur, lettres in _VALEURS_ROMAINES:
        while n >= valeur:
            resultat += lettres
            n -= valeur
    return resultat


def depuis_romain(texte: str) -> int | None:
    """Valeur d'un nombre romain écrit sous sa forme régulière, sinon ``None``."""
    n, k = 0, 0
    for valeur, lettres in _VALEURS_ROMAINES:
        while texte.startswith(lettres, k):
            n += valeur
            k += len(lettres)
    return n if n and k == len(texte) and en_romain(n) == texte else None


def _construire_romain(m: re.Match[str], en_contexte: bool = False) -> Romain | None:
    """``en_contexte`` : un mot annonce un numéro (« Chapitre XLV », « Louis XIV ») ; tout nombre régulier compte."""
    lettres, suffixe = m.group("rom"), m.group("suffixe")
    valeur = depuis_romain(lettres)
    if valeur is None:
        return None
    if en_contexte and not suffixe and len(lettres) >= 2:
        return Romain(valeur, False, False)
    # « CD », « DIX », « MIX » sont plus souvent autre chose, et « Le », « De », « Ce », « Me » sont des
    # mots : hors des nombres écrits en I, V, X, il faut au moins quatre lettres. Une lettre seule
    # n'est un nombre qu'avec un suffixe ordinal (« Ier », « Ve », « Xe »).
    courant = set(lettres) <= set("IVX") and (len(lettres) >= 2 or bool(suffixe))
    if not (courant or len(lettres) >= 4):
        return None
    if suffixe and (suffixe in ("er", "re", "ère")) != (valeur == 1):
        return None
    return Romain(valeur, bool(suffixe), bool(suffixe) and _SUFFIXES_ROMAINS[suffixe])


def _lire_romain(m: re.Match[str], en_contexte: bool = False) -> list[MotLu]:
    v = _construire_romain(m, en_contexte)
    if v.ordinal and v.valeur == 1:
        return [MotLu("première" if v.feminin else "premier", m.start(), m.end())]
    mots = ecrire_entier(v.valeur)
    if v.ordinal:
        *debut, dernier = mots[-1].split("-")
        mots[-1] = "-".join(debut + [_ordinal_de(dernier)])
    # Les chiffres romains ne se lisent pas un à un : toute la lecture porte sur le nombre entier.
    return _bloc(lire_mots(mots), m.start(), m.end())


def lire_mots(mots: list[str]) -> list[MotLu]:
    """Mots sans alignement propre, découpés en éléments aux traits d'union."""
    return [
        MotLu(mot, 0, 0, tuple(Element(e, 0, 0, k > 0) for k, e in enumerate(mot.split("-")))) for mot in mots
    ]


def _ecrire_romain(v: Romain) -> str:
    suffixe = ("re" if v.feminin else "er") if v.valeur == 1 else "e"
    return en_romain(v.valeur) + (suffixe if v.ordinal else "")


def romain_en_contexte(texte: str, position: int):
    """Nombre romain régulier d'au moins deux lettres, sans suffixe, que le contexte annonce (« Chapitre XLV »),
    même quand il est trop court pour être pris seul (« XLV », « LX ») : (valeur, fin, lecture) ou None."""
    m = ROMAIN.motif.match(texte, position)
    if m is None or (v := _construire_romain(m, True)) is None:
        return None
    return v, m.end(), _lire_romain(m, True)


ROMAIN = TypeFormule(
    "romain",
    re.compile(rf"(?P<rom>[IVXLCDM]+)(?P<suffixe>{'|'.join(sorted(_SUFFIXES_ROMAINS, key=len, reverse=True))})?{_FIN}"),
    _construire_romain,
    _lire_romain,
    lambda elems, i: None,
    _ecrire_romain,
)

# ── Sigle ──────────────────────────────────────────────────────────────────────

_VOYELLES_ECRITES = frozenset("AEIOUYÀÂÉÈÊËÎÏÔÙÛÜ")
LETTRE = "lettre"


def _construire_sigle(m: re.Match[str]) -> Sigle | None:
    texte = m.group()
    # Un mot en capitales sans chiffre est laissé à la chaîne : le lexique le dit, sinon elle l'épelle d'un seul
    # tenant s'il est imprononçable (« SCLC » ɛs.se.ɛl.se, « FIH »), ou le modèle de mot le lit (« UNICEF »).
    if texte.isalpha():
        return None
    return Sigle(texte)


def _lire_sigle(m: re.Match[str]) -> list[MotLu]:
    mots = []
    for composant, morceau in enumerate(re.finditer(r"\d+|[^\W\d]", m.group())):
        debut = m.start() + morceau.start()
        if morceau.group().isdigit():
            mots.extend(_bloc(lire_chiffres(morceau.group()), debut, debut + len(morceau.group()), composant))
        else:
            mots.append(MotLu(morceau.group(), debut, debut + 1, composant=composant, nature=LETTRE))
    return mots


SIGLE = TypeFormule(
    "sigle",
    re.compile(rf"[A-Z](?:[A-Z]|\d)+{_FIN}"),
    _construire_sigle,
    _lire_sigle,
    lambda elems, i: None,
    lambda v: v.texte,
)


# ── Durée ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Duree:
    heures: int | None = None
    minutes: int | None = None
    secondes: int | None = None


_PARTIES_DUREE = (("h", "heure"), ("min", "minute"), ("s", "seconde"))
_E = rf"[{_ESPACES}]?"


def _construire_duree(m: re.Match[str]) -> Duree | None:
    valeurs = [int(m.group(g) or m.group(g + "2") or -1) if g != "h" else int(m.group("h") or -1) for g, _n in _PARTIES_DUREE]
    h, mn, s = (v if v >= 0 else None for v in valeurs)
    return Duree(h, mn, s) if (mn or 0) < 60 and (s or 0) < 60 else None


def _lire_duree(m: re.Match[str]) -> list[MotLu]:
    mots = []
    for composant, (groupe, nom) in enumerate(_PARTIES_DUREE):
        for g, signe in ((groupe, "u" + groupe), (groupe + "2", "u" + groupe + "2")):
            if g in m.re.groupindex and m.group(g) is not None:
                valeur = int(m.group(g))
                mots.extend(_bloc(lire_chiffres(str(valeur), feminin=True), m.start(g), m.end(g), composant))
                mots.append(MotLu(nom + ("s" if valeur > 1 else ""), m.start(signe), m.end(signe), composant=composant))
    return mots


def _reconnaitre_duree(elems: list[str], i: int) -> tuple[Duree, int] | None:
    valeurs: dict[str, int] = {}
    j = i
    for _signe, nom in _PARTIES_DUREE:
        nombre = plus_long_entier(elems, j) if j < len(elems) else None
        if nombre and nombre[1] < len(elems) and elems[nombre[1]] in (nom, nom + "s"):
            valeurs[nom], j = nombre[0], nombre[1] + 1
    # Une durée a au moins deux parties, dont des minutes : « trois heures » seul est une heure.
    if len(valeurs) < 2 or "minute" not in valeurs:
        return None
    valeur = Duree(valeurs.get("heure"), valeurs.get("minute"), valeurs.get("seconde"))
    return (valeur, j) if _verifie(DUREE, valeur, elems[i:j]) else None


def _ecrire_duree(v: Duree) -> str:
    parties = [(v.heures, "h"), (v.minutes, "min"), (v.secondes, "s")]
    return " ".join(f"{valeur} {signe}" for valeur, signe in parties if valeur is not None)


DUREE = TypeFormule(
    "duree",
    re.compile(
        rf"(?:(?:(?P<h>\d+){_E}(?P<uh>[hH]){_E})?(?P<min>\d+){_E}(?P<umin>min|mn)(?:{_E}(?P<s>\d+){_E}(?P<us>s))?"
        rf"|(?P<min2>\d+)(?P<umin2>['\u2032])(?P<s2>\d+)(?P<us2>[\"\u2033])){_FIN}"
    ),
    _construire_duree,
    _lire_duree,
    _reconnaitre_duree,
    _ecrire_duree,
)

# ── Plage et intervalle ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Plage:
    debut: int
    fin: int


@dataclass(frozen=True)
class Intervalle:
    gauche: str                # borne telle qu'écrite : « 0 », « -1 », « +∞ »
    droite: str
    ouvert_gauche: bool = False
    ouvert_droite: bool = False


def _lire_plage(m: re.Match[str]) -> list[MotLu]:
    """« 1990-2000 », « 12-15 », « 3-2 » : les deux nombres reliés par « à »."""
    mots = lire_chiffres(m.group("a"), list(range(m.start("a"), m.end("a"))))
    mots.append(MotLu("à", m.start("sep"), m.end("sep"), composant=1))
    return mots + _composant(lire_chiffres(m.group("b"), list(range(m.start("b"), m.end("b")))), 2)


PLAGE = TypeFormule(
    "plage",
    re.compile(rf"(?P<a>\d+)(?P<sep>[-\u2013])(?P<b>\d+){_FIN}"),
    lambda m: Plage(int(m.group("a")), int(m.group("b"))),
    _lire_plage,
    lambda elems, i: None,
    lambda v: f"{v.debut}-{v.fin}",
)

_BORNE = r"[-+\u2212]?(?:\d+(?:[,.]\d+)?|∞)"
_BORNE_ENTIERE = r"[-+\u2212]?(?:\d+|∞)"


def _lire_borne(m: re.Match[str], groupe: str, composant: int) -> list[MotLu]:
    texte, debut = m.group(groupe), m.start(groupe)
    mots = []
    if texte[0] in "-\u2212+":
        mots.append(MotLu(MOINS if texte[0] != "+" else "plus", debut, debut + 1))
        texte, debut = texte[1:], debut + 1
    if texte == "∞":
        mots.append(MotLu("l'", debut, debut + 1))
        mots.append(MotLu("infini", debut, debut + 1))
    else:
        nombre = NOMBRE.motif.match(" " * debut + texte, debut)
        mots.extend(NOMBRE.lire(nombre))
    return _composant(mots, composant)


def _lire_intervalle(m: re.Match[str]) -> list[MotLu]:
    """« [0;1] » : de zéro à un. L'ouverture des crochets n'est pas dite."""
    a, sep, b = ("a", "sep", "b") if m.group("a") is not None else ("a2", "sep2", "b2")
    mots = [MotLu("de", m.start("g"), m.end("g"))]
    mots.extend(_lire_borne(m, a, 0))
    mots.append(MotLu("à", m.start(sep), m.end(sep), composant=1))
    return mots + _lire_borne(m, b, 2)


def _construire_intervalle(m: re.Match[str]) -> Intervalle:
    a, b = (m.group("a"), m.group("b")) if m.group("a") is not None else (m.group("a2"), m.group("b2"))
    return Intervalle(a, b, m.group("g") == "]", m.group("d") == "[")


INTERVALLE = TypeFormule(
    "intervalle",
    re.compile(
        rf"(?P<g>[\[\]]){_E}(?:(?P<a>{_BORNE}){_E}(?P<sep>;){_E}(?P<b>{_BORNE})"
        rf"|(?P<a2>{_BORNE_ENTIERE})(?P<sep2>,){_E}(?P<b2>{_BORNE_ENTIERE})){_E}(?P<d>[\[\]])"
    ),
    _construire_intervalle,
    _lire_intervalle,
    lambda elems, i: None,
    lambda v: ("]" if v.ouvert_gauche else "[") + v.gauche + ";" + v.droite + ("[" if v.ouvert_droite else "]"),
)
