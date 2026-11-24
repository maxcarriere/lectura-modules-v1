# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Mode local : les fonctions lexicales lisent une base au format rapide sur la machine ; rien ne passe par le réseau.

Le paquet ne contient aucune base. On en obtient une : (1) en la construisant depuis un lexique que l'on possède
(``python -m lectura_lexicon convertir``, depuis LeXiK téléchargée, Lexique 3, GLAFF ou un CSV/TSV) ; (2) avec la
licence commerciale de Lectura (bases prêtes à l'emploi, ``python -m lectura_lexicon installer``).
"""

from __future__ import annotations

from ._lexicon import FONCTIONS, Lexicon, _langue


def moteur(langue: str):
    """Module du moteur local de la langue (``lectura_lexicon.fr`` ou ``lectura_lexicon.en``)."""
    if _langue(langue) == "fr":
        from .fr import lexicon as m
    else:
        from .en import lexicon as m
    return m


class LexiconLocal(Lexicon):
    """Lexicon sur une base locale. Toutes les fonctions du moteur de la langue sont disponibles, plus le dictionnaire
    de l'utilisateur (``ajouter``, ``retirer``) et les seuils de validité (``seuils``)."""

    mode = "local"

    def __init__(self, chemin=None, langue: str = "fr", taille: str | None = None, mode: str | None = None,
                 api: str | None = None, cle: str | None = None, delai: float = 10.0, seuils=None,
                 dictionnaire=None, cache: int = 0):
        self.langue = _langue(langue)
        if chemin is not None:
            from pathlib import Path

            from .nue import est_nue, indexee

            if Path(chemin).is_file() and est_nue(Path(chemin)):   # base nue : indexée une fois, dans le cache
                chemin = indexee(Path(chemin))
        self._moteur = moteur(self.langue).Lexicon(chemin, taille, seuils, dictionnaire)

    def __repr__(self) -> str:
        return f"LexiconLocal(langue={self.langue!r}, chemin={str(self.chemin)!r}, taille={self.taille!r})"

    def __getattr__(self, nom: str):
        # appelé seulement pour ce que LexiconLocal et Lexicon ne définissent pas
        if nom.startswith("__") or nom == "_moteur":
            raise AttributeError(nom)
        if nom in _AUTRE_LANGUE[self.langue]:
            raise AttributeError(f"« {nom} » n'existe pas en « {self.langue} » (fonctions : "
                                 f"{', '.join(FONCTIONS[self.langue])})")
        return getattr(self._moteur, nom)

    def __dir__(self):
        """Noms de Lexicon et du moteur de la langue (fonctions déléguées comprises), sans ceux de l'autre langue."""
        noms = set(super().__dir__()) | {n for n in dir(self._moteur) if not n.startswith("__")}
        return sorted(noms - _AUTRE_LANGUE[self.langue])

    @property
    def moteur(self):
        """Moteur de la langue (``fr.lexicon.Lexicon`` ou ``en.lexicon.Lexicon``) : utile aux branchements internes
        (``lectura_lexicon.fr.transducer.brancher``)."""
        return self._moteur

    def fermer(self) -> None:
        self._moteur.fermer()


_AUTRE_LANGUE = {"fr": set(FONCTIONS["en"]) - set(FONCTIONS["fr"]), "en": set(FONCTIONS["fr"]) - set(FONCTIONS["en"])}
