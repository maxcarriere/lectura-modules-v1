# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Relecture des graphies d'une phrase par un modèle de langue écrit (sens phonétique → orthographe, 2026-10-14).

Les homophones grammaticaux (ces / ses, et / est, a / à, leur / leurs) ne se départagent pas mot à mot : la relecture
choisit les graphies de toute la phrase ensemble. Chaque graphie candidate garde la note que la chaîne lui donne seule
(``Chaine._notes_graphie`` : accord avec l'analyse, tête de graphie, fréquence) ; la phrase est choisie en faisceau sur
log P(mots | modèle de langue) + ``poids`` × (note − meilleure note du mot). Sans les notes de la chaîne (poids 0), la
relecture dégrade nettement ; l'optimum mesuré est entre 1,5 et 2.

Modèle : KenLM 4-grammes de mots écrits (``langue_ecrite.bin``, construit par ``outils/construire_langue_ecrite.py``),
mots découpés par ``mots_ecrits``. Dépendance facultative : ``kenlm``.

Branchement : ``Relecture(modele).brancher(chaine)`` (accroche ``chaine.recherche``) ; ``MoteurLocal`` la branche
d'office quand le fichier est présent et ``kenlm`` installé (option ``relecture=False`` pour s'en passer).

Mesures (WER, 2026-10-14) : écriture depuis la phonétique parfaite FLEURS dev 5,23 → 4,81 %, dev du corpus 2
5,88 → 5,34 % ; STT complet FLEURS dev 17,88 → 17,60 %, dev du corpus 2 12,43 → 11,90 %.
"""

from __future__ import annotations

import math
import re

from .structures import TypeMot

FICHIER = "langue_ecrite.bin"
POIDS = 2.0
LARGEUR = 16

_LN10 = math.log(10)
# La fréquence ne départage qu'à note égale (comme dans ``Chaine._graphie``).
_EPSILON = 0.01
_MOT = re.compile(r"\d+(?:[.,\s]\d+)*|[^\W\d_]+(?:-[^\W\d_]+)*'?")


def mots_ecrits(texte: str) -> list[str]:
    """Texte → mots du modèle de langue écrit : minuscules, apostrophe gardée sur l'élision (« l' », « qu' »), mots à
    trait d'union entiers, nombres → ``<nombre>``, ponctuation retirée. Même découpe qu'à la construction du modèle."""
    texte = texte.lower().replace("’", "'").replace("œ", "oe")
    return ["<nombre>" if m[0].isdigit() else m for m in _MOT.findall(texte)]


def charger(chemin):
    """Modèle KenLM, ou None si ``kenlm`` n'est pas installé."""
    try:
        import kenlm
    except ImportError:
        return None
    return kenlm.Model(str(chemin))


class Relecture:
    def __init__(self, modele, poids: float = POIDS, largeur: int = LARGEUR):
        self.lm, self.poids, self.largeur = modele, poids, largeur

    def brancher(self, chaine) -> None:
        chaine.recherche = self

    def _options(self, chaine, mots, analyses, inverses, entrees) -> list[list[tuple]]:
        """Par mot : [(entrée, mots écrits, note relative)] ; un seul choix si la chaîne n'en propose qu'un."""
        options: list[list[tuple]] = []
        for i, (m, a) in enumerate(zip(mots, analyses)):
            e = entrees[i]
            if m.type is not TypeMot.MOT:
                options.append([(e, [], 0.0)])
                continue
            notes = chaine._notes_graphie(m, inverses[i], a) if e is not None else []
            if len({x.ortho.lower() for x, _ in notes}) < 2:
                options.append([(e, mots_ecrits(e.ortho) if e else ["<unk>"], 0.0)])
                continue
            meilleures: dict[str, tuple] = {}
            for x, (p, f) in notes:
                cle, note = x.ortho.lower(), p + _EPSILON * f
                if cle not in meilleures or note > meilleures[cle][1]:
                    meilleures[cle] = (x, note)
            haut = max(n for _, n in meilleures.values())
            options.append([(x, mots_ecrits(x.ortho), n - haut) for x, n in meilleures.values()])
        return options

    def choisir(self, chaine, mots, analyses, inverses, entrees):
        import kenlm

        options = self._options(chaine, mots, analyses, inverses, entrees)
        if all(len(o) == 1 for o in options):
            return entrees
        depart = kenlm.State()
        self.lm.BeginSentenceWrite(depart)
        faisceau = [(0.0, depart, [])]             # (score, état du modèle, choix)
        for opts in options:
            suivants = []
            for score, etat, choix in faisceau:
                for k, (_, ecrits, note) in enumerate(opts):
                    s, courant = score + self.poids * note, etat
                    for w in ecrits:
                        nouvel = kenlm.State()
                        s += _LN10 * self.lm.BaseScore(courant, w, nouvel)
                        courant = nouvel
                    suivants.append((s, courant, choix + [k]))
            # Recombinaison : un seul chemin par contexte du modèle de langue.
            suivants.sort(key=lambda x: -x[0])
            vus, faisceau = set(), []
            for s, etat, choix in suivants:
                if etat in vus:
                    continue
                vus.add(etat)
                faisceau.append((s, etat, choix))
                if len(faisceau) >= self.largeur:
                    break
        fin = []
        for s, etat, choix in faisceau:
            sortie = kenlm.State()
            fin.append((s + _LN10 * self.lm.BaseScore(etat, "</s>", sortie), choix))
        _, choix = max(fin, key=lambda x: x[0])
        return [opts[k][0] for opts, k in zip(options, choix)]
