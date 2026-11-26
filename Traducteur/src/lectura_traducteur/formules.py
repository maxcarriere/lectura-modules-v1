# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Formules (nombres, monnaies, heures, dates, pourcentages, ordinaux, mesures) : conversion déterministe d'une
convention d'écriture à l'autre (fr ⇄ en), pour les protéger pendant la traduction.

Les formules sont repérées par le découpage des Modules (``type == "formule"``, ``type_formule``) ; on les remplace
par un repère que le traducteur recopie, puis on remet la forme convertie. ``convertir`` rend ``None`` quand on ne
sait pas faire : la formule est alors laissée au traducteur.
"""
from __future__ import annotations

import re

MOIS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"]
MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
           "novembre", "décembre"]
ABR_EN = {m[:3].lower(): i for i, m in enumerate(MOIS_EN)} | {"sept": 8}
DEVISES = {"$": ("$", "dollars"), "£": ("£", "livres"), "€": ("€", "euros"), "¥": ("¥", "yens")}
ECHELLES_EN = {"m": "million", "mn": "million", "million": "million", "bn": "billion", "b": "billion",
               "billion": "billion", "k": "thousand", "thousand": "thousand", "trillion": "trillion", "tn": "trillion"}
ECHELLES_FR = {"million": "millions", "billion": "milliards", "trillion": "billions", "thousand": "mille"}
ECHELLES_FR_EN = {"million": "million", "millions": "million", "milliard": "billion", "milliards": "billion",
                  "mille": "thousand", "md": "billion", "mds": "billion", "m": "million"}
UNITES_EN_FR = {"ft": "pieds", "feet": "pieds", "foot": "pied", "in": "pouces", "inches": "pouces", "mi": "miles",
                "miles": "miles", "lb": "livres", "lbs": "livres", "mph": "mi/h"}
UNITES_COURANTES = {"pieds", "pied", "pouces", "pouce", "milles", "miles", "mile", "km", "m", "cm", "mm", "kg", "g",
                    "lb", "lbs", "livres", "mètres", "kilomètres", "ft", "feet", "foot", "inches", "in", "metres",
                    "meters", "kilometres", "kilometers", "mph", "km/h", "mi"}
ESP = " "  # espace insécable : 1 200, 3,50 €, 18 %


# --- nombres ---
def lire_nombre(t: str, langue: str) -> tuple[str, str] | None:
    """« 1,200.5 » (en) / « 1 200,5 » (fr) → (« 1200 », « 5 »)."""
    t = t.strip().replace(" ", " ").replace(" ", " ")
    if langue == "en":
        m = re.fullmatch(r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?", t)
        return (m.group(1).replace(",", ""), m.group(2) or "") if m else None
    m = re.fullmatch(r"(\d{1,3}(?: \d{3})+|\d+)(?:,(\d+))?", t)
    if not m:
        m = re.fullmatch(r"(\d{1,3}(?:\.\d{3})+)", t)  # 1.200 (fr, rare)
        return (m.group(1).replace(".", ""), "") if m else None
    return m.group(1).replace(" ", ""), m.group(2) or ""


def ecrire_nombre(entier: str, dec: str, langue: str, annee: bool = False, grouper4: bool = True) -> str:
    if annee or len(entier) <= 3 or (len(entier) == 4 and not grouper4):
        e = entier
    else:
        groupes = []
        while entier:
            groupes.insert(0, entier[-3:])
            entier = entier[:-3]
        e = (ESP if langue == "fr" else ",").join(groupes)
    return e + ((("," if langue == "fr" else ".") + dec) if dec else "")


def _nombre(t: str, s: str, c: str) -> str | None:
    v = lire_nombre(t, s)
    # 4 chiffres : groupés seulement si la source les groupait (1,200 → 1 200 ; 2012 → 2012)
    return ecrire_nombre(*v, c, grouper4=bool(re.search(r"\d[ ,.\u00a0\u202f]\d{3}", t))) if v else None


# --- par type ---
def _monnaie(t: str, s: str, c: str) -> str | None:
    t = t.replace(" ", " ").replace(" ", " ").strip()
    if s == "en":
        m = re.fullmatch(r"(US|C|A|NZ|HK)?([$£€¥])\s?([\d.,]+)\s?([a-zA-Z]+)?", t)
        if not m:
            return None
        pays, sym, n, ech = m.groups()
        v = lire_nombre(n, "en")
        if not v:
            return None
        nombre = ecrire_nombre(*v, "fr")
        nom = DEVISES[sym][1]
        if pays == "US":
            nom = "dollars américains"
        elif pays and sym == "$":
            nom = {"C": "dollars canadiens", "A": "dollars australiens", "NZ": "dollars néo-zélandais",
                   "HK": "dollars de Hong Kong"}[pays]
        if ech:
            e = ECHELLES_EN.get(ech.lower())
            if not e:
                return None
            pluriel = int(v[0]) >= 2
            mot = ECHELLES_FR[e] if pluriel or e == "thousand" else ECHELLES_FR[e].rstrip("s")
            return f"{nombre} {mot} d'{nom}" if nom[0] in "aeéiouy" else f"{nombre} {mot} de {nom}"
        return f"{nombre}{ESP}{sym}" if not pays else f"{nombre} {nom}"
    m = re.fullmatch(r"([\d ,.]+?)\s?(millions?|milliards?|mds?|M|Md)?\s?(?:d['’]|de )?\s?([$£€¥]|euros?|dollars?)(?:\s?(US|CA|canadiens?|américains?))?", t)
    if not m:
        return None
    n, ech, dev, pays = m.groups()
    v = lire_nombre(n.strip(), "fr")
    if not v:
        return None
    sym = {"euro": "€", "euros": "€", "dollar": "$", "dollars": "$"}.get(dev, dev)
    pre = {"US": "US", "CA": "C", "canadien": "C", "canadiens": "C"}.get(pays or "", "")
    ech_en = ECHELLES_FR_EN.get((ech or "").lower(), "")
    return f"{pre}{sym}{ecrire_nombre(*v, 'en')}" + (f" {ech_en}" if ech_en else "")


def _pourcentage(t: str, s: str, c: str) -> str | None:
    m = re.fullmatch(r"([\d.,   ]+?)\s?%", t)
    if not m:
        return None
    n = _nombre(m.group(1), s, c)
    return None if n is None else (f"{n}{ESP}%" if c == "fr" else f"{n}%")


def _heure(t: str, s: str, c: str) -> str | None:
    t = t.strip().rstrip(".")
    if s == "en":
        m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?\s?([ap])\.?\s?m\.?|(\d{1,2}):(\d{2})", t, re.I)
        if not m:
            return None
        if m.group(4):
            h, mn = int(m.group(4)), m.group(5)
        else:
            h, mn = int(m.group(1)), m.group(2) or ""
            ap = m.group(3).lower()
            h = (0 if h == 12 else h) + (12 if ap == "p" else 0)
        return f"{h}{ESP}h" + (f"{ESP}{mn}" if mn and mn != "00" else "")
    m = re.fullmatch(r"(\d{1,2})\s?h\s?(\d{2})?", t)
    if not m:
        return None
    h, mn = int(m.group(1)), m.group(2) or ""
    if h > 23:
        return None
    suf = "a.m." if h < 12 else "p.m."
    h12 = h % 12 or 12
    return f"{h12}:{mn} {suf}" if mn and mn != "00" else f"{h12} {suf}"


def _ordinal(t: str, s: str, c: str) -> str | None:
    if s == "en":
        m = re.fullmatch(r"(\d+)(st|nd|rd|th)", t)
        return None if not m else (m.group(1) + ("er" if m.group(1) == "1" else "e"))
    m = re.fullmatch(r"(\d+)(?:e|ème|eme|er|re|ère)", t)
    if not m:
        return None
    n = int(m.group(1))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _date(t: str, s: str, c: str) -> str | None:
    t = t.strip()
    if re.fullmatch(r"\d{4}", t):
        return t
    if s == "en":
        m = re.fullmatch(r"(\d{4})s", t)
        if m:
            return f"années {m.group(1)}"
        m = re.fullmatch(r"([A-Z][a-z]+)\.?\s(\d{1,2})(?:st|nd|rd|th)?(?:\s?[-–]\s?(\d{1,2}))?(?:,?\s(\d{4}))?", t)
        if m and m.group(1)[:4].lower().rstrip(".")[:3] in ABR_EN:
            mois = MOIS_FR[ABR_EN[m.group(1)[:3].lower()]]
            j = "1er" if m.group(2) == "1" else m.group(2)
            j += f"-{m.group(3)}" if m.group(3) else ""
            return f"{j} {mois}" + (f" {m.group(4)}" if m.group(4) else "")
        m = re.fullmatch(r"(\d{1,2})\s([A-Z][a-z]+)(?:,?\s(\d{4}))?", t)  # 3 March 2024 (britannique)
        if m and m.group(2)[:3].lower() in ABR_EN:
            j = "1er" if m.group(1) == "1" else m.group(1)
            return f"{j} {MOIS_FR[ABR_EN[m.group(2)[:3].lower()]]}" + (f" {m.group(3)}" if m.group(3) else "")
        m = re.fullmatch(r"([A-Z][a-z]+)\s(\d{4})", t)
        if m and m.group(1)[:3].lower() in ABR_EN:
            return f"{MOIS_FR[ABR_EN[m.group(1)[:3].lower()]]} {m.group(2)}"
        return None
    m = re.fullmatch(r"(?:années\s)?(\d{4})", t)
    if m and t.startswith("années"):
        return f"{m.group(1)}s"
    m = re.fullmatch(r"(\d{1,2})(?:er)?(?:\s?[-–]\s?(\d{1,2}))?\s([a-zéû]+)(?:\s(\d{4}))?", t)
    if m and m.group(3) in MOIS_FR:
        mois = MOIS_EN[MOIS_FR.index(m.group(3))]
        j = m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")
        return f"{mois} {j}" + (f", {m.group(4)}" if m.group(4) else "")
    m = re.fullmatch(r"([a-zéû]+)\s(\d{4})", t)
    if m and m.group(1) in MOIS_FR:
        return f"{MOIS_EN[MOIS_FR.index(m.group(1))]} {m.group(2)}"
    return None


def _mesure(t: str, s: str, c: str) -> str | None:
    m = re.fullmatch(r"([\d.,   ]+?)\s?([^\d\s].*)", t)
    if not m:
        return None
    n = _nombre(m.group(1), s, c)
    if n is None:
        return None
    u = m.group(2)
    if s == "en" and c == "fr":
        u = UNITES_EN_FR.get(u, u)
    return f"{n}{ESP if c == 'fr' else ' '}{u}"


CONVERTISSEURS = {"nombre": _nombre, "monnaie": _monnaie, "pourcentage": _pourcentage, "heure": _heure,
                  "ordinal": _ordinal, "date": _date, "mesure": _mesure}


def convertir(forme: str, type_formule: str, source: str, cible: str) -> str | None:
    f = CONVERTISSEURS.get(type_formule)
    if f is None:
        return None
    try:
        return f(forme, source, cible)
    except (ValueError, KeyError, IndexError):
        return None



# --- substituts typés (dates, heures) : le traducteur gère la préposition, on remplace ensuite ---
def substitut(type_formule: str, forme: str, conv: str, source: str, n: int) -> tuple[str, str] | None:
    """(substitut à mettre dans la source, motif regex qui le retrouve dans la traduction) ; ``None`` : repère
    numérique ordinaire. ``n`` : rang du substitut dans la phrase (0, 1, 2…)."""
    if type_formule == "heure":
        h = 21 + n  # 21 h, 22 h, 23 h : rares dans les textes, faciles à retrouver
        if n > 2:
            return None
        if source == "en":
            return f"{h - 12} p.m.", rf"(?<![\d:]){h}\s?h(?:eures?)?(?:\s?00)?(?!\s?\d)"
        return f"{h} h", (rf"(?<![\d:]){h - 12}(?::00)?\s?(?:p\.\s?m\.?|pm|PM|P\.M\.)|(?<![\d:]){h}:00|(?<![\d:]){h}h"
                          rf"|(?<![\d:.,]){h - 12}:00(?!\s?[ap]\.?m)|(?<![\d:.,]){h - 12} o'clock")
    if type_formule == "monnaie":
        sym = next((c for c in forme if c in DEVISES), None) or next(
            (c for c in conv if c in DEVISES), None)
        if sym is None or n > 9:
            return None
        k = 971 + n
        noms = "dollars?|euros?|livres?(?: sterling)?|yens?|pounds?|dollars? américains"
        motif = rf"(?:[$€£¥]\s?)?(?<![\w.,]){k}(?![\w]|[.,]\d)(?:\s?(?:[$€£¥]|(?:de |d')?(?:{noms})))?"
        return (f"{sym}{k}" if source == "en" else f"{k}{ESP}{sym}"), motif
    if type_formule == "mesure":
        m = re.fullmatch(r"[\d.,\s\u00a0\u202f]+?\s?([^\d\s].*)", forme)
        if not m or n > 9:
            return None
        u_src = m.group(1)
        u_cib = conv.replace("\u00a0", " ").split()[-1]
        unites = {u_src, u_cib} | UNITES_COURANTES
        alt = "|".join(sorted((re.escape(u) for u in unites), key=len, reverse=True))
        k = 951 + n
        return f"{k} {u_src}", rf"(?<![\w.,]){k}(?:\s?(?:{alt})(?![\w]))?"
    if type_formule != "date" or re.fullmatch(r"\d{4}", forme):
        return None
    j = 13 + n  # 13, 14… janvier
    if source == "en":
        if conv.startswith("années"):
            a = 1910 + 10 * n
            return f"{a}s", rf"années\s{a}"
        if re.match(r"\d", conv):
            return f"January {j}", rf"{j}\s+janvier"
        return f"January {1897 + n}", rf"janvier\s+{1897 + n}"
    if conv.startswith("the "):
        a = 1910 + 10 * n
        return f"années {a}", rf"(?:the\s)?{a}s"
    if re.match(r"[A-Z][a-z]+ \d", conv):
        return f"{j} janvier", rf"January\s+{j}(?:th)?|(?:the\s)?{j}(?:th)?\s+(?:of\s)?January"
    return f"janvier {1897 + n}", rf"January\s+{1897 + n}"
