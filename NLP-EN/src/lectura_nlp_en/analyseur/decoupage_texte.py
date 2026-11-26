# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Interface stable « texte → mots » de l'anglais, référence de tokenisation pour les corpus des modèles.

Même interface que le français (`NLP/Module/src/lectura_transducer/decoupage_texte.py`) : ``decouper(texte)`` rend
les phrases du texte, chaque phrase étant la suite de ses mots : forme écrite, position, type (mot, ponctuation,
formule, abrègement), type de formule et lecture (les mots qui la disent). Tout changement de sortie change
``VERSION``.

Propre à l'anglais (conventions UD English-EWT, voir `tokeniseur.py`) : les contractions sont découpées en mots
(*don't* → do + n't, *Bush's* → Bush + 's) ; le clitique n'a pas d'espace avant et touche son hôte.
``tokens_de_surface(phrase)`` recolle ces mots en tokens de surface d'UD (*don't*), entrée du modèle de phrase.
"""

from __future__ import annotations

from dataclasses import dataclass

from .abregements import table
from .formules import TYPES, TYPES_CROCHET, TYPES_LETTRES
from .formules.detection import detecter_formules
from .structures import TypeMot
from .tokeniseur import FORMES_CLITIQUES, decomposer, tokeniser

VERSION = "en-4"          # en-2 (12/10) : dates avec mois à l'américaine (April eighth)
# en-3 (12/10) : formules complétées (maths, durées, versions, angles, intervalles, plages de jours, paires…)
# en-4 (12/10, figée) : conventions validées ; date jour d'abord lue dans l'ordre (the fifth of March) ; symboles seuls
#   (& @ + = #) ; 2k two thousand, 3x three times
MOT, PONCTUATION, FORMULE, ABREGEMENT = "mot", "ponctuation", "formule", "abregement"
NATURES_D_ABREGEMENT = ("sigle", "acronyme", "abreviation", "initiale")
TYPES_DE_FORMULE: tuple[str, ...] = tuple(t.nom for t in (*TYPES, *TYPES_LETTRES, *TYPES_CROCHET))


@dataclass(frozen=True)
class MotTexte:
    forme: str                       # tel qu'écrit dans le texte, normalisé (« n't », « Bush », « $3.50 »)
    debut: int                       # position dans le texte
    fin: int
    type: str                        # MOT, PONCTUATION, FORMULE ou ABREGEMENT
    espace_avant: bool
    type_formule: str = ""           # formule : un de TYPES_DE_FORMULE ; abrègement : un de NATURES_D_ABREGEMENT
    lecture: tuple[str, ...] = ()    # pour une formule : les mots qui la disent (« three », « dollars », « fifty »)
    composants: tuple[int, ...] = () # pour chaque mot de la lecture, le rang de la partie de la formule qu'il lit


def decouper(texte: str) -> list[list[MotTexte]]:
    """Phrases du texte, chacune comme liste de mots."""
    phrases = []
    for phrase in detecter_formules(tokeniser(texte)).phrases:
        mots = []
        for m in phrase.mots:
            if m.abregement:
                mots.append(MotTexte(m.forme, m.debut, m.fin, ABREGEMENT, m.espace_avant, m.abregement, _lecture_abregement(m)))
            elif m.type is TypeMot.FORMULE and m.lecture:
                mots.append(MotTexte(m.forme, m.debut, m.fin, FORMULE, m.espace_avant, m.type_formule,
                                     tuple(x.forme for x in m.lecture), tuple(x.composant for x in m.lecture)))
            elif m.type is TypeMot.PONCTUATION:
                mots.append(MotTexte(m.forme, m.debut, m.fin, PONCTUATION, m.espace_avant))
            else:
                # Mot (ou formule sans lecture : symbole isolé, code, nombre trop complexe, gardé tel quel).
                mots.append(MotTexte(m.forme, m.debut, m.fin, MOT if m.type is not TypeMot.FORMULE else FORMULE,
                                     m.espace_avant, m.type_formule))
        phrases.append(mots)
    return phrases


def _lecture_abregement(m) -> tuple[str, ...]:
    """Sigle : ses lettres ; acronyme : le mot lui-même ; abréviation : son développement ; initiale : sa lettre."""
    if m.abregement in ("sigle", "initiale") and m.lecture:
        return tuple(x.forme for x in m.lecture)
    if m.abregement == "sigle":
        return tuple(c.upper() for c in m.forme if c.isalpha())
    if m.abregement == "abreviation":
        abrege = table().get(m.forme)
        if abrege and abrege.developpement:
            if m.lecture:
                return tuple(x.forme for x in m.lecture)
            return tuple(abrege.developpement.split())
        return (m.forme,)
    if m.abregement == "initiale":
        return (m.forme.rstrip("."),)
    return (m.forme,)


def est_clitique(precedent: MotTexte | None, mot: MotTexte) -> bool:
    """``mot`` est-il le clitique d'une contraction dont ``precedent`` est l'hôte (do + n't, Bush + 's) ?"""
    return (precedent is not None and not mot.espace_avant and mot.debut == precedent.fin
            and mot.type == MOT and precedent.type in (MOT, ABREGEMENT)
            and mot.forme.lower() in FORMES_CLITIQUES and decomposer(precedent.forme + mot.forme) is not None)


def tokens_de_surface(phrase: list[MotTexte]) -> list[list[MotTexte]]:
    """Mots regroupés par token de surface d'UD : [[do, n't], [go], …] (une contraction = un groupe de mots)."""
    groupes: list[list[MotTexte]] = []
    for k, m in enumerate(phrase):
        if groupes and est_clitique(phrase[k - 1], m):
            groupes[-1].append(m)
        else:
            groupes.append([m])
    return groupes
