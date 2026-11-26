# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Moteur de traduction local : découpage en phrases par l'Analyseur de la langue source, traduction phrase par phrase
par OPUS-MT (CTranslate2 int8 + sentencepiece, processeur ou GPU, sans transformers ni torch), formules protégées.

Les phrases gardent leurs positions dans le texte source (``debut``, ``fin``) : c'est l'appui de l'alignement mot à
mot et du glossaire en contexte.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

# CTranslate2 (OpenMP) : attente passive des fils, nettement plus rapide quand la machine est chargée (−30 % de temps
# mesuré à charge 22 sur 12 cœurs) ; sans effet notable sur une machine libre. Modifiable avant l'import.
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

from . import analyseurs  # noqa: E402
from .modeles import dossier_traduction  # noqa: E402

SPECIAUX = {"</s>", "<unk>", "<pad>", "<s>"}


def normaliser(phrase: str) -> str:
    """Apostrophes typographiques → ' (inconnues des modèles de base : <unk>)."""
    return phrase.replace("’", "'").replace("‘", "'")


@dataclass
class Phrase:
    source: str
    debut: int
    fin: int
    traduction: str = ""


def decouper_phrases(texte: str, langue: str) -> list[Phrase]:
    """Phrases du texte selon le découpage de l'Analyseur ; chaque phrase est la tranche du texte d'origine."""
    phrases = []
    for mots in analyseurs.decouper(langue)(texte):
        if not mots:
            continue
        debut, fin = mots[0].debut, mots[-1].fin
        phrases.append(Phrase(texte[debut:fin], debut, fin))
    return phrases


class MoteurOpus:
    """Un sens de traduction (``source`` → ``cible``), modèle OPUS-MT ``base`` ou ``big`` en CTranslate2 int8."""

    def __init__(self, source: str = "en", cible: str = "fr", taille: str = "base", gpu: bool = False, fils: int = 4,
                 faisceau: int = 2, lot: int = 16, models_dir=None):
        self.source, self.cible, self.taille = source, cible, taille
        self.faisceau, self.lot = faisceau, lot
        self.repli = 0
        dossier = dossier_traduction(source, cible, taille, models_dir)
        if gpu:
            try:  # fournit libcublas / libcudnn (paquets nvidia de torch) à CTranslate2 ; inutile sur processeur
                import torch  # noqa: F401
            except ImportError:
                pass
        try:
            import ctranslate2
            import sentencepiece as spm
        except ImportError as e:
            raise ImportError(f"mode local : {e.name} absent ; pip install \"lectura-traducteur[local]\"") from e
        self.sp_source = spm.SentencePieceProcessor(model_file=str(dossier / "source.spm"))
        self.sp_cible = spm.SentencePieceProcessor(model_file=str(dossier / "target.spm"))
        self.modele = ctranslate2.Translator(str(dossier), device="cuda" if gpu else "cpu",
                                             compute_type="int8_float16" if gpu else "int8",
                                             inter_threads=1, intra_threads=fils)

    def proteger(self, phrase: str, repere: str = "nombre") -> tuple[str, dict[str, tuple[str, str]]]:
        """Remplace les formules convertibles : dates et heures par un substitut du même type (le traducteur choisit
        la préposition), les autres par un repère numérique (901, 902…). Rend la phrase et
        {clé: (motif regex à chercher dans la traduction, forme convertie)}."""
        from .formules import convertir, substitut
        morceaux, table, pos, rangs = [], {}, 0, {}
        for mots in analyseurs.decouper(self.source)(phrase):
            for m in mots:
                if m.type != "formule" or m.type_formule == "ordinal" or m.debut < pos:
                    continue
                forme, type_f, fin = m.forme, m.type_formule, m.fin
                suite = phrase[fin:]
                if self.source == "en" and type_f == "nombre":
                    # heure à la britannique que l'Analyseur coupe en deux : 2.15pm, 3.30 p.m.
                    e = re.match(r"\s?(a\.m\.|p\.m\.|am\b|pm\b|AM\b|PM\b)", suite)
                    if e and re.fullmatch(r"\d{1,2}(?:[.:]\d{2})?", forme):
                        forme, type_f, fin = forme + e.group(0), "heure", fin + e.end()
                if type_f == "monnaie":
                    # échelle détachée : $700-billion, $5 billion
                    e = re.match(r"-?\s?(million|billion|trillion|bn)\b", suite)
                    if e and not re.search(r"[a-zA-Z]$", forme):
                        forme, fin = forme + " " + e.group(1), fin + e.end()
                conv = convertir(forme, type_f, self.source, self.cible)
                if conv is None or (conv == forme and type_f == "nombre"):
                    continue
                n = rangs.get(type_f, 0)
                sub = substitut(type_f, forme, conv, self.source, n)
                if sub:
                    rangs[type_f] = n + 1
                    texte, motif = sub
                else:
                    texte = f"{901 + len(table)}" if repere == "nombre" else f"X{len(table) + 1}"
                    motif = rf"(?<![\w.,]){re.escape(texte)}(?![\w]|[.,]\d)"
                table[texte] = (motif, conv)
                morceaux += [phrase[pos:m.debut], texte]
                pos = fin
        morceaux.append(phrase[pos:])
        return "".join(morceaux), table

    @staticmethod
    def restaurer(traduction: str, table: dict[str, tuple[str, str]]) -> str | None:
        """Remet les formules ; ``None`` si un repère a disparu ou a été dédoublé."""
        for motif, conv in table.values():
            if len(re.findall(motif, traduction)) != 1:
                return None
            traduction = re.sub(motif, lambda _: conv, traduction)
        return traduction

    def traduire_phrases(self, phrases: list[str], formules: bool = True, repere: str = "nombre") -> list[str]:
        """Avec ``formules`` : formules protégées par des repères, puis remises converties ; si un repère se perd,
        traduction sans protection pour cette phrase."""
        if not formules:
            return self._traduire(phrases)
        proteges = [self.proteger(p, repere) for p in phrases]
        sorties = self._traduire([p for p, _ in proteges])
        a_refaire = []
        for k, ((_, table), t) in enumerate(zip(proteges, sorties)):
            if table:
                r = self.restaurer(t, table)
                if r is None:
                    a_refaire.append(k)
                else:
                    sorties[k] = r
        self.repli = len(a_refaire)
        if a_refaire:
            for k, t in zip(a_refaire, self._traduire([phrases[k] for k in a_refaire])):
                sorties[k] = t
        return sorties

    def _traduire(self, phrases: list[str]) -> list[str]:
        sorties = []
        for i in range(0, len(phrases), self.lot):
            lot = phrases[i:i + self.lot]
            jetons = [self.sp_source.encode(normaliser(p), out_type=str)[:510] + ["</s>"] for p in lot]
            res = self.modele.translate_batch(jetons, beam_size=self.faisceau, max_decoding_length=512)
            sorties += [self.sp_cible.decode([t for t in r.hypotheses[0] if t not in SPECIAUX]).strip()
                        for r in res]
        return sorties
