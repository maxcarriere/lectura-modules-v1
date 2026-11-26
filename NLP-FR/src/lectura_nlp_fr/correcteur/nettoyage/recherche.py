# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Recherche globale des graphies, en phonétique → orthographe (phase de correction, 2026-10-10).

Couche optionnelle : ``Recherche(...).brancher(chaine)`` ; sans elle, chaque mot choisit seul sa graphie
(``Chaine._graphie``). Ici les graphies d'une phrase sont choisies ensemble : chaque graphie candidate garde la note que
la chaîne lui donne seule (accord avec l'analyse, tête de graphie, puis fréquence), et les mots reliés par une relation
d'accord de l'analyse (déterminant, adjectif → nom ; sujet → verbe) gagnent ``egal`` par trait égal et perdent
``different`` par trait différent, d'après les traits des entrées du lexique. Un mot dont la prononciation fixe le
nombre (« les », « sont ») le transmet ainsi à ses voisins homophones (« chaises », « ils »). Seuls les arcs sûrs
(``Analyse.confiance_tete`` ≥ ``seuil``) comptent ; ils forment une forêt, et le meilleur ensemble se calcule
exactement (programmation dynamique sur l'arbre, comme ``coherence.py`` dans le sens du correcteur).
"""

from __future__ import annotations

from lectura_nlp_fr.analyseur.analyse import Analyse
from lectura_nlp_fr.analyseur.structures import TypeMot

# Traits à accorder selon la relation du dépendant vers sa tête.
ACCORDS = {
    "det": ("Number", "Gender"),
    "amod": ("Number", "Gender"),
    "nsubj": ("Number", "Person"),
    "nsubj:pass": ("Number", "Person"),
    "expl:subj": ("Number", "Person"),
}
# Pronoms dont le nombre grammatical ne dit pas le nombre réel : « vous êtes marié » (vouvoiement), « on est venus ».
_NOMBRE_TROMPEUR = {"vous", "nous", "on"}
# La fréquence ne départage qu'à note égale (comme dans ``Chaine._graphie``) : son poids reste sous un point d'accord.
_EPSILON = 0.01


def _traits(relation: str, tete, etre: bool) -> tuple[str, ...]:
    if relation.startswith("nsubj") and tete.feats.get("VerbForm") == "Part":
        # Participe avec « être » : le sujet s'accorde en nombre et en genre (« elles sont venues ») ; avec « avoir »,
        # pas d'accord avec le sujet (« elles ont mangé »).
        return ("Number", "Gender") if etre else ()
    return ACCORDS.get(relation, ())


class Recherche:
    def __init__(self, seuil: float = 0.7, egal: float = 1.0, different: float = 3.0, audible: bool = True):
        # ``audible`` : un trait ne compte sur un lien que si l'un des deux mots l'a fixé par sa prononciation (toutes ses
        # candidates ont la même valeur : « les », « sont ») ; entre deux mots homophones (« leur feuille(s) »,
        # « il(s) lisai(en)t »), chacun garde son choix.
        self.seuil, self.egal, self.different, self.audible = seuil, egal, different, audible
        self.changes = 0            # graphies changées par la recherche (dernière phrase), pour le banc

    def brancher(self, chaine) -> None:
        chaine.recherche = self

    def _lien(self, dependant, tete, relation: str, etre: bool, fixes: set[str]) -> float:
        score = 0.0
        for trait in _traits(relation, tete, etre):
            if self.audible and trait not in fixes:
                continue
            a, b = dependant.feats.get(trait), tete.feats.get(trait)
            if a and b:
                score += self.egal if a == b else -self.different
        return score

    def choisir(self, chaine, mots, analyses: list[Analyse], inverses: list[bool], entrees: list):
        n = len(mots)
        candidats: list[list] = []
        propres: list[list[float]] = []
        for i, (m, a) in enumerate(zip(mots, analyses)):
            notes = chaine._notes_graphie(m, inverses[i], a) if m.type is TypeMot.MOT and entrees[i] is not None else []
            if len({e.ortho.lower() for e, _ in notes}) < 2:
                candidats.append([entrees[i]])                   # rien à départager : le mot est fixé
                propres.append([0.0])
                continue
            candidats.append([e for e, _ in notes])
            propres.append([p + _EPSILON * f for _, (p, f) in notes])
        # Traits fixés par la prononciation : même valeur pour toutes les candidates.
        fixes: list[set[str]] = []
        for cs in candidats:
            valeurs: dict[str, set] = {}
            for e in cs:
                for t in ("Number", "Gender", "Person"):
                    valeurs.setdefault(t, set()).add(e.feats.get(t) if e is not None else None)
            fixe = {t for t, v in valeurs.items() if len(v) == 1 and None not in v}
            # Ni nom propre (« Palaos » pluriel au lexique) ni numéral : leur nombre ne s'entend pas dans l'accord.
            if any(e is not None and (e.ortho.lower() in _NOMBRE_TROMPEUR or e.upos in ("PROPN", "NUM")) for e in cs):
                fixe = set()
            fixes.append(fixe)
        enfants: dict[int, list[int]] = {i: [] for i in range(n)}
        a_une_tete = [False] * n
        for i, a in enumerate(analyses):
            t = a.tete
            if candidats[i][0] is None or t is None or not 0 <= t < n or t == i or candidats[t][0] is None:
                continue
            if a.relation not in ACCORDS or a.confiance_tete < self.seuil:
                continue
            if a.relation.startswith("nsubj") and any(b.relation == "conj" and b.tete in (i, t) and b.upos in ("NOUN", "PROPN", "PRON")
                                                      for b in analyses):
                continue                                         # sujet coordonné (le « conj » parfois rattaché au verbe)
            enfants[t].append(i)
            a_une_tete[i] = True
        # Ordre post-fixe depuis les racines ; un cycle (impossible dans un arbre, possible sur des arcs filtrés) est coupé.
        ordre: list[int] = []
        vus: set[int] = set()

        def parcourir(i: int) -> None:
            pile = [(i, iter(enfants[i]))]
            vus.add(i)
            while pile:
                k, fils = pile[-1]
                j = next(fils, None)
                if j is None:
                    pile.pop()
                    ordre.append(k)
                elif j in vus:
                    enfants[k] = [x for x in enfants[k] if x != j]
                    a_une_tete[j] = False
                else:
                    vus.add(j)
                    pile.append((j, iter(list(enfants[j]))))

        for i in range(n):
            if not a_une_tete[i] and i not in vus:
                parcourir(i)
        for i in range(n):
            if i not in vus:
                a_une_tete[i] = False
                parcourir(i)
        # Prédicat conjugué avec « être » (auxiliaire du passif, copule, temps composé) : le participe s'accorde.
        etre = [any(b.tete == i and b.relation in ("aux:pass", "cop", "aux", "aux:tense") and b.lemme == "être"
                    for b in analyses) for i in range(n)]
        meilleur: dict[int, list[float]] = {}
        retenu_fils: dict[int, list[list[tuple[int, int]]]] = {}
        for i in ordre:
            scores = list(propres[i])
            retenu_fils[i] = [[] for _ in scores]
            for j in enfants[i]:
                for ci, tete in enumerate(candidats[i]):
                    options = [meilleur[j][cj] + self._lien(fils, tete, analyses[j].relation, etre[i], fixes[i] | fixes[j])
                               for cj, fils in enumerate(candidats[j])]
                    k = max(range(len(options)), key=options.__getitem__)
                    scores[ci] += options[k]
                    retenu_fils[i][ci].append((j, k))
            meilleur[i] = scores
        choix = [0] * n

        def descendre(i: int, ci: int) -> None:
            pile = [(i, ci)]
            while pile:
                k, ck = pile.pop()
                choix[k] = ck
                pile.extend(retenu_fils[k][ck])

        for i in range(n):
            if not a_une_tete[i]:
                descendre(i, max(range(len(meilleur[i])), key=meilleur[i].__getitem__))
        resultat = list(entrees)
        self.changes = 0
        for i in range(n):
            e = candidats[i][choix[i]]
            if len(candidats[i]) > 1 and e is not None and (entrees[i] is None or e.ortho != entrees[i].ortho or e.feats != entrees[i].feats):
                resultat[i] = chaine.lexique.aligner(e)
                self.changes += e.ortho != (entrees[i].ortho if entrees[i] else None)
        return resultat
