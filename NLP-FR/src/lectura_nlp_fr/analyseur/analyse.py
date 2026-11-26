# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Interfaces des trois ressources de la chaîne : analyseur de phrase, lexique, modèle de mot.

La chaîne ne connaît que ces interfaces. Les modèles entraînés, le lexique complet ou un
lexique embarqué réduit à des correctifs s'y branchent sans qu'elle change.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Protocol


@dataclass(frozen=True)
class Couple:
    """Une association de l'alignement linéaire : ce qui se prononce, ce qui s'écrit.

    Frontière de syllabe : ``Couple(".", ".")``. Lettre muette : phonème vide. Le côté
    phonème porte les marques du cadre (``[z]`` latente, ``*h*`` h aspiré, ``{a|b}``).
    """

    phone: str
    graphe: str


_SYLLABE = Couple(".", ".")
_VOYELLES_ECRITES = set("aeiouyàâäéèêëîïôöùûüœæ")


def redresser(couples: tuple[Couple, ...]) -> tuple[Couple, ...]:
    """Conventions de l'alignement lettres ⇄ phonèmes (syllabation écrite, 28/10/2026) :
    - le h muet ouvre la syllabe qui suit (« ca.hier », « de.hors », et non « cah.ier ») ;
    - « qu » et « gu » devant « ill », « il », « ign » forment un graphème (« qu|i|ll », « gu|i|gn ») ; le u ne porte
      pas le son de la voyelle suivante (« coquille », « anguille », « Guignard ») ;
    - « oi », « oî » se lisent /wa/ d'un bloc (« boîte » comme « boire »)."""
    c = list(couples)
    k = 0
    while k < len(c) - 1:
        a, b = c[k], c[k + 1]
        if a.phone == "w" and a.graphe.lower() == "o" and b.phone == "a" and b.graphe.lower() in ("i", "î"):
            c[k : k + 2] = [Couple("wa", a.graphe + b.graphe)]
            continue
        if a.graphe.lower() in ("q", "g") and b.graphe.lower() == "u" and b.phone == "i":
            j = next((j for j in range(k + 2, len(c)) if c[j] != _SYLLABE), None)
            if j is not None and len(c[j].graphe) > 1 and c[j].graphe[0] == "i" and not c[j].phone.startswith("i"):
                c[k], c[k + 1] = Couple(a.phone, a.graphe + b.graphe), Couple("i", c[j].graphe[0])
                c[j] = Couple(c[j].phone, c[j].graphe[1:])
        if k > 0 and a.phone == "" and a.graphe.lower() == "h" and b == _SYLLABE:
            j = next((j for j in range(k + 2, len(c)) if c[j] != _SYLLABE), None)
            if j is not None and c[j].graphe[:1].lower() in _VOYELLES_ECRITES:
                c[k], c[k + 1] = b, a
        k += 1
    return tuple(c)


@dataclass(frozen=True)
class Analyse:
    upos: str
    feats: dict[str, str] = field(default_factory=dict)
    lemme: str = ""
    tete: int | None = None           # indice du mot gouverneur dans la phrase, -1 pour la racine
    relation: str = ""
    confiance: float = 1.0
    amalgame: str = ""                # « aux » : forme nommée par la décomposition prédite d'un amalgame
    graphie: str = ""                 # en phonétique, graphie choisie par la tête de graphie parmi les homophones
    graphies: tuple[str, ...] = ()    # homophones qu'a vus la tête (sa table : mots simples, sans timbre voisin)
    confiance_tete: float = 1.0       # probabilité de l'arc vers ``tete`` (biaffine) : sûreté d'une règle d'accord


@dataclass(frozen=True)
class Entree:
    """Une lecture d'une forme dans le lexique."""

    ortho: str
    upos: str
    feats: dict[str, str]
    lemme: str
    phone_enrichi: str
    couples: tuple[Couple, ...]       # vide si la prononciation ne s'aligne pas sur la graphie
    frequence: float = 0.0            # zipf de cette analyse
    type: str = ""                    # Spéciaux : lettre, unite, symbole, sigle…
    origine: str = ""                 # "" : lexique du transducer ; sinon lexique branché (« lexicon »)


class Analyseur(Protocol):
    def analyser(self, formes: list[str]) -> list[Analyse]:
        """Analyse grammaticale d'une phrase écrite, un résultat par forme."""
        ...

    def analyser_phone(self, phones: list[str]) -> list[Analyse]:
        """Analyse grammaticale d'une phrase donnée par la prononciation de ses mots."""
        ...


class Lexique(Protocol):
    def lectures(self, forme: str) -> list[Entree]:
        """Toutes les lectures connues d'une forme écrite (casse exacte, sinon minuscules)."""
        ...

    def graphies(self, phones: list[str]) -> list[Entree]:
        """Toutes les entrées qui ont l'une de ces prononciations (écriture syllabée du lexique).
        Leurs couples peuvent être vides : ``aligner`` les donne pour l'entrée retenue."""
        ...

    def aligner(self, entree: Entree) -> Entree:
        """La même entrée avec ses couples d'alignement."""
        ...


class ModeleDeMot(Protocol):
    def aligner(self, forme: str, analyse: Analyse | None) -> tuple[Couple, ...] | None:
        """Alignement linéaire d'un mot écrit absent du lexique, ou ``None``."""
        ...

    def graphier(self, phone: str, analyse: Analyse | None) -> tuple[Couple, ...] | None:
        """Alignement linéaire d'un mot prononcé que le lexique ne connaît pas, ou ``None``."""
        ...


# L'analyseur lit au plus 512 mots d'un tenant (encodage des positions) : une phrase plus longue (texte sans
# ponctuation, transcription d'un long enregistrement) est analysée par tranches de 256 mots, chacune avec 64 mots de
# contexte de part et d'autre.
TRANCHE, CONTEXTE = 256, 64


def par_tranches(n: int, analyser: Callable[[int, int], list[Analyse]]) -> list[Analyse]:
    """``analyser(a, b)`` analyse les mots ``a`` à ``b`` (exclu) ; résultats recousus, têtes ramenées à la phrase."""
    if n <= 2 * TRANCHE:
        return analyser(0, n)
    resultat: list[Analyse] = []
    for debut in range(0, n, TRANCHE):
        fin = min(n, debut + TRANCHE)
        a, b = max(0, debut - CONTEXTE), min(n, fin + CONTEXTE)
        for r in analyser(a, b)[debut - a : fin - a]:
            tete = r.tete + a if r.tete is not None and r.tete >= 0 else r.tete
            resultat.append(replace(r, tete=tete))
    return resultat


def accord(entree: Entree, analyse: Analyse | None) -> int:
    """Points d'accord entre une entrée du lexique et l'analyse : catégorie, lemme, traits."""
    if analyse is None:
        return 0
    points = 4 * (entree.upos == analyse.upos)
    # Amalgame nommé par l'analyseur (« aux » et non « au ») : un indice de plus, pas une décision — en canal
    # phonétique l'étalon 3 répond « au » dans 109 cas sur 126 (mesure du 2026-10-06).
    points += 1 * (bool(analyse.amalgame) and entree.ortho.lower() == analyse.amalgame)
    points += 2 * (bool(analyse.lemme) and entree.lemme.lower() == analyse.lemme.lower())
    points += sum(1 for trait, valeur in analyse.feats.items() if entree.feats.get(trait) == valeur)
    points -= sum(1 for trait, valeur in analyse.feats.items() if trait in entree.feats and entree.feats[trait] != valeur)
    return points


def choisir(entrees: list[Entree], analyse: Analyse | None, nature: str = "") -> Entree | None:
    """Lecture du lexique qui s'accorde le mieux avec l'analyse ; à égalité, la plus fréquente."""
    if nature:
        entrees = [e for e in entrees if e.type == nature] or entrees
    if not entrees:
        return None
    return max(entrees, key=lambda e: (accord(e, analyse), e.frequence))
