# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Modèle de langue des homophones (table compacte de l'instance Modèles), sans dépendance au code d'entraînement.

``score(gauche, candidat, droite)`` = log P(candidat | gauche) + log P(droite | candidat). Table triée d'empreintes
CRC-32 (UTF-8 de « gauche droite ») → log-probabilité quantifiée sur 8 bits (pas de 0,1 nat) ; repli sur la fréquence
du mot seul (× 0,4). Minuscules, ``<s>`` et ``</s>`` aux bords, ponctuation comme mot. Même calcul que
``ModeleLangueCompact`` (``Modeles/etiquetage/modele_langue.py``).
"""

from __future__ import annotations

import math
import zlib
from pathlib import Path

PAS = 0.1
REPLI = math.log(0.4)


def empreinte(texte: str) -> int:
    return zlib.crc32(texte.encode("utf-8")) & 0xFFFFFFFF


class ModeleLangue:
    def __init__(self, chemin: str | Path):
        import numpy as np

        self._np = np
        z = np.load(Path(chemin))
        self._ch, self._cq, self._mh, self._mq = z["couples_h"], z["couples_q"], z["mots_h"], z["mots_q"]
        self._inconnu = -PAS * float(z["inconnu_q"][0])

    def _cherche(self, h, q, cle: int) -> float | None:
        cle = self._np.uint32(cle)
        k = int(self._np.searchsorted(h, cle))
        return -PAS * float(q[k]) if k < len(h) and h[k] == cle else None

    def _logp(self, droite: str, gauche: str) -> float:
        lp = self._cherche(self._ch, self._cq, empreinte(gauche + " " + droite))
        if lp is not None:
            return lp
        u = self._cherche(self._mh, self._mq, empreinte(droite))
        return REPLI + (u if u is not None else self._inconnu)

    def score(self, gauche: str, candidat: str, droite: str) -> float:
        return self._logp(candidat, gauche) + self._logp(droite, candidat)
