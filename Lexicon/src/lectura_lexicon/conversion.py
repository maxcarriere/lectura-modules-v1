# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Conversion d'un lexique au format rapide de Lexicon (``lexicon.db``), pour le mode local.

Sources reconnues (``format``, détecté par défaut) :

- ``lexik`` : LeXiK téléchargée (https://lexique.lectura.world, ORTOLANG ``11403/lexik``), le dossier publié ou
  ``lexik_formes_mots.tsv[.gz]`` ; les fichiers voisins sont lus s'ils sont là (multimots, spéciaux, non classés,
  lemmes, ``provenance/lexik_provenance.tsv.gz``). Français seulement. N'importe quelle version publiée de LeXiK :
  la base obtenue dépend de la version téléchargée.
- ``lexique3`` : Lexique 3 (``Lexique383.tsv`` : ortho, phon ou syll, lemme, cgram, genre, nombre, freqfilms2,
  infover) ; la phonétique de Lexique 3 est convertie en API, syllabée quand la colonne ``syll`` est là.
- ``glaff`` : GLÀFF (``glaff-1.2.2.txt``, champs séparés par « | » : forme, MULTEXT, lemme, API, SAMPA, fréquences).
- ``tableau`` : un CSV ou TSV maison avec une ligne d'en-tête. Colonnes reconnues (mêmes alias que lectura-lexique
  v0) : ``ortho`` (obligatoire ; ou graphie, form, word, forme, flexion), ``phone`` (API ; ou phon, ipa,
  prononciation), ``lemme``, ``upos`` ou ``cgram``, ``feats`` (traits UD) ou ``multext`` ou ``genre`` / ``nombre`` /
  ``mode`` / ``temps`` / ``personne``, ``freq`` (par million ; ou freqfilms2, freq_opensubs…) ou ``zipf``.
  Français ou anglais.

Le format rapide garde : formes et fréquences (indice Zipf = log₁₀(fréquence par million) + 3), prononciations et
clés phonétiques, analyses (lemme, UPOS, traits, MULTEXT), lemmes, index des voisins et des rimes. Toutes les
formes de la source sont gardées. Une forme d'une source validée (LeXiK Mots, Lexique 3, GLÀFF, tableau) est du
« noyau » : elle est acceptée dès que son lemme est courant (zipf ≥ 2), même si elle-même est rare.

Ce que les fichiers publiés de LeXiK ne donnent pas, et que la base Lexicon de Lectura ajoute : les graphies
variantes (marques du Wiktionnaire, corrections écrites à la main) et le niveau « noyau » exact de LeXiK. On peut
donner ses propres variantes (``variantes=`` : TSV forme → graphie usuelle).

Licence des données : la base obtenue dérive de la source et en suit la licence (LeXiK : CC BY-SA 4.0, avec
attribution ; Lexique 3 : CC BY-SA 4.0 ; GLÀFF : CC BY-SA 3.0). Ce module ne contient aucune donnée.

    python -m lectura_lexicon convertir LeXiK/ ma_base/lexicon.db
    python -m lectura_lexicon convertir Lexique383.tsv lexique3.db --format lexique3
"""

from __future__ import annotations

import csv
import gzip
import importlib
import io
import json
import lzma
import math
import re
import sqlite3
import time
from pathlib import Path

from .v0._aliases import ALIAS_MAP, FREQ_PRIORITE

FORMATS = ("auto", "lexik", "lexique3", "glaff", "tableau")

# ── Lecture des fichiers ───────────────────────────────────────────────────────


def ouvrir(chemin: Path):
    """Fichier texte, décompressé à la volée (.gz, .xz)."""
    chemin = Path(chemin)
    if chemin.suffix == ".gz":
        return io.TextIOWrapper(gzip.open(chemin, "rb"), encoding="utf-8-sig", newline="")
    if chemin.suffix == ".xz":
        return io.TextIOWrapper(lzma.open(chemin, "rb"), encoding="utf-8-sig", newline="")
    return open(chemin, encoding="utf-8-sig", newline="")


def _premiere_ligne(chemin: Path) -> str:
    with ouvrir(chemin) as f:
        return f.readline()


def _fichier_lexik(dossier: Path, nom: str) -> Path | None:
    for suffixe in (".tsv.gz", ".tsv", ".tsv.xz"):
        if (dossier / f"{nom}{suffixe}").exists():
            return dossier / f"{nom}{suffixe}"
    return None


def detecter(source: Path) -> str:
    """Format de ``source`` (voir le module)."""
    source = Path(source)
    if source.is_dir():
        if _fichier_lexik(source, "lexik_formes_mots"):
            return "lexik"
        raise ValueError(f"{source} : dossier sans lexik_formes_mots.tsv[.gz] ; donnez le fichier du lexique")
    if source.name.startswith("lexik_formes"):
        return "lexik"
    entete = _premiere_ligne(source)
    if "\t" not in entete and "," not in entete and entete.count("|") >= 4:
        return "glaff"
    colonnes = {c.strip().lower() for c in re.split(r"[\t,;]", entete)}
    if {"ortho", "phon", "cgram", "freqfilms2"} <= colonnes:
        return "lexique3"
    return "tableau"


def _reel(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def zipf(par_million: float) -> float:
    """Indice Zipf d'une fréquence par million de mots (0 pour une fréquence nulle)."""
    return round(math.log10(par_million) + 3, 2) if par_million > 0 else 0.0


def phone_brut(phone: str) -> str:
    """Prononciation brute de LeXiK (§6.4) : sans ``[latentes]`` ni ``*h*``, première valeur des ``{a|b}``."""
    phone = re.sub(r"\[[^\]]*\]", "", phone)
    phone = re.sub(r"\*[^*]*\*", "", phone)
    return re.sub(r"\{([^|}]*)(?:\|[^}]*)?\}", r"\1", phone)


# ── MULTEXT (français) → traits UD ─────────────────────────────────────────────

_GENRE = {"m": "Masc", "f": "Fem"}
_NOMBRE = {"s": "Sing", "p": "Plur"}
_MODE = {"i": "Ind", "s": "Sub", "m": "Imp", "c": "Cnd"}
_TEMPS = {"p": "Pres", "i": "Imp", "f": "Fut", "s": "Past"}
_UPOS_MSD = {"N": "NOUN", "V": "VERB", "A": "ADJ", "R": "ADV", "S": "ADP", "C": "CCONJ", "D": "DET", "P": "PRON",
             "I": "INTJ", "M": "NUM", "X": "X", "F": "PUNCT", "Y": "NOUN"}


def _a(tag: str, i: int) -> str:
    return tag[i] if len(tag) > i else "-"


def upos_multext(tag: str) -> str:
    if not tag:
        return "X"
    if tag[:2] == "Np":
        return "PROPN"
    if tag[:2] == "Va":
        return "AUX"
    if tag[:2] == "Cs":
        return "SCONJ"
    return _UPOS_MSD.get(tag[0], "X")


def traits_multext(tag: str) -> str:
    """Traits UD (``Gender=Masc|Number=Sing``, triés) d'une étiquette MULTEXT du français (LeXiK, GLÀFF)."""
    t: dict[str, str] = {}
    c = tag[:1]
    if c in ("N", "Y"):
        g, n = _a(tag, 2), _a(tag, 3)
    elif c == "A":
        g, n = _a(tag, 3), _a(tag, 4)
    elif c in ("D", "P"):
        if _a(tag, 2) in "123":
            t["Person"] = _a(tag, 2)
        g, n = _a(tag, 3), _a(tag, 4)
    elif c == "V":
        forme, temps = _a(tag, 2), _a(tag, 3)
        if forme == "n":
            t["VerbForm"] = "Inf"
        elif forme in ("p", "g"):
            t["VerbForm"] = "Part"
            t["Tense"] = "Past" if temps == "s" else "Pres"
        elif forme in _MODE:
            t["VerbForm"], t["Mood"] = "Fin", _MODE[forme]
            if temps in _TEMPS:
                t["Tense"] = _TEMPS[temps]
            if _a(tag, 4) in "123":
                t["Person"] = _a(tag, 4)
        g, n = _a(tag, 6), _a(tag, 5)
    else:
        g = n = "-"
    if g in _GENRE:
        t["Gender"] = _GENRE[g]
    if n in _NOMBRE:
        t["Number"] = _NOMBRE[n]
    return "|".join(f"{k}={v}" for k, v in sorted(t.items()))


# ── Lexique 3 ──────────────────────────────────────────────────────────────────

# Code phonétique de Lexique 3 → API (documentation de Lexique 3, « phon »)
LEXIQUE3_API = {
    "a": "a", "i": "i", "y": "y", "u": "u", "o": "o", "O": "ɔ", "e": "e", "E": "ɛ", "°": "ə", "2": "ø", "9": "œ",
    "5": "ɛ̃", "1": "œ̃", "@": "ɑ̃", "§": "ɔ̃", "3": "ə", "j": "j", "8": "ɥ", "w": "w", "p": "p", "b": "b", "t": "t",
    "d": "d", "k": "k", "g": "ɡ", "f": "f", "v": "v", "s": "s", "z": "z", "S": "ʃ", "Z": "ʒ", "m": "m", "n": "n",
    "N": "ɲ", "G": "ŋ", "l": "l", "R": "ʁ", "x": "x", "-": ".",
}
_CGRAM_UPOS = {"NOM": "NOUN", "VER": "VERB", "AUX": "AUX", "ADJ": "ADJ", "ADV": "ADV", "PRE": "ADP", "CON": "CCONJ",
               "ONO": "INTJ", "ART": "DET", "PRO": "PRON", "LIA": "X", "ADJ:num": "NUM"}
_INFOVER_MODE = {"ind": "Ind", "sub": "Sub", "imp": "Imp", "cnd": "Cnd"}
_INFOVER_TEMPS = {"pre": "Pres", "imp": "Imp", "fut": "Fut", "pas": "Past"}


def lexique3_vers_api(phon: str) -> str:
    return "".join(LEXIQUE3_API.get(c, c) for c in phon)


def _upos_cgram(cgram: str) -> str:
    cgram = (cgram or "").strip()
    return _CGRAM_UPOS.get(cgram) or _CGRAM_UPOS.get(cgram.split(":")[0], cgram.upper() or "X")


def _traits_simples(genre: str, nombre: str) -> dict[str, str]:
    t = {}
    if (genre or "")[:1] in _GENRE:
        t["Gender"] = _GENRE[genre[:1]]
    if (nombre or "")[:1] in _NOMBRE:
        t["Number"] = _NOMBRE[nombre[:1]]
    return t


def _joindre(t: dict[str, str]) -> str:
    return "|".join(f"{k}={v}" for k, v in sorted(t.items()))


def traits_infover(infover: str, genre: str = "", nombre: str = "") -> list[str]:
    """Traits UD de chaque analyse d'une cellule ``infover`` de Lexique 3 (« ind:pre:3s;sub:pre:3s; »)."""
    res = []
    for a in (x for x in (infover or "").split(";") if x):
        p = a.split(":")
        mode = p[0]
        if mode == "inf":
            res.append(_joindre({"VerbForm": "Inf"}))
        elif mode == "par":
            t = {"VerbForm": "Part", "Tense": _INFOVER_TEMPS.get(p[1] if len(p) > 1 else "", "Past")}
            t.update(_traits_simples(genre, nombre))
            res.append(_joindre(t))
        elif mode in _INFOVER_MODE:
            t = {"VerbForm": "Fin", "Mood": _INFOVER_MODE[mode]}
            if len(p) > 1 and p[1] in _INFOVER_TEMPS:
                t["Tense"] = _INFOVER_TEMPS[p[1]]
            if len(p) > 2 and p[2][:1] in "123":
                t["Person"] = p[2][0]
                if p[2][1:2] in _NOMBRE:
                    t["Number"] = _NOMBRE[p[2][1]]
            res.append(_joindre(t))
    return res or [""]


# ── Entrées normalisées ────────────────────────────────────────────────────────
# Une entrée : (ortho, lemme, id_lemme, upos, feats, phone, phone_enrichi, fpm_forme, fpm_analyse, multext,
#               table, confiance) ; table ∈ {"mots", "speciaux", "non_classe"} ; fpm = fréquence par million.


def _moyenne(valeurs: list[float]) -> float:
    """Moyenne géométrique des fréquences non nulles des corpus : c'est ainsi que LeXiK calcule son indice Zipf
    (vérifié sur sa base : grand 349, 360 et 796 par million → zipf 5,67)."""
    valeurs = [v for v in valeurs if v > 0]
    return math.exp(sum(math.log(v) for v in valeurs) / len(valeurs)) if valeurs else 0.0


_CORPUS = ("opensubtitles", "wikipedia", "gutenberg")


def multext_lexik(dossier: Path) -> dict[str, str]:
    """Traits UD de chaque étiquette MULTEXT, d'après l'annexe de LeXiK (``annexes/lexik_multext.tsv``) : plus
    précis que ``traits_multext`` (PronType, NumType…). Vide si l'annexe manque."""
    chemin = _fichier_lexik(dossier / "annexes", "lexik_multext")
    if chemin is None:
        return {}
    with ouvrir(chemin) as f:
        return {r["multext"]: r.get("feats") or "" for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}


def lire_lexik(source: Path, non_classes: bool = True):
    """Entrées des fichiers publiés de LeXiK (mots, multimots, spéciaux, non classés de fréquence > 0)."""
    dossier = source if source.is_dir() else source.parent
    traits_annexe = multext_lexik(dossier)
    fichiers = [("mots", _fichier_lexik(dossier, "lexik_formes_mots") or source),
                ("multimots", _fichier_lexik(dossier, "lexik_formes_multimots")),
                ("speciaux", _fichier_lexik(dossier, "lexik_formes_speciaux"))]
    if non_classes:
        fichiers.append(("non_classe", _fichier_lexik(dossier, "lexik_formes_non_classes")))
    for table, chemin in fichiers:
        if chemin is None:
            continue
        with ouvrir(chemin) as f:
            for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                ortho = r.get("ortho") or ""
                if not ortho:
                    continue
                freqs = [_reel(r.get(f"freq_{c}")) for c in _CORPUS]
                fpm = _moyenne(freqs)
                if table == "non_classe" and fpm <= 0:
                    continue
                upos = r.get("upos") or ""
                lemme = r.get("lemme") or ortho
                id_lemme = r.get("id_lemme") or f"{lemme}#{upos}"
                enrichi = r.get("phone") or ""
                brut = phone_brut(enrichi)
                tags = (r.get("multext") or "").split(";")
                parts = [(r.get(f"parts_{c}") or "").split(";") for c in _CORPUS]
                for k, tag in enumerate(tags):
                    # fréquence de l'analyse = fréquence de la graphie × part (§10), moyenne sur les corpus ; sans
                    # part (analyse non observée, locution, forme spéciale) : 0, comme dans la base de LeXiK
                    fpm_a = _moyenne([freqs[c] * _reel(parts[c][k] if k < len(parts[c]) else 0)
                                      for c in range(len(_CORPUS))])
                    traits = traits_annexe[tag] if tag in traits_annexe else traits_multext(tag)
                    yield (ortho, lemme, id_lemme, upos or upos_multext(tag), traits, brut,
                           enrichi if enrichi != brut else "", fpm, fpm_a, tag,
                           "mots" if table == "multimots" else table, r.get("confiance") or "")


def lemmes_lexik(source: Path):
    """Lemmes de ``lexik_lemmes`` en flux : (id_lemme, fréquence par million, masculin, féminin, auxiliaire,
    pronominal, groupe, source de l'auxiliaire, orthographe de 1990) ; l'autre genre seulement pour les noms, les
    propriétés verbales pour les verbes.

    Auxiliaire : celui de LeXiK (source « lexik ») ; sinon déduit par règle (source « regle ») : « être » pour un
    verbe essentiellement pronominal, « avoir » pour les autres (les verbes en « être » sont ceux que LeXiK donne).
    Un emploi pronominal se conjugue toujours avec « être »."""
    dossier = source if source.is_dir() else source.parent
    chemin = _fichier_lexik(dossier, "lexik_lemmes")
    if chemin is None:
        return
    with ouvrir(chemin) as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            p = dict(x.split(":", 1) for x in (r.get("proprietes") or "").split(";") if ":" in x)
            masc = fem = aux = pron = grp = source_aux = None
            if r.get("upos") == "NOUN":
                masc, fem = p.get("masculin") or None, p.get("feminin") or None
            if r.get("upos") in ("VERB", "AUX"):
                aux, pron = p.get("auxiliaire") or None, p.get("pronominal") or None
                grp = int(p["groupe"]) if p.get("groupe", "").isdigit() else None
                source_aux = "lexik" if aux else "regle"
                aux = aux or ("être" if pron == "essentiel" else "avoir")
            yield (r.get("id_lemme") or "", _moyenne([_reel(r.get(f"freq_{c}")) for c in _CORPUS]), masc, fem, aux,
                   pron, grp, source_aux, p.get("ortho_1990") or None)


def lire_lexique3(source: Path):
    with ouvrir(source) as f:
        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            ortho = r.get("ortho") or ""
            if not ortho:
                continue
            upos = _upos_cgram(r.get("cgram", ""))
            lemme = r.get("lemme") or ortho
            fpm = _reel(r.get("freqfilms2"))
            # ``syll`` : prononciation syllabée (« S@-s§ ») quand la colonne est là, sinon ``phon``
            phone = lexique3_vers_api(r.get("syll") or r.get("phon") or "")
            if upos in ("VERB", "AUX"):
                tous = traits_infover(r.get("infover", ""), r.get("genre", ""), r.get("nombre", ""))
            else:
                tous = [_joindre(_traits_simples(r.get("genre", ""), r.get("nombre", "")))]
            for feats in tous:
                yield (ortho, lemme, f"{lemme}#{upos}", upos, feats, phone, "", fpm, fpm / len(tous), "",
                       "mots", "")


def lire_glaff(source: Path):
    with ouvrir(source) as f:
        for ligne in f:
            c = ligne.rstrip("\r\n").split("|")
            if len(c) < 3 or not c[0]:
                continue
            ortho, tag, lemme = c[0], c[1], c[2] or c[0]
            phone = (c[3].split(";")[0] if len(c) > 3 else "")
            fpm = _reel(c[14]) if len(c) > 14 else (_reel(c[10]) if len(c) > 10 else 0.0)
            upos = upos_multext(tag)
            yield (ortho, lemme, f"{lemme}#{upos}", upos, traits_multext(tag), phone, "", fpm, fpm, tag, "mots", "")


def _canonique(colonne: str) -> str:
    c = colonne.strip().lower()
    for canon, alias in ALIAS_MAP.items():
        if c == canon or c in alias:
            return canon
    return c


def lire_tableau(source: Path, separateur: str | None = None, phonetique: str = "api", langue: str = "fr"):
    """CSV/TSV maison (colonnes : voir le module). ``phonetique="lexique3"`` convertit le code de Lexique 3."""
    with ouvrir(source) as f:
        entete = f.readline()
        if separateur is None:
            separateur = "\t" if "\t" in entete else ";" if entete.count(";") > entete.count(",") else ","
        noms = next(csv.reader([entete], delimiter=separateur))
        canons = [_canonique(n) for n in noms]
        if "ortho" not in canons:
            raise ValueError(f"{source} : pas de colonne « ortho » (ou graphie, form, word, forme, flexion) ; "
                             f"colonnes lues : {noms}")
        priorite = [n for n in noms if n.strip().lower() in FREQ_PRIORITE]
        for valeurs in csv.reader(f, delimiter=separateur):
            if not valeurs:
                continue
            r: dict[str, str] = {}
            for nom, canon, v in zip(noms, canons, valeurs):
                if canon == "freq" and "freq" in r and nom not in priorite[:1]:
                    continue
                r.setdefault(canon, v)
            ortho = (r.get("ortho") or "").strip()
            if not ortho:
                continue
            multext = r.get("multext", "")
            upos = r.get("upos") or (_upos_cgram(r["cgram"]) if r.get("cgram") else upos_multext(multext)
                                     if multext else "")
            if r.get("feats"):
                feats = r["feats"]
            elif multext and langue == "fr":
                feats = traits_multext(multext)
            else:
                t = _traits_simples(r.get("genre", ""), r.get("nombre", ""))
                mode = (r.get("mode") or "").lower()
                if mode:
                    t.update(dict(x.split("=") for x in traits_infover(
                        f"{mode[:3]}:{(r.get('temps') or '')[:3].lower()}:{r.get('personne', '')}"
                        f"{(r.get('nombre') or '')[:1]};", r.get("genre", ""), r.get("nombre", ""))[0].split("|")
                        if "=" in x))
                feats = _joindre(t)
            if r.get("zipf"):
                fpm = 10 ** (_reel(r["zipf"]) - 3) if _reel(r["zipf"]) > 0 else 0.0
            else:
                fpm = _reel(r.get("freq"))
            phone = r.get("phone", "")
            if phonetique == "lexique3":
                phone = lexique3_vers_api(phone)
            lemme = r.get("lemme") or ortho
            yield (ortho, lemme, r.get("id_lemme") or f"{lemme}#{upos}", upos, feats, phone_brut(phone),
                   phone if phone_brut(phone) != phone else "", fpm, fpm, multext, "mots", r.get("confiance", ""))


# ── Construction de la base ────────────────────────────────────────────────────


TAILLES = ("complet", "standard", "mini")


SEUIL_MINI = 2.0


def convertir(source, sortie, langue: str = "fr", format: str = "auto", taille: str = "complet",
              zipf_voisins: float | None = None, suppressions: int = 1, separateur: str | None = None,
              phonetique: str = "api", variantes=None, non_classes: bool = False, afficher=None,
              seuil: float = SEUIL_MINI, zipf_lemme_min: float = 2.0) -> Path:
    """Construit ``sortie`` (``lexicon.db`` au format rapide) depuis ``source`` ; rend son chemin.

    ``zipf_voisins`` : fréquence minimale des formes indexées pour les voisins (orthographiques et phonétiques) ;
    ``suppressions`` : lettres supprimées dans l'index des voisins (1 ou 2) ; ``variantes`` : TSV « forme, graphie
    usuelle » (formes acceptées, jamais proposées).

    ``taille`` (même schéma pour toutes, définie par la fréquence de la forme) : ``complet`` (toutes les formes
    validées), ``standard`` (fréquence > 0), ``mini`` (zipf ≥ ``seuil``). Les formes « non classées » de LeXiK
    (jetons de corpus jamais validés) sont exclues, sauf ``non_classes=True`` (drapeau ``non_valide``)."""
    from .local import moteur

    afficher = afficher or (lambda *_: None)
    t0 = time.time()
    source, sortie = Path(source), Path(sortie)
    if sortie.is_dir() or not sortie.suffix:
        sortie = sortie / "lexicon.db"
    langue = langue.lower()
    if taille not in TAILLES:
        raise ValueError(f"taille « {taille} » : attendu {', '.join(TAILLES)}")
    if zipf_voisins is None:
        zipf_voisins = 1.0
    fmt = detecter(source) if format == "auto" else format
    if fmt not in FORMATS[1:]:
        raise ValueError(f"format « {format} » : attendu {', '.join(FORMATS)}")
    if fmt in ("lexik", "lexique3", "glaff") and langue != "fr":
        raise ValueError(f"le format {fmt} est un lexique du français (langue='fr')")
    moteur(langue)

    if fmt == "lexik":
        entrees = lire_lexik(source, non_classes)
        lemmes_source = lemmes_lexik(source)
        rectifiees = set()          # orthographe de 1990 : propriété des lemmes (``ortho_1990``)
    else:
        entrees = {"lexique3": lambda: lire_lexique3(source), "glaff": lambda: lire_glaff(source),
                   "tableau": lambda: lire_tableau(source, separateur, phonetique, langue)}[fmt]()
        lemmes_source, rectifiees = iter(()), set()

    usuelles: dict[str, str] = {}
    if variantes:
        with ouvrir(Path(variantes)) as fv:
            for ligne in fv:
                if ligne.strip() and not ligne.startswith("#"):
                    o, *u = ligne.rstrip("\r\n").split("\t")
                    usuelles[o] = u[0] if u else ""

    meta = {"taille": taille, "langue": langue, "source": source.name, "format_source": fmt,
            "zipf_voisins": zipf_voisins, "suppressions": suppressions,
            "seuil": seuil if taille == "mini" else "", "non_classes": int(non_classes),
            "licence": "celle de la source (LeXiK : CC BY-SA 4.0, avec attribution)" if fmt == "lexik"
            else "celle de la source"}
    return _ecrire(sortie, langue, entrees, lemmes_source, usuelles, fmt, zipf_voisins, suppressions, afficher, t0,
                   taille, seuil, zipf_lemme_min, meta, rectifiees=rectifiees)


def _ecrire(sortie: Path, langue: str, entrees, lemmes_source, usuelles: dict, fmt: str, zipf_voisins: float,
            suppressions: int, afficher, t0: float, taille: str, seuil: float, zipf_lemme_min: float, meta: dict,
            rectifiees=frozenset(), drapeaux_sup=None, americaines=None) -> Path:
    """Écrit la base au format rapide ``sortie`` depuis des entrées normalisées (voir ``_construire``)."""
    from .local import moteur

    pkg = moteur(langue).__name__.rsplit(".", 1)[0]
    cles = importlib.import_module(pkg + ".cles")
    donnees = importlib.import_module(pkg + ".donnees")
    # Mémoire bornée : les entrées passent par une base de travail (``<sortie>.travail``, effacée à la fin), relue
    # triée par graphie ; seuls restent en mémoire les numéros des clés phonétiques et des lemmes.
    sortie.parent.mkdir(parents=True, exist_ok=True)
    provisoire = sortie.with_name(sortie.name + ".tmp")
    travail = sortie.with_name(sortie.name + ".travail")
    for f in (provisoire, travail):
        f.unlink(missing_ok=True)
    db = sqlite3.connect(provisoire)
    db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=FILE;"
                     "PRAGMA cache_size=-65536;" + donnees.SCHEMA)
    db.execute("ATTACH DATABASE ? AS t", (str(travail),))
    db.executescript(
        "PRAGMA t.journal_mode=OFF; PRAGMA t.synchronous=OFF;"
        "CREATE TABLE t.entrees (ortho TEXT, lemme TEXT, id_lemme TEXT, upos TEXT, feats TEXT, phone TEXT,"
        " enrichi TEXT, fpm REAL, fpm_a REAL, msd TEXT, tbl TEXT, confiance TEXT, marque TEXT);"
        "CREATE TABLE t.lemmes_src (id_lemme TEXT PRIMARY KEY, zipf REAL, masculin TEXT, feminin TEXT,"
        " auxiliaire TEXT, pronominal TEXT, groupe INTEGER, auxiliaire_source TEXT, ortho_1990 TEXT);"
        "CREATE TABLE t.voisins (cle INTEGER, forme INTEGER);"
        "CREATE TABLE t.voisins_phones (cle INTEGER, phone INTEGER);")
    try:
        _construire(db, entrees, lemmes_source, rectifiees, usuelles, fmt, langue, cles, donnees, zipf_voisins,
                    suppressions, afficher, t0, taille, seuil, zipf_lemme_min, drapeaux_sup or {}, americaines or {})
        meta = {**meta, "construit": time.strftime("%Y-%m-%d %H:%M"), "convertisseur": "lectura_lexicon.conversion"}
        db.executemany("INSERT INTO metadonnees VALUES (?,?)",
                       [(k, json.dumps(v) if not isinstance(v, str) else v) for k, v in meta.items()])
        db.executescript(
            "CREATE INDEX idx_formes_min ON formes (min); CREATE UNIQUE INDEX idx_cles_phone ON cles_phone (cle);"
            "CREATE INDEX idx_cles_inverse ON cles_phone (inverse);"
            + ("CREATE INDEX idx_formes_anagramme ON formes (anagramme);"
               "CREATE INDEX idx_analyses_syllabes ON analyses (syllabes, zipf);"
               "CREATE INDEX idx_analyses_forme ON analyses (forme); CREATE INDEX idx_analyses_lemme ON analyses (lemme);"
               "CREATE INDEX idx_analyses_phone ON analyses (phone);"
               "CREATE INDEX idx_lemmes_lemme ON lemmes (lemme); CREATE INDEX idx_lemmes_id ON lemmes (id_lemme);")
            + ("CREATE INDEX idx_americaines ON americaines (americaine);" if langue == "en" else ""))
        db.commit()
        db.execute("DETACH DATABASE t")
        db.execute("VACUUM")
        n_formes = db.execute("SELECT COUNT(*) FROM formes").fetchone()[0]
    finally:
        db.close()
        travail.unlink(missing_ok=True)
    provisoire.replace(sortie)
    afficher(f"{sortie} : {n_formes} formes, {sortie.stat().st_size / 1e6:.1f} Mo ({time.time() - t0:.0f} s)")
    return sortie


_LOT = 20_000


def _par_lots(lignes, taille: int = _LOT):
    lot = []
    for x in lignes:
        lot.append(x)
        if len(lot) >= taille:
            yield lot
            lot = []
    if lot:
        yield lot


def _construire(db, entrees, lemmes_source, rectifiees, usuelles, fmt, langue, cles, donnees, zipf_voisins,
                n_suppr, afficher, t0, taille: str = "complet", seuil: float = SEUIL_MINI,
                zipf_lemme_min: float = 2.0, drapeaux_sup: dict | None = None, americaines: dict | None = None) -> None:
    """Écrit les tables de ``db`` (schéma de la langue) depuis les entrées, en passant par la base de travail ``t``."""
    from itertools import groupby

    # 1. Entrées et lemmes de la source, en flux
    n = 0
    for lot in _par_lots(entrees):
        n += len(lot)
        db.executemany("INSERT INTO t.entrees VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       [x if len(x) == 13 else (*x, None) for x in lot])
    if not n:
        raise ValueError(f"aucune entrée lue (format {fmt})")
    for lot in _par_lots(lemmes_source):
        db.executemany("INSERT OR REPLACE INTO t.lemmes_src VALUES (?,?,?,?,?,?,?,?,?)",
                       [(x[0], zipf(x[1]), *x[2:], *(None,) * (9 - len(x))) for x in lot])
    afficher(f"{n} entrées lues ({time.time() - t0:.0f} s)")

    # 2. Zipf des lemmes absents de la source des lemmes : somme des analyses, dans l'ordre de lecture
    db.execute("CREATE INDEX t.idx_entrees_lemme ON entrees (id_lemme)")

    def sommes():
        for id_lemme, groupe in groupby(db.execute(
                "SELECT id_lemme, fpm_a FROM t.entrees ORDER BY id_lemme, rowid"), key=lambda r: r[0]):
            yield id_lemme, zipf(sum(r[1] for r in groupe))

    lecture = db.cursor()
    for lot in _par_lots(sommes()):
        lecture.executemany("INSERT OR IGNORE INTO t.lemmes_src (id_lemme, zipf) VALUES (?,?)", lot)

    # 3. Une passe par graphie (ordre binaire = ordre des chaînes Python), analyses dans l'ordre de lecture
    db.execute("CREATE INDEX t.idx_entrees_ortho ON entrees (ortho)")
    francais = langue == "fr"
    codes: dict[tuple[str, str], int] = {}
    effectifs: dict[str, int] = {}

    def code(espace: str, valeur: str) -> int:
        if (espace, valeur) not in codes:
            codes[(espace, valeur)] = effectifs.get(espace, 0)
            effectifs[espace] = codes[(espace, valeur)] + 1
        return codes[(espace, valeur)]

    ids_lemmes: dict[str, int] = {}
    ids_cles: dict[str, int] = {}
    cles_voisines: set[int] = set()
    formes_l, analyses_l, phones_l, voisins_l, usuelles_l, americaines_l = [], [], [], [], [], []
    ecriture = db.cursor()
    insertion_analyses = None

    def vider(force: bool = False) -> None:
        nonlocal insertion_analyses
        if force or len(analyses_l) >= _LOT:
            ecriture.executemany("INSERT INTO formes VALUES (?,?,?,?,?,?,?,?)", formes_l)
            if analyses_l:
                insertion_analyses = insertion_analyses or \
                    f"INSERT INTO analyses VALUES ({','.join('?' * len(analyses_l[0]))})"
                ecriture.executemany(insertion_analyses, analyses_l)
            ecriture.executemany("INSERT INTO phones VALUES (?,?,?)" if francais else "INSERT INTO phones VALUES (?,?)",
                                 phones_l)
            ecriture.executemany("INSERT INTO t.voisins VALUES (?,?)", voisins_l)
            for liste in (formes_l, analyses_l, phones_l, voisins_l):
                liste.clear()

    requete = ("SELECT e.ortho, e.lemme, e.id_lemme, e.upos, e.feats, e.phone, e.enrichi, e.fpm, e.fpm_a, e.msd, e.tbl,"
               " e.confiance, l.zipf, e.marque, l.ortho_1990 FROM t.entrees e LEFT JOIN t.lemmes_src l ON l.id_lemme = e.id_lemme"
               " ORDER BY e.ortho, e.rowid")
    i = -1
    for ortho, groupe in groupby(db.execute(requete), key=lambda r: r[0]):
        analyses = list(groupe)
        fpm, drapeaux, classee = 0.0, donnees.PROPRE_SEUL, False
        rectifiee = False
        for _o, _l, _il, upos, _f, _p, _e, fpm_f, fpm_a, _m, tbl, _c, _z, _mq, o1990 in analyses:
            rectifiee = rectifiee or o1990 == "rectifiee"
            fpm = max(fpm, fpm_f) if fmt in ("lexik", "nue") else fpm + fpm_a
            if tbl != "non_classe":
                classee = True
                drapeaux |= donnees.NOYAU
            if upos != "PROPN":
                drapeaux &= ~donnees.PROPRE_SEUL
            if tbl == "speciaux":
                drapeaux |= donnees.SPECIAL
        if not classee:
            drapeaux |= donnees.NON_VALIDE
        drapeaux |= (drapeaux_sup or {}).get(ortho, 0)
        z = zipf(fpm)
        zl = max((a[12] or 0.0 for a in analyses), default=0.0)
        if (taille == "standard" and z <= 0) or (taille == "mini" and z < seuil):
            continue
        i += 1
        if ortho in usuelles:
            drapeaux |= donnees.VARIANTE
            if usuelles[ortho]:
                usuelles_l.append((i, usuelles[ortho]))
        if (rectifiee or ortho in rectifiees) and hasattr(donnees, "RECTIFIEE"):
            drapeaux |= donnees.RECTIFIEE
        if americaines and ortho in americaines:
            americaines_l.append((i, americaines[ortho]))
        if drapeaux & donnees.NOYAU and zl >= zipf_lemme_min:
            drapeaux |= donnees.ACCEPTEE_NOYAU
        vue = any(zipf(a[8]) > 0 for a in analyses)
        cles_forme: list[int] = []
        masquees: dict[int, int] = {}
        vues_analyses = set()
        for _o, lemme, id_lemme, upos, feats, phone, enrichi, _f, fpm_a, msd, _t, confiance, _z, marque, _r in analyses:
            if id_lemme is None or (id_lemme, feats, phone) in vues_analyses:     # forme sans analyse
                continue
            vues_analyses.add((id_lemme, feats, phone))
            zipf_a = zipf(fpm_a)
            masquee = int(vue and zipf_a <= 0)
            if phone:
                k = ids_cles.setdefault(cles.cle_phone(phone), len(ids_cles))
                if k not in masquees:
                    cles_forme.append(k)
                    masquees[k] = masquee
                else:
                    masquees[k] = min(masquees[k], masquee)
                if z >= zipf_voisins and not drapeaux & donnees.NON_VALIDE:
                    cles_voisines.add(k)
            j = ids_lemmes.setdefault(id_lemme, len(ids_lemmes))
            ligne = [i, j, code("upos", upos), code("traits", feats), phone, zipf_a, masquee, enrichi or None, None,
                     confiance or None, cles.nombre_syllabes(phone)]
            if francais:
                ligne.append(code("multext", msd))
            ligne.append(marque or None)
            analyses_l.append(tuple(ligne))
        phones_l.extend((k, i, m) if francais else (k, i) for k, m in masquees.items())
        mini = cles.minuscule(ortho)
        formes_l.append((i, ortho, mini, z, zl, drapeaux, " ".join(map(str, cles_forme)),
                         cles.anagramme(ortho) or None))
        if (z >= zipf_voisins and " " not in mini and len(mini) >= 2
                and not drapeaux & (donnees.SPECIAL | donnees.NON_VALIDE)):
            voisins_l.extend((cles.empreinte(s), i) for s in cles.suppressions(mini, n_suppr))
        vider()
    vider(force=True)
    afficher(f"{i + 1} formes écrites ({time.time() - t0:.0f} s)")

    db.executemany("INSERT INTO usuelles VALUES (?,?)", sorted(usuelles_l))
    if americaines_l:
        db.executemany("INSERT INTO americaines VALUES (?,?)", americaines_l)
    db.executemany("INSERT INTO cles_phone VALUES (?,?,?)",
                   ((k, c, cles.inverse(c)) for c, k in ids_cles.items()))
    db.executemany("INSERT INTO t.voisins_phones VALUES (?,?)",
                   ((cles.empreinte(s), k) for c, k in ids_cles.items() if k in cles_voisines
                    for s in cles.suppressions(cles.phonemes(c), n_suppr)))
    del ids_cles, cles_voisines
    db.execute("INSERT INTO voisins SELECT DISTINCT cle, forme FROM t.voisins ORDER BY cle, forme")
    db.execute("INSERT INTO voisins_phones SELECT DISTINCT cle, phone FROM t.voisins_phones ORDER BY cle, phone")
    db.execute("CREATE TABLE t.ids_lemmes (j INTEGER, id_lemme TEXT, lemme TEXT, upos TEXT)")
    db.executemany("INSERT INTO t.ids_lemmes VALUES (?,?,?,?)",
                   ((j, il, il.split("#")[0], (il.split("#") + [""])[1]) for il, j in ids_lemmes.items()))
    del ids_lemmes
    db.execute("INSERT INTO lemmes (id, id_lemme, lemme, upos, zipf, masculin, feminin, auxiliaire, pronominal,"
               " groupe, auxiliaire_source, ortho_1990) SELECT i.j, i.id_lemme, i.lemme, i.upos, COALESCE(l.zipf, 0.0),"
               " l.masculin, l.feminin, l.auxiliaire, l.pronominal, l.groupe, l.auxiliaire_source, l.ortho_1990"
               " FROM t.ids_lemmes i LEFT JOIN t.lemmes_src l"
               " ON l.id_lemme = i.id_lemme ORDER BY i.j")
    db.executemany("INSERT INTO codes VALUES (?,?,?)", [(e, j, v) for (e, v), j in codes.items()])
    afficher(f"index des voisins et lemmes écrits ({time.time() - t0:.0f} s)")
