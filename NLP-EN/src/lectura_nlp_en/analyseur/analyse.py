# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Interfaces des trois ressources de la chaîne anglaise : analyseur de phrase, lexique, modèle de mot.

La chaîne ne connaît que ces interfaces (comme le français) : l'adaptateur PyTorch de développement
(``adaptateurs/etalon.py``, ``adaptateurs/gpa.py``), le lexique de développement (``lexique.py``, jeux TSV) ou le
lexique embarqué (``lexique_embarque.py``), et plus tard les modèles ONNX, s'y branchent sans qu'elle change.

Écart avec le français : l'analyseur anglais reçoit des **jetons de surface** (``Jeton`` : une contraction *don't*
est un jeton de deux mots *do* + *n't*, comme UD EWT) et rend une analyse par **mot** ; il peut aussi rendre l'entrée
du lexique qu'il a choisie (tête de sélection), que la chaîne prend telle quelle.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Protocol

# Couples de frontière de syllabe de la forme linéaire (spec 06 §5) : point, accent primaire, accent secondaire.
SYLLABE_COUPLES = frozenset({(".", "."), ("ˈ", "."), ("ˌ", ".")})


@dataclass(frozen=True)
class Couple:
    """Une association de l'alignement linéaire : ce qui se prononce, ce qui s'écrit.

    Frontière de syllabe : ``Couple(".", ".")``, ``Couple("ˈ", ".")``, ``Couple("ˌ", ".")``. Lettre muette : phonème
    vide. Séparateur : graphème ``'`` ``-`` ou espace, phonème ``‿`` quand une syllabe l'enjambe, ``.``/``ˈ`` s'il
    porte une frontière de syllabe, vide sinon.
    """

    phone: str
    graphe: str

    @property
    def frontiere(self) -> bool:
        return (self.phone, self.graphe) in SYLLABE_COUPLES


@dataclass(frozen=True)
class Entree:
    """Une lecture d'une forme dans le lexique."""

    ortho: str
    upos: str
    feats: dict[str, str]
    lemme: str
    phone_enrichi: str
    couples: tuple[Couple, ...]       # forme linéaire (frontières de syllabe comprises) ; vide si non alignée
    frequence: float = 0.0            # zipf de cette analyse
    type: str = ""                    # Spéciaux : lettre, unite, symbole, sigle…
    speciale: bool = False            # ligne des Spéciaux
    niveau: str = ""                  # noyau / etendu (colonne du lexique) ; vide : noyau

    def __hash__(self) -> int:
        return hash((self.ortho, self.upos, self.lemme, self.phone_enrichi, tuple(sorted(self.feats.items()))))


@dataclass(frozen=True)
class Analyse:
    upos: str
    feats: dict[str, str] = field(default_factory=dict)
    lemme: str = ""
    tete: int | None = None           # indice du mot gouverneur dans la phrase, -1 pour la racine
    relation: str = ""
    confiance: float = 1.0
    graphie: str = ""                 # en phonétique, graphie choisie (tête de sélection ou de graphie)
    graphies: tuple[str, ...] = ()
    entree: Entree | None = None      # entrée du lexique choisie par l'analyseur (tête de sélection), s'il y en a une
    code: str = ""                    # comment l'analyse a été obtenue (L lexique, M/E improvisée, C contraction…)


@dataclass
class Jeton:
    """Jeton de surface donné à l'analyseur : forme (ou prononciation), type du découpage, mots d'une contraction."""

    forme: str
    type: str = "m"                   # m, p, s, f:<type>, a:<nature> (types du découpage du Module)
    mots: tuple[str, ...] = ()        # contraction : ses mots (« do », « n't ») ; vide sinon
    phone: str = ""                   # canal phonétique
    lecture: tuple[str, ...] = ()     # abrègement : les mots de sa lecture
    variantes: tuple[str, ...] = ()   # canal phonétique : autres prononciations à chercher (forme faible d'une forte)


class Analyseur(Protocol):
    def analyser(self, jetons: list[Jeton]) -> list[list[Analyse]]:
        """Phrase écrite : pour chaque jeton, l'analyse de chacun de ses mots (un seul, ou ceux de la contraction)."""
        ...

    def analyser_phone(self, jetons: list[Jeton]) -> list[list[Analyse]]:
        """Phrase donnée par la prononciation de ses jetons : analyse et graphie choisie (``Analyse.entree``)."""
        ...


class Lexique(Protocol):
    def lectures(self, forme: str) -> list[Entree]:
        """Toutes les lectures connues d'une forme écrite (casse exacte d'abord, puis minuscules)."""
        ...

    def homophones(self, phone: str) -> list[Entree]:
        """Entrées prononcées ainsi, sans tenir compte de l'accent ni des syllabes."""
        ...


class ModeleDeMot(Protocol):
    def aligner(self, forme: str, analyse: Analyse | None) -> tuple[Couple, ...] | None:
        """Forme linéaire d'un mot écrit absent du lexique, ou ``None``."""
        ...

    def graphier(self, phone: str, analyse: Analyse | None) -> tuple[Couple, ...] | None:
        """Forme linéaire d'un mot prononcé que le lexique ne connaît pas, ou ``None``."""
        ...


# L'analyseur lit au plus 512 mots d'un tenant : une phrase plus longue est analysée par tranches de 256 jetons, chacune
# avec 64 jetons de contexte de part et d'autre (comme le français).
TRANCHE, CONTEXTE = 256, 64


def par_tranches(n: int, analyser: Callable[[int, int], list]) -> list:
    """``analyser(a, b)`` analyse les jetons ``a`` à ``b`` (exclu) ; résultats recousus, têtes ramenées à la phrase."""
    if n <= 2 * TRANCHE:
        return analyser(0, n)
    resultat: list = []
    for debut in range(0, n, TRANCHE):
        fin = min(n, debut + TRANCHE)
        a, b = max(0, debut - CONTEXTE), min(n, fin + CONTEXTE)
        for r in analyser(a, b)[debut - a : fin - a]:
            resultat.append([replace(x, tete=x.tete + a if x.tete is not None and x.tete >= 0 else x.tete) for x in r])
    return resultat


def sans_etendus(entrees: list[Entree]) -> list[Entree]:
    """Les entrées de niveau ``etendu`` (homophones rares : *frum*, *Hees*) sont écartées quand une entrée du noyau
    existe pour la même clé (forme ou prononciation) ; seules, elles restent."""
    noyau = [e for e in entrees if e.niveau != "etendu"]
    return noyau or entrees


def accord(entree: Entree, analyse: Analyse | None) -> int:
    """Points d'accord entre une entrée du lexique et l'analyse : catégorie, lemme, traits."""
    if analyse is None:
        return 0
    points = 4 * (entree.upos == analyse.upos)
    points += 2 * (bool(analyse.lemme) and entree.lemme.lower() == analyse.lemme.lower())
    points += sum(1 for trait, valeur in analyse.feats.items() if entree.feats.get(trait) == valeur)
    points -= sum(1 for trait, valeur in analyse.feats.items() if trait in entree.feats and entree.feats[trait] != valeur)
    return points


def choisir(entrees: list[Entree], analyse: Analyse | None, forme: str = "") -> Entree | None:
    """Lecture du lexique qui s'accorde le mieux avec l'analyse ; à égalité, la casse exacte puis la plus fréquente.
    L'entrée choisie par l'analyseur (tête de sélection) passe avant, si elle est parmi les lectures."""
    if not entrees:
        return None
    if analyse is not None and analyse.entree is not None and analyse.entree in entrees:
        return analyse.entree
    return max(entrees, key=lambda e: (accord(e, analyse), e.ortho == forme, e.frequence))
