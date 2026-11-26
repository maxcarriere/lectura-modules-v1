# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Choix cohérent des graphies d'une phrase (prototype de la recherche globale).

Pour chaque mot, plusieurs graphies homophones sont possibles, chacune avec ses traits
(lexique). Le choix se fait sur toute la phrase : chaque graphie a un score propre
(accord avec l'analyse, fréquence, prime à la graphie reçue), et les mots reliés par une
relation d'accord (déterminant → nom, adjectif → nom, sujet → verbe) doivent s'accorder en
nombre, en genre ou en personne. Les relations viennent de l'analyseur ; quand elles forment
un arbre, le meilleur ensemble se calcule exactement (programmation dynamique sur l'arbre).

Couche optionnelle : la chaîne ne l'emploie que sur demande.
"""

from __future__ import annotations

from dataclasses import dataclass

from lectura_nlp_fr.analyseur.analyse import Analyse, Entree, accord

# Poids du score : points d'accord avec l'analyse, fréquence (zipf), prime à la graphie reçue.
POIDS_ACCORD, POIDS_FREQUENCE, PRIME_RECUE = 1.0, 0.5, 5.0
# Accord entre mots reliés : récompense par trait égal, pénalité par trait différent.
TRAIT_EGAL, TRAIT_DIFFERENT = 1.0, 5.0
# Traits à accorder selon la relation du dépendant vers sa tête.
_ACCORDS = {
    "det": ("Number", "Gender"),
    "amod": ("Number", "Gender"),
    "nummod": ("Number",),
    "nsubj": ("Number", "Person"),
    "nsubj:pass": ("Number", "Person", "Gender"),
    "expl:subj": ("Number", "Person"),
}
# Copule et auxiliaire (« cop », « aux ») ne sont pas accordés : essayé le 2026-10-06, aucun gain, trois faux positifs de plus.


@dataclass
class Choix:
    entree: Entree
    recue: bool


def _traits(relation: str, tete: Entree) -> tuple[str, ...]:
    traits = _ACCORDS.get(relation) or _ACCORDS.get(relation.split(":")[0], ())
    # Participe : le sujet s'accorde aussi en genre (« elles sont venues ») ; verbe conjugué : en personne.
    if relation.startswith("nsubj") and tete.feats.get("VerbForm") == "Part":
        return ("Number", "Gender")
    return traits


def _lien(dependant: Entree, tete: Entree, relation: str) -> float:
    score = 0.0
    for trait in _traits(relation, tete):
        a, b = dependant.feats.get(trait), tete.feats.get(trait)
        if a and b:
            score += TRAIT_EGAL if a == b else -TRAIT_DIFFERENT
    return score


def choisir(candidats: list[list[Choix]], analyses: list[Analyse]) -> list[int]:
    """Indice de la graphie retenue pour chaque mot (``0`` par défaut : la graphie reçue en tête)."""
    n = len(candidats)
    propre = [
        [POIDS_ACCORD * accord(c.entree, a) + POIDS_FREQUENCE * c.entree.frequence + (PRIME_RECUE if c.recue else 0.0) for c in cs]
        for cs, a in zip(candidats, analyses)
    ]
    enfants: dict[int, list[int]] = {i: [] for i in range(n)}
    racines = []
    for i, a in enumerate(analyses):
        tete = a.tete
        accordee = a.relation in _ACCORDS or a.relation.split(":")[0] in _ACCORDS
        if tete is None or tete < 0 or tete >= n or tete == i or not accordee:
            racines.append(i)
        else:
            enfants[tete].append(i)
    # Les relations d'accord doivent former une forêt : un cycle rend ses mots indépendants.
    visites: set[int] = set()
    ordre: list[int] = []

    def parcourir(i: int, pile: set[int]) -> None:
        if i in visites:
            return
        visites.add(i)
        pile.add(i)
        for j in enfants[i]:
            if j in pile:
                enfants[i] = [k for k in enfants[i] if k != j]
                racines.append(j)
            else:
                parcourir(j, pile)
        pile.discard(i)
        ordre.append(i)

    for r in list(racines):
        parcourir(r, set())
    for i in range(n):
        if i not in visites:
            racines.append(i)
            parcourir(i, set())
    # Programmation dynamique des feuilles vers les racines : meilleur score du sous-arbre pour chaque choix de la tête.
    meilleur: dict[int, list[float]] = {}
    choix_fils: dict[int, dict[int, list[int]]] = {}
    for i in ordre:               # ordre post-fixe : les enfants avant leur tête
        scores = list(propre[i])
        choix_fils[i] = {}
        for j in enfants[i]:
            for ci, c_tete in enumerate(candidats[i]):
                options = [
                    meilleur[j][cj] + _lien(c_fils.entree, c_tete.entree, analyses[j].relation)
                    for cj, c_fils in enumerate(candidats[j])
                ]
                k = max(range(len(options)), key=options.__getitem__)
                scores[ci] += options[k]
                choix_fils[i].setdefault(ci, []).append((j, k))
        meilleur[i] = scores
    resultat = [0] * n

    def descendre(i: int, ci: int) -> None:
        resultat[i] = ci
        for j, cj in choix_fils[i].get(ci, []):
            descendre(j, cj)

    for r in set(racines):
        descendre(r, max(range(len(meilleur[r])), key=meilleur[r].__getitem__))
    return resultat
