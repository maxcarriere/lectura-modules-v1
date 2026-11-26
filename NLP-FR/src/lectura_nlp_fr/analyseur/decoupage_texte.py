# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Interface stable « texte → mots », référence de tokenisation pour les corpus des modèles.

``decouper(texte)`` rend les phrases du texte, chaque phrase étant la suite de ses mots : forme écrite, position, type
(mot, ponctuation, formule), type de formule et lecture de la formule (les mots qui la disent). C'est le découpage que
fait la chaîne du Module ; il ne dépend pas des structures internes (segments, jonctions), qui peuvent évoluer.
Tout changement de sortie de cette fonction change ``VERSION``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .abregements import table
from .formules import TYPES, TYPES_CROCHET, TYPES_LETTRES
from .formules.detection import detecter_formules
from .structures import TypeMot
from .tokeniseur import tokeniser

VERSION = "4"
MOT, PONCTUATION, FORMULE, ABREGEMENT = "mot", "ponctuation", "formule", "abregement"
# Natures d'abrègement (champ ``type_formule`` d'un abrègement) : sigle (épelé : SNCF), acronyme (lu comme un mot :
# NASA), abréviation (lue par son développement : M., av. J.-C.), initiale (« J. » de « J. Dupont »).
NATURES_D_ABREGEMENT = ("sigle", "acronyme", "abreviation", "initiale")
# Types de formules, dans l'ordre où le détecteur les essaie.
TYPES_DE_FORMULE: tuple[str, ...] = tuple(t.nom for t in (*TYPES, *TYPES_LETTRES, *TYPES_CROCHET))


@dataclass(frozen=True)
class MotTexte:
    forme: str                       # tel qu'écrit dans le texte (« l' », « -t-il », « 25,50 € »)
    debut: int                       # position dans le texte
    fin: int
    type: str                        # MOT, PONCTUATION, FORMULE ou ABREGEMENT
    espace_avant: bool
    type_formule: str = ""           # formule : un de TYPES_DE_FORMULE ; abrègement : un de NATURES_D_ABREGEMENT
    lecture: tuple[str, ...] = ()    # pour une formule : les mots qui la disent (« vingt-cinq », « euros », « cinquante »)
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
                # Mot (ou formule sans lecture : symbole isolé, gardé tel quel).
                mots.append(MotTexte(m.forme, m.debut, m.fin, MOT if m.type is not TypeMot.FORMULE else FORMULE,
                                     m.espace_avant, m.type_formule))
        phrases.append(mots)
    return phrases


def _lecture_abregement(m) -> tuple[str, ...]:
    """Sigle : ses lettres ; acronyme : le mot lui-même ; abréviation : son développement ; initiale : sa lettre."""
    if m.abregement in ("sigle", "initiale") and m.lecture:
        return tuple(x.forme for x in m.lecture)
    if m.abregement == "sigle":
        return tuple(x.forme for x in m.lecture) if m.lecture else tuple(c for c in m.forme if c.isalnum())
    if m.abregement == "abreviation":
        abrege = table().get(m.forme)
        return tuple(abrege.developpement.split()) if abrege and abrege.developpement else (m.forme,)
    if m.abregement == "initiale":
        return (m.forme.rstrip("."),)
    return (m.forme,)
