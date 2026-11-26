# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Inventaire phonétique anglais (General American, spec `NLP_EN/Lexique/spec/02_phonetique.md`) et outils communs.

Copie de `NLP_EN/Modeles/communs/utils/ipa_en.py` (le Module ne dépend pas des Modèles) : diphtongues et affriquées
= un phonème (eɪ aɪ ɔɪ aʊ oʊ tʃ dʒ) ; ɹ ; ɝ / ɚ ; ʌ / ə. Marques : « . » syllabe, « ˈ » « ˌ » accent (à la place du
point de la syllabe qu'il ouvre), « ‿ » syllabe ou mot enchaîné.
"""

from __future__ import annotations

VOYELLES = ("ɑ", "æ", "ɔ", "aʊ", "aɪ", "ɛ", "eɪ", "ɪ", "i", "oʊ", "ɔɪ", "ʊ", "u", "ʌ", "ə", "ɝ", "ɚ")
CONSONNES = ("b", "tʃ", "d", "ð", "f", "ɡ", "h", "dʒ", "k", "l", "m", "n", "ŋ", "p", "ɹ", "s", "ʃ", "t", "θ", "v",
             "w", "j", "z", "ʒ")
PHONEMES = frozenset(VOYELLES + CONSONNES)
_PAR_LONGUEUR = sorted(PHONEMES, key=len, reverse=True)
ACCENTS = ("ˈ", "ˌ")
SYLLABE, LIAISON = ".", "‿"
MARQUES = frozenset((SYLLABE, LIAISON) + ACCENTS)
CARACTERES = frozenset("".join(PHONEMES)) | MARQUES
_VOYELLES = frozenset(VOYELLES)
SIFFLANTES = frozenset(("s", "z", "ʃ", "ʒ", "tʃ", "dʒ"))
SOURDES = frozenset(("p", "t", "k", "f", "θ"))
# Voyelles réduites et leur forme pleine sous accent (formes fortes, spec 02 §6).
PLEINES = {"ə": "ʌ", "ɚ": "ɝ"}


def phonemes(s: str) -> list[str] | None:
    """Découpe une suite de phonèmes sans marques (glouton, plus long d'abord) ; ``None`` si un caractère en sort."""
    resultat, i = [], 0
    while i < len(s):
        for p in _PAR_LONGUEUR:
            if s.startswith(p, i):
                resultat.append(p)
                i += len(p)
                break
        else:
            return None
    return resultat


def unites(s: str) -> list[str]:
    """Phonèmes et marques d'une chaîne (marques gardées, espaces et caractères inconnus gardés seuls)."""
    resultat, i = [], 0
    while i < len(s):
        for p in _PAR_LONGUEUR:
            if s.startswith(p, i):
                resultat.append(p)
                i += len(p)
                break
        else:
            resultat.append(s[i])
            i += 1
    return resultat


def sans_marques(phone: str) -> str:
    """Clé de recherche : phonèmes seuls (ni syllabe, ni accent, ni ‿, ni espace) — tolérante à l'accent."""
    return "".join(c for c in phone if c not in MARQUES and not c.isspace())


def sans_accent(phone: str) -> str:
    return phone.replace("ˈ", "").replace("ˌ", "")


def est_voyelle(p: str) -> bool:
    return p in _VOYELLES


def premier_phoneme(phone: str) -> str:
    ph = phonemes(sans_marques(phone))
    return ph[0] if ph else ""


def dernier_phoneme(phone: str) -> str:
    ph = phonemes(sans_marques(phone))
    return ph[-1] if ph else ""


def commence_par_voyelle(phone: str) -> bool:
    """Le premier phonème est une voyelle (j et w sont des consonnes : *a university*, *a one*)."""
    return est_voyelle(premier_phoneme(phone))


def finit_par_consonne(phone: str) -> bool:
    d = dernier_phoneme(phone)
    return bool(d) and not est_voyelle(d)


def nombre_de_syllabes(phone: str) -> int:
    return sum(1 for p in phonemes(sans_marques(phone)) or () if est_voyelle(p))


def assimiler_s(hote: str) -> str:
    """RE8 : réalisation de *'s* après la prononciation ``hote`` : ɪz après sifflante, s après sourde, z sinon."""
    d = dernier_phoneme(hote)
    if d in SIFFLANTES:
        return "ɪz"
    if d in SOURDES:
        return "s"
    return "z"
