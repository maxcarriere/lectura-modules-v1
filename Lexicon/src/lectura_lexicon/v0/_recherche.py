# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Fonctions de recherche : rechercher, filtrer, anagrammes."""

from __future__ import annotations

import re
from typing import Any, Iterable


def rechercher(
    index: dict[str, list[dict[str, Any]]],
    pattern: str,
    champ: str = "ortho",
    limite: int = 50,
) -> list[dict[str, Any]]:
    """Regex sur ortho ou phone.

    Args:
        index: Index (ortho ou phone) -> [entrees]
        pattern: Expression reguliere a chercher
        champ: Champ a tester ("ortho" ou "phone")
        limite: Nombre max de resultats

    Returns:
        Liste d'entrees correspondantes, triees par frequence
    """
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return []

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for _key, entries in index.items():
        for e in entries:
            valeur = str(e.get(champ, "") or "")
            if valeur and regex.search(valeur):
                ortho = str(e.get("ortho", "") or "").lower()
                if ortho not in seen:
                    seen.add(ortho)
                    results.append(e)

    results.sort(key=lambda x: -float(x.get("freq", 0) or 0))
    return results[:limite]


def _nombre_ou_none(valeur: Any) -> float | None:
    """Convertit une valeur de cellule en nombre ; vide ou illisible -> None."""
    if valeur is None or valeur == "":
        return None
    try:
        return float(valeur)
    except (ValueError, TypeError):
        return None


def filtrer(
    entries_iter: Iterable[dict[str, Any]],
    *,
    cgram: str | None = None,
    genre: str | None = None,
    nombre: str | None = None,
    freq_min: float | None = None,
    freq_max: float | None = None,
    nb_syllabes: int | None = None,
    age_min: float | None = None,
    age_max: float | None = None,
    illustrable_min: float | None = None,
    categorie: str | None = None,
    has_age: bool | None = None,
    has_phone: bool | None = None,
    mode: str | None = None,
    temps: str | None = None,
    personne: str | None = None,
    limite: int = 100,
) -> list[dict[str, Any]]:
    """Filtre multi-critere sur un iterateur d'entrees.

    Memes criteres que la version SQLite. Une valeur absente ou vide
    ne satisfait pas un critere qui la demande (comme NULL en SQL),
    sauf ``has_age=False`` et ``has_phone=False``.

    Args:
        entries_iter: Iterateur d'entrees lexicales
        cgram: Filtre POS (prefix match)
        genre: Filtre genre (egalite stricte, ex. m/f)
        nombre: Filtre nombre (egalite stricte, ex. s/p)
        freq_min: Frequence minimale
        freq_max: Frequence maximale
        nb_syllabes: Nombre exact de syllabes
        age_min, age_max: Bornes sur la colonne ``age``
        illustrable_min: Minimum sur la colonne ``illustrable``
        categorie: Egalite sur la colonne ``categorie``
        has_age: True = ``age`` renseigne, False = ``age`` vide
        has_phone: True = ``phone`` renseigne, False = ``phone`` vide
        mode, temps, personne: Egalite stricte sur ces colonnes
        limite: Nombre max de resultats (0 ou moins = pas de limite)

    Returns:
        Liste d'entrees correspondantes
    """
    results: list[dict[str, Any]] = []
    egalites = {
        "genre": genre, "nombre": nombre, "categorie": categorie,
        "mode": mode, "temps": temps, "personne": personne,
    }
    egalites = {k: v for k, v in egalites.items() if v is not None}

    for e in entries_iter:
        if cgram is not None:
            e_cgram = str(e.get("cgram", "") or "")
            if not e_cgram.startswith(cgram):
                continue

        if any(str(e.get(k, "") or "") != str(v) for k, v in egalites.items()):
            continue

        freq = 0.0
        try:
            freq = float(e.get("freq", 0) or 0)
        except (ValueError, TypeError):
            pass

        if freq_min is not None and freq < freq_min:
            continue
        if freq_max is not None and freq > freq_max:
            continue

        if nb_syllabes is not None:
            nb = _get_nb_syllabes(e)
            if nb != nb_syllabes:
                continue

        age = _nombre_ou_none(e.get("age"))
        if has_age is True and age is None:
            continue
        if has_age is False and age is not None:
            continue
        if age_min is not None and (age is None or age < age_min):
            continue
        if age_max is not None and (age is None or age > age_max):
            continue

        if illustrable_min is not None:
            illu = _nombre_ou_none(e.get("illustrable"))
            if illu is None or illu < illustrable_min:
                continue

        if has_phone is not None:
            a_phone = bool(str(e.get("phone", "") or ""))
            if a_phone != has_phone:
                continue

        results.append(e)
        if limite > 0 and len(results) >= limite:
            break

    return results


def anagrammes(
    ortho_index: dict[str, list[dict[str, Any]]],
    mot: str,
    limite: int = 50,
) -> list[dict[str, Any]]:
    """Mots avec les memes lettres rearrangees.

    Exclut le mot lui-meme. Trie par frequence.

    Args:
        ortho_index: Index ortho -> [entrees]
        mot: Mot de reference
        limite: Nombre max de resultats

    Returns:
        Liste d'entrees anagrammes
    """
    mot_lower = mot.strip().lower()
    mot_sorted = sorted(mot_lower)
    results: list[dict[str, Any]] = []

    for ortho, entries in ortho_index.items():
        if ortho == mot_lower:
            continue
        if sorted(ortho) == mot_sorted:
            # Prendre la premiere entree du groupe
            if entries:
                results.append(entries[0])

    results.sort(key=lambda x: -float(x.get("freq", 0) or 0))
    return results[:limite]


def _get_nb_syllabes(entry: dict[str, Any]) -> int | None:
    """Extrait le nombre de syllabes d'une entree."""
    nb_raw = entry.get("nb_syllabes") or entry.get("nbsyll")
    if nb_raw is not None:
        try:
            return int(nb_raw)
        except (ValueError, TypeError):
            pass

    syllabes = str(entry.get("syllabes", "") or entry.get("syll", "") or "")
    if syllabes:
        return syllabes.count(".") + 1

    return None
