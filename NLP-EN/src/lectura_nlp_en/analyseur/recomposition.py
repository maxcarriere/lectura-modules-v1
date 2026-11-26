# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Recomposition d'une phrase phonétique anglaise (sens phonétique → écrit), avant le choix des graphies.

« ‿ » est une frontière de mot de nature inconnue (comme en français) : en anglais, soit un **enchaînement** (consonne
finale devant voyelle, ``ən‿ˈæp.əl``), soit un **clitique** (``ˈdoʊn‿t``, ``ˈbɑb‿z``, ``ju‿ɚ``). Règles (spec 09 §7) :

1. une suite de morceaux liés par « ‿ » qui, recollée, est la prononciation d'une contraction du lexique (graphie à
   apostrophe : *don't*, *it's*, *you're*) devient un seul mot ;
2. sinon, un morceau sans voyelle qui suit « ‿ » (``z s d l m v``, ``t`` de *n't*) ou ``ɚ`` après une voyelle est le
   clitique du mot précédent (*'s*, *'d*, *'ll*, *'m*, *'ve*, *'re*) ;
3. sinon, c'est un enchaînement : deux mots.

Le mot recollé garde ses « ‿ » ; un clitique reçoit ``nature = "clitique"`` ; la jonction du mot de gauche dit
``"clitique"`` ou ``"enchainement"`` (``Mot.jonction``).
"""

from __future__ import annotations

from .phonetique import LIAISON, est_voyelle, finit_par_consonne, phonemes, sans_marques
from .structures import Document, Mot, Phrase, TypeMot

CLITIQUE, ENCHAINEMENT = "clitique", "enchainement"
_CLITIQUES_PHONE = frozenset({"s", "z", "d", "l", "m", "v", "t", "nt", "ənt"})
_MAX_MORCEAUX = 3


def cle(phone: str) -> str:
    """Clé de recherche d'un mot phonétique : phonèmes seuls (ni accent, ni syllabe, ni séparateurs)."""
    return sans_marques(phone).replace("'", "").replace("-", "")


def est_contraction(lexique, phone: str) -> bool:
    return any("'" in e.ortho for e in lexique.homophones(cle(phone)))


def recomposer(document: Document, lexique) -> Document:
    phrases = []
    for phrase in document.phrases:
        mots: list[Mot] = []
        i, ms = 0, phrase.mots
        while i < len(ms):
            m = ms[i]
            # suite de morceaux liés par ‿ à partir de m
            j = i
            while j < len(ms) - 1 and ms[j].lie_au_suivant and ms[j].type is TypeMot.MOT and ms[j + 1].type is TypeMot.MOT:
                j += 1
            if j == i or m.type is not TypeMot.MOT:
                mots.append(m)
                i += 1
                continue
            k = i
            while k <= j:
                fait = False
                for fin in range(min(j, k + _MAX_MORCEAUX - 1), k, -1):
                    groupe = ms[k : fin + 1]
                    phone = LIAISON.join(x.forme for x in groupe)
                    # un morceau qui commence par une voyelle après ‿ est un enchaînement (la lecture écrit « . » devant
                    # un clitique syllabique : ˈbʊʃ.ɪz), sauf 're (ju‿ɚ) : « which is » n'est pas « which's »
                    voyelle = any(est_voyelle((phonemes(cle(x.forme)) or [""])[0]) and cle(x.forme) != "ɚ" for x in groupe[1:])
                    if not voyelle and est_contraction(lexique, phone):
                        mot = Mot(TypeMot.MOT, phone, groupe[0].debut, groupe[-1].fin, [s for x in groupe for s in x.segments],
                                  groupe[0].espace_avant, lie_au_suivant=groupe[-1].lie_au_suivant)
                        _lier(mots, mot)
                        k, fait = fin + 1, True
                        break
                if not fait:
                    _lier(mots, ms[k])
                    k += 1
            i = j + 1
        phrases.append(Phrase(mots))
    return Document(document.texte, document.canal, phrases, document.niveau_phone)


def _lier(mots: list[Mot], mot: Mot) -> None:
    """Ajoute ``mot`` ; s'il suit un « ‿ », décide clitique ou enchaînement avec le mot précédent."""
    precedent = mots[-1] if mots else None
    if precedent is not None and precedent.lie_au_suivant and precedent.type is TypeMot.MOT and not mot.espace_avant:
        c = cle(mot.forme)
        ph = phonemes(c) or []
        clitique = c in _CLITIQUES_PHONE or (c == "ɚ" and not finit_par_consonne(precedent.forme))
        if clitique and not any(est_voyelle(p) for p in ph[:1]) or (c == "ɚ" and clitique):
            mot.nature = CLITIQUE
            precedent.jonction = CLITIQUE
        else:
            precedent.jonction = ENCHAINEMENT
    mots.append(mot)
