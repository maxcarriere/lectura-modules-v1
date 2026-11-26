# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Modèle de langue du texte écrit anglais (KenLM, n-grammes de mots) : juge des candidats du correcteur.

Découpe en mots (``mots_ecrits``, la même à la construction et à l'usage) : minuscules, apostrophe droite, contractions
et possessifs gardés entiers (« it's », « don't », « they're », « workers' ») — c'est ce qui départage its / it's,
your / you're —, mots à trait d'union entiers, nombres → ``<nombre>``, ponctuation retirée.
"""

from __future__ import annotations

import re
from pathlib import Path

_MOT = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+(?:['-][^\W\d_]+)*(?:(?<=s)')?")   # « ' » final : possessif pluriel seul


def mots_ecrits(texte: str) -> list[str]:
    """Texte → mots du modèle de langue écrit."""
    texte = texte.lower().replace("’", "'").replace("‘", "'")
    return ["<nombre>" if m[0].isdigit() else m for m in _MOT.findall(texte)]


class Juge:
    """log10 P(phrase) par le modèle de langue écrit."""

    def __init__(self, chemin: str | Path):
        import kenlm

        self._lm = kenlm.Model(str(chemin))

    def note(self, texte: str) -> float:
        return self._lm.score(" ".join(mots_ecrits(texte)), bos=True, eos=True)
