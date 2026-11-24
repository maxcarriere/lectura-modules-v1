# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Types communs au français et à l'anglais, en mode local comme en mode API.

``Lecture`` et ``Forme`` réunissent les champs des deux langues : un champ propre à une langue reste à sa valeur par
défaut dans l'autre (``Lecture.multext`` est vide en anglais, ``Forme.britannique`` toujours faux en français).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields

ACCEPTEE, PROPOSABLE, RARE, INCONNUE, VARIANTE = "acceptee", "proposable", "rare", "inconnue", "variante"
VALIDITES = (INCONNUE, RARE, VARIANTE, ACCEPTEE, PROPOSABLE)
LANGUES = ("fr", "en")


@dataclass(frozen=True)
class Lecture:
    """Une analyse d'une forme. Avec une base sans analyses (taille mini), seuls ``phone`` et ``zipf`` sont remplis."""

    ortho: str
    lemme: str = ""
    upos: str = ""
    feats: str = ""
    phone: str = ""
    zipf: float = 0.0              # zipf de l'analyse (bases avec analyses), sinon de la forme
    id_lemme: str = ""
    sources: tuple[str, ...] = ()
    confiance: str = ""
    masquee: bool = False          # zipf 0 alors qu'une autre analyse de la forme a été vue
    phone_enrichi: str = ""        # marques du cadre (latentes, h aspiré, {a|b}) ; vide = ``phone``
    multext: str = ""              # (français) étiquette MULTEXT (« Ncms », « Vmip3s- ») ; vide sans elle
    marque: str = ""               # flexion que le Wiktionnaire marque seulement rare, archaïque… ; vide = courante

    def traits(self) -> dict[str, str]:
        return dict(t.split("=", 1) for t in self.feats.split("|") if "=" in t)


@dataclass(frozen=True)
class Forme:
    ortho: str
    zipf: float
    validite: str
    propre: bool = False           # seulement nom propre
    special: bool = False          # abrègement, symbole, sigle, lettre
    distance: int = 0              # pour les voisins
    lectures: tuple[Lecture, ...] = field(default=(), compare=False)
    rime: str = ""                 # (français) qualité de la rime : pauvre, suffisante, riche
    non_valide: bool = False       # forme non validée : présente avec sa fréquence, validité « inconnue »
    britannique: bool = False      # (anglais) graphie britannique (colour) ; ``americaine`` donne l'autre


@dataclass
class Seuils:
    """Seuils de validité, réglables au-dessus du plancher de construction des données (mode local)."""

    acceptee: float = 0.5          # zipf de la forme
    acceptee_lemme: float = 2.0    # ou forme du noyau d'un lemme de ce zipf
    proposable: float = 1.0        # zipf de la forme


_CHAMPS_LECTURE = {f.name for f in fields(Lecture)}
_CHAMPS_FORME = {f.name for f in fields(Forme)}


def lecture_depuis_json(d: dict) -> Lecture:
    """``Lecture`` depuis sa forme JSON (champs inconnus ignorés, listes rendues en tuples)."""
    d = {k: v for k, v in d.items() if k in _CHAMPS_LECTURE}
    if "sources" in d:
        d["sources"] = tuple(d["sources"] or ())
    return Lecture(**d)


def forme_depuis_json(d: dict) -> Forme:
    d = {k: v for k, v in d.items() if k in _CHAMPS_FORME}
    d["lectures"] = tuple(lecture_depuis_json(x) for x in d.get("lectures") or ())
    return Forme(**d)
