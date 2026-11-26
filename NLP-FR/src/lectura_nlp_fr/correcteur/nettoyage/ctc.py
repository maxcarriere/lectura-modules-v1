# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Sortie du décodeur CTC actuel → phrase phonétique du module.

Le décodeur CTC en service (``lectura_decodeur``, vocabulaire de 59 symboles) produit des phonèmes
séparés par des espaces, « | » entre les mots, la ponctuation comme jetons, et des marques :
« [z] [t] [n] [ʁ] [p] » (liaison devant le mot suivant), « ['] » (élision : le clitique se
rattache au mot suivant), « [-] » (frontière de mot composé). Son alphabet dépasse l'inventaire
du cadre (ɑ, c, ɟ, ʎ, dʒ, tʃ, ts, mʲ).

Le module, lui, suit le lexique : mots séparés par des espaces, « ‿ » pour une jonction (liaison,
élision, tiret), « . » entre syllabes. Cet adaptateur fait la traduction ; il disparaîtra quand le
CTC sera réentraîné sur les conventions actuelles (annoncé par l'utilisateur, en second temps).
"""

from __future__ import annotations

from lectura_nlp_fr.analyseur.tokeniseur import LIAISON, PHONEMES

MARQUES_LIAISON = {"[z]": "z", "[t]": "t", "[n]": "n", "[ʁ]": "ʁ", "[p]": "p"}
ELISION, COMPOSE, SEPARATEUR = "[']", "[-]", "|"
PONCTUATION = {",", ".", "?", "!", "…", ";", ":"}
# Symboles du CTC hors inventaire du cadre.
_HORS_INVENTAIRE = {"ɑ": "a", "c": "k", "ɟ": "ɡ", "ʎ": "j", "g": "ɡ", "mʲ": "mj"}


def phoneme(symbole: str) -> str:
    """Symbole du CTC → phonème(s) du cadre (``dʒ`` devient ``d`` + ``ʒ``)."""
    if symbole in PHONEMES:
        return symbole
    if symbole in _HORS_INVENTAIRE:
        return _HORS_INVENTAIRE[symbole]
    return "".join(phoneme(c) for c in symbole) if len(symbole) > 1 else symbole


def depuis_ctc(chaine: str) -> str:
    """« b o [z] a ʁ b ʁ | k ['] i l . » → « boz‿aʁbʁ k‿il. »"""
    mots: list[str] = []
    courant: list[str] = []

    def clore(jonction: str = "") -> None:
        if courant:
            mots.append("".join(courant) + jonction)
            courant.clear()
        elif jonction and mots and not mots[-1].endswith(LIAISON):
            mots[-1] += jonction

    for jeton in chaine.split():
        if jeton == SEPARATEUR:
            clore()
        elif jeton in MARQUES_LIAISON:
            if not courant and mots and mots[-1] not in PONCTUATION and not mots[-1].endswith(LIAISON):
                # Marque placée en tête du mot suivant (« œ̃ | [n] ɛ̃ s t ɑ̃ ») : la consonne de liaison finit le mot
                # précédent.
                mots[-1] += MARQUES_LIAISON[jeton] + LIAISON
                continue
            courant.append(MARQUES_LIAISON[jeton])
            clore(LIAISON)
        elif jeton == ELISION:
            # Clitique élidé : une consonne ; le CTC a pu la coller au mot précédent (« ɛ m ['] »).
            if len(courant) > 1:
                dernier = courant.pop()
                clore()
                courant.append(dernier)
            clore(LIAISON)
        elif jeton == COMPOSE:
            clore(LIAISON)
        elif jeton in PONCTUATION:
            clore()
            mots.append(jeton)
        else:
            courant.append(phoneme(jeton))
    clore()
    texte = ""
    for mot in mots:
        if mot in PONCTUATION or not texte or texte.endswith(LIAISON):
            texte += mot
        else:
            texte += " " + mot
    return texte
