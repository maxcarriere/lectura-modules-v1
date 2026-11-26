# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Découpage d'une chaîne à séparateurs en mots (spec 01 §6).

Une chaîne est une suite de segments reliés par des apostrophes et des tirets, sans
espace (``qu'est-ce``, ``grand-père``, ``donne-le-moi``). La règle est la même pour
l'orthographe et pour la phonétique ; seules les tables changent.

- une forme élidée initiale est un mot (``j'`` + ``aime``) ;
- un clitique final à tiret est un mot (``veux`` + ``-tu``, ``donne`` + ``-le`` + ``-moi``) ;
- ``-t-`` suivi d'un sujet forme un seul mot de deux segments (``a`` + ``-t-il``) ;
- tout le reste est un seul mot (``grand-père``, ``aujourd'hui``), ainsi que les
  mots de la liste fermée des lexicalisés (``rendez-vous``, ``quelqu'un``).
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

SEG, APO, TIR = "seg", "apo", "tir"


@dataclass(frozen=True)
class Piece:
    nature: str          # SEG, APO ou TIR
    forme: str           # forme normalisée (« ' » et « - » pour les séparateurs)
    debut: int
    fin: int
    syllabes: tuple[str, ...] = ()
    jonction: str = ""


@dataclass(frozen=True)
class Tables:
    elidees: frozenset[str]        # segments qui, suivis d'une apostrophe, forment un mot
    clitiques: frozenset[str]      # segments qui, précédés d'un tiret, forment un mot
    sujets: frozenset[str]         # clitiques sujets admis après le t euphonique
    t_euphonique: str
    elides_apres_tiret: frozenset[str]   # « -t' », « -m' » (va-t'en, donne-m'en)
    apres_elide: frozenset[str]          # « en », « y »
    lexicalises: frozenset[str]
    # Initiales à apostrophe de noms propres (« M'Bae », « N'Diaye ») : pas une élision
    # quand la lettre et le segment suivant ont tous deux une majuscule.
    initiales_propres: frozenset[str] = frozenset()
    # « -tu » seul en début de chaîne est-il un clitique ? Non à l'écrit, où un tiret
    # collé en début de mot est le plus souvent un tiret de dialogue.
    clitique_isole_simple: bool = False


def _charger_liste(nom: str) -> frozenset[str]:
    texte = resources.files("lectura_nlp_en.analyseur.data").joinpath(nom).read_text(encoding="utf-8")
    return frozenset(
        ligne.strip() for ligne in texte.splitlines() if ligne.strip() and not ligne.startswith("#")
    )


TABLES_ORTHO = Tables(
    elidees=frozenset(
        "j l d n s m t c ç qu jusqu lorsqu puisqu quoiqu presqu quelqu".split()
    ),
    clitiques=frozenset(
        "je tu il elle on nous vous ils elles ce y en le la les lui leur moi toi t là ci".split()
    ),
    sujets=frozenset("il elle on ils elles".split()),
    t_euphonique="t",
    elides_apres_tiret=frozenset({"t", "m"}),
    apres_elide=frozenset({"en", "y"}),
    lexicalises=_charger_liste("mots_lexicalises.txt"),
    initiales_propres=frozenset({"M", "N", "T"}),
)

TABLES_PHONE = Tables(
    elidees=frozenset("ʒ l d n s m t k ʒysk lɔʁsk pɥisk kwak pʁɛsk kɛlk".split()),
    clitiques=frozenset(
        "ʒə ty il ɛl ɔ̃ nu vu sə i ɑ̃ lə la le lɥi lœʁ mwa twa t si".split()
    ),
    sujets=frozenset("il ɛl ɔ̃".split()),
    t_euphonique="t",
    elides_apres_tiret=frozenset({"t", "m"}),
    apres_elide=frozenset({"ɑ̃", "i"}),
    lexicalises=_charger_liste("mots_lexicalises_phone.txt"),
    clitique_isole_simple=True,
)


def _cle(pieces: list[Piece]) -> str:
    return "".join(p.forme for p in pieces).lower()


def decouper_chaine(pieces: list[Piece], tables: Tables) -> list[list[Piece]]:
    """Renvoie les mots de la chaîne, chacun comme liste de pièces.

    Un mot réduit à un séparateur seul (apostrophe finale non élidée, tiret initial)
    est une ponctuation ; c'est à l'appelant de le typer.
    """
    if not pieces:
        return []
    if _cle(pieces) in tables.lexicalises:
        return [pieces]

    premier, dernier = pieces[0], pieces[-1]

    if premier.nature == TIR and not _est_clitique_isole(pieces, tables):
        return [[premier]] + decouper_chaine(pieces[1:], tables)

    if dernier.nature == APO:
        if len(pieces) == 2 and premier.forme.lower() in tables.elidees:
            return [pieces]
        return decouper_chaine(pieces[:-1], tables) + [[dernier]]

    if (
        len(pieces) >= 3
        and premier.nature == SEG
        and pieces[1].nature == APO
        and premier.forme.lower() in tables.elidees
        and not (premier.forme in tables.initiales_propres and pieces[2].forme[:1].isupper())
    ):
        return [pieces[:2]] + decouper_chaine(pieces[2:], tables)

    # va-t'en, donne-m'en : « -t' » + « en »
    if (
        len(pieces) >= 5
        and pieces[-4].nature == TIR
        and pieces[-3].forme.lower() in tables.elides_apres_tiret
        and pieces[-2].nature == APO
        and dernier.forme.lower() in tables.apres_elide
    ):
        return decouper_chaine(pieces[:-4], tables) + [pieces[-4:-1], pieces[-1:]]

    if len(pieces) >= 3 and pieces[-2].nature == TIR and dernier.forme.lower() in tables.clitiques:
        if (
            len(pieces) >= 4
            and pieces[-4].nature == TIR
            and pieces[-3].forme.lower() == tables.t_euphonique
            and dernier.forme.lower() in tables.sujets
        ):
            return decouper_chaine(pieces[:-4], tables) + [pieces[-4:]]
        return decouper_chaine(pieces[:-2], tables) + [pieces[-2:]]

    return [pieces]


def _est_clitique_isole(pieces: list[Piece], tables: Tables) -> bool:
    """« -tu », « -t-il » écrits seuls (entrée du lexique, clitique détaché par une espace)."""
    formes = [p.forme.lower() for p in pieces]
    if len(pieces) == 2:
        return tables.clitique_isole_simple and formes[1] in tables.clitiques
    if len(pieces) == 4 and pieces[2].nature == TIR:
        return formes[1] == tables.t_euphonique and formes[3] in tables.sujets
    return False
