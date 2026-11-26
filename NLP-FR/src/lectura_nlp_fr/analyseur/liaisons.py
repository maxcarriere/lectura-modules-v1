# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Liaison entre deux mots : la règle qui s'applique, et ce que cela donne.

Les contextes viennent de LeXiK (``liaisons_contextes.tsv``, spec 02 §10, validés par
l'utilisateur) : statut et fréquence sont lus dans la table, les conditions sont codées ici.
La première règle dont les conditions sont remplies s'applique.

Une liaison n'est possible que si le mot de gauche a une consonne latente et si celui de
droite commence par une voyelle ou une semi-voyelle ; la règle dit ensuite si elle est
interdite, obligatoire ou facultative.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Callable

from .index_phone import cle_de, forme_liee
from .tokeniseur import VOYELLES

INTERDITE, OBLIGATOIRE, FACULTATIVE = "interdite", "obligatoire", "facultative"
_SEMI_VOYELLES = frozenset("jwɥ")
_VERBE = ("VERB", "AUX")


@dataclass(frozen=True)
class MotAnalyse:
    """Ce que la décision de liaison a besoin de savoir d'un mot."""

    forme: str
    upos: str
    phone: str                            # prononciation en isolation, syllabée ou non
    latente: str = ""                     # marque du cadre : « [z] », « [ɔ̃>ɔn] », « [s>z;s>] »
    h_aspire: bool = False
    lemme: str = ""
    feats: dict[str, str] = field(default_factory=dict)

    @property
    def f(self) -> str:
        return self.forme.lower()

    @property
    def syllabes(self) -> int:
        return sum(1 for c in self.phone if c in VOYELLES)


@dataclass(frozen=True)
class Jonction:
    regle: str               # identifiant de la règle appliquée, « » si aucune liaison n'est possible
    statut: str
    frequence: str = ""
    forme_liee: str = ""     # prononciation du mot de gauche en liaison (« lez », « diz », « bɔn »)

    def realisee(self, politique: "Politique") -> bool:
        return bool(self.forme_liee) and politique.realise(self)


@dataclass(frozen=True)
class Politique:
    """Quelles liaisons facultatives sont faites."""

    frequences: frozenset[str]

    def realise(self, j: Jonction) -> bool:
        return j.statut == OBLIGATOIRE or (j.statut == FACULTATIVE and j.frequence in self.frequences)


# Lecture à voix haute : les obligatoires et les facultatives fréquentes.
LECTURE = Politique(frozenset({"fréquente"}))
MINIMALE = Politique(frozenset())
SOUTENUE = Politique(frozenset({"fréquente", "courante", "rare"}))

Condition = Callable[[MotAnalyse, MotAnalyse], bool]


def _dans(*formes: str) -> frozenset[str]:
    return frozenset(formes)


_BLOQUANTS = _dans("onze", "onzième", "oui", "huit", "huitième", "yaourt", "yacht", "yoga", "whisky", "week-end")
_CLITIQUES_POSTPOSES = _dans("-ils", "-elles", "-on", "-nous", "-vous", "-il", "-elle")
_CLITIQUES_PREVERBAUX = _dans("nous", "vous", "ils", "elles", "on", "les", "en", "y")

# Identifiant → (texte de la table au moment du codage, condition).
_REGLES: dict[str, tuple[tuple[str, str, str, str], Condition]] = {
    "L01": (("*", "", "*", "h aspiré (marque h de phone_var)"), lambda g, d: d.h_aspire),
    "L02": (
        ("*", "", "*", "forme ∈ {onze, onzième, oui, huit, huitième, un (numéral nom), yaourt, yacht, yoga, whisky, week-end}"),
        lambda g, d: d.f in _BLOQUANTS or (d.f == "un" and d.upos == "NOUN"),
    ),
    "L03": (("CCONJ", "forme = et", "*", ""), lambda g, d: g.upos == "CCONJ" and g.f == "et"),
    "L04": (("NOUN", "Number=Sing", "*", ""), lambda g, d: g.upos == "NOUN" and g.feats.get("Number") == "Sing"),
    "L05": (("PROPN", "", "*", ""), lambda g, d: g.upos == "PROPN"),
    "L06": (
        ("PRON", "clitique sujet postposé (-ils, -elles, -on, -nous, -vous, -il, -elle)", "*", ""),
        lambda g, d: g.upos == "PRON" and g.f in _CLITIQUES_POSTPOSES,
    ),
    "L07": (
        ("ADV", "forme ∈ {quand, comment, combien} interrogatifs", "VERB,AUX", ""),
        lambda g, d: g.upos == "ADV" and g.f in _dans("quand", "comment", "combien") and d.upos in _VERBE,
    ),
    "L10": (
        ("DET", "", "NOUN,PROPN,ADJ,PRON,NUM,ADV", ""),
        lambda g, d: g.upos == "DET" and d.upos in ("NOUN", "PROPN", "ADJ", "PRON", "NUM", "ADV"),
    ),
    "L11": (("NUM", "", "NOUN,ADJ", ""), lambda g, d: g.upos == "NUM" and d.upos in ("NOUN", "ADJ")),
    "L12": (
        ("ADJ", "antéposé (suivi du nom qu'il qualifie)", "NOUN", ""),
        lambda g, d: g.upos == "ADJ" and d.upos == "NOUN",
    ),
    "L13": (
        ("PRON", "clitique préverbal (nous, vous, ils, elles, on, les, en, y)", "VERB,AUX,PRON", "à droite : verbe, ou clitique en / y"),
        lambda g, d: g.upos == "PRON"
        and g.f in _CLITIQUES_PREVERBAUX
        and (d.upos in _VERBE or (d.upos == "PRON" and d.f in _dans("en", "y"))),
    ),
    "L14": (
        ("VERB,AUX", "", "PRON", "clitique postposé (-il, -elle, -on, -ils, -elles, -y, -en)"),
        lambda g, d: g.upos in _VERBE
        and d.upos == "PRON"
        and d.f in _dans("-il", "-elle", "-on", "-ils", "-elles", "-y", "-en"),
    ),
    "L15": (
        ("ADP", "monosyllabe (en, dans, chez, sans, sous, dès)", "*", ""),
        lambda g, d: g.upos == "ADP" and g.syllabes == 1,
    ),
    "L16": (
        ("ADV", "forme ∈ {très, tout, plus, moins, bien}", "ADJ,ADV,VERB", "à droite : adjectif, adverbe ou participe"),
        lambda g, d: g.upos == "ADV"
        and g.f in _dans("très", "tout", "plus", "moins", "bien")
        and (d.upos in ("ADJ", "ADV") or (d.upos == "VERB" and d.feats.get("VerbForm") == "Part")),
    ),
    "L29": (("ADV", "forme = très", "NOUN", ""), lambda g, d: g.upos == "ADV" and g.f == "très" and d.upos == "NOUN"),
    "L17": (("SCONJ", "forme = quand", "*", ""), lambda g, d: g.upos == "SCONJ" and g.f == "quand"),
    "L18": (
        ("PRON", "forme ∈ {dont, tout, rien}", "*", ""),
        lambda g, d: g.upos == "PRON" and g.f in _dans("dont", "tout", "rien"),
    ),
    "L19": (("AUX,VERB", "lemme = être", "*", ""), lambda g, d: g.upos in _VERBE and g.lemme == "être"),
    "L20": (
        ("AUX", "lemme = avoir", "VERB", ""),
        lambda g, d: g.upos == "AUX" and g.lemme == "avoir" and d.upos == "VERB",
    ),
    "L21": (
        ("ADV", "forme ∈ {pas, trop, jamais, assez, fort, point}", "*", ""),
        lambda g, d: g.upos == "ADV" and g.f in _dans("pas", "trop", "jamais", "assez", "fort", "point"),
    ),
    "L22": (
        ("NOUN", "Number=Plur", "ADJ", ""),
        lambda g, d: g.upos == "NOUN" and g.feats.get("Number") == "Plur" and d.upos == "ADJ",
    ),
    "L23": (
        ("ADP", "polysyllabe (après, depuis, pendant, devant, avant)", "*", ""),
        lambda g, d: g.upos == "ADP" and g.syllabes > 1,
    ),
    "L24": (("CCONJ", "forme = mais", "*", ""), lambda g, d: g.upos == "CCONJ" and g.f == "mais"),
    "L25": (
        ("ADV", "polysyllabe (souvent, toujours, vraiment…)", "*", ""),
        lambda g, d: g.upos == "ADV" and g.syllabes > 1,
    ),
    "L26": (("VERB", "", "*", ""), lambda g, d: g.upos == "VERB"),
    "L27": (
        ("NOUN", "Number=Plur", "VERB,AUX", ""),
        lambda g, d: g.upos == "NOUN" and g.feats.get("Number") == "Plur" and d.upos in _VERBE,
    ),
    "L28": (("ADJ", "postposé", "*", ""), lambda g, d: g.upos == "ADJ"),
    "L99": (("*", "", "*", ""), lambda g, d: True),
}
CONDITIONS_CODEES = {identifiant: texte for identifiant, (texte, _c) in _REGLES.items()}


@cache
def _table() -> list[tuple[str, str, str, Condition]]:
    texte = resources.files("lectura_nlp_fr.analyseur.data").joinpath("liaisons_contextes.tsv").read_text(encoding="utf-8")
    lignes = csv.DictReader(texte.splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE)
    return [(l["id"], l["statut"], l["frequence"], _REGLES[l["id"]][1]) for l in lignes]


def liaison_possible(gauche: MotAnalyse, droite: MotAnalyse) -> str:
    """Prononciation de ``gauche`` en liaison si la phonétique la permet, sinon « »."""
    debut = cle_de(droite.phone)[:1]
    if not gauche.latente or not (debut in VOYELLES or debut in _SEMI_VOYELLES):
        return ""
    return forme_liee(cle_de(gauche.phone), gauche.latente) or ""


def jonction(gauche: MotAnalyse, droite: MotAnalyse) -> Jonction:
    liee = liaison_possible(gauche, droite)
    if not liee:
        return Jonction("", INTERDITE)
    for identifiant, statut, frequence, condition in _table():
        if condition(gauche, droite):
            return Jonction(identifiant, statut, frequence, "" if statut == INTERDITE else liee)
    return Jonction("", INTERDITE)
