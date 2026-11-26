# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Règles d'accord sur l'analyse, en phonétique → orthographe (phase de correction, 2026-10-10).

Couche optionnelle : ``Chaine.correcteur = Accords(...)`` ; sans elle, la chaîne n'en dépend pas. Chaque règle corrige
les traits prédits d'un mot (nombre, genre) d'après ses dépendances prédites, avant le choix de la graphie parmi les
homophones (« était » / « étaient » se départagent sur ``Number``). Une règle ne s'applique que si les arcs qu'elle
emprunte sont sûrs : probabilité du biaffine (``Analyse.confiance_tete``) au moins ``seuil``.

Règles (chacune mesurée seule sur le banc, ``outils/banc_correction.py``) :

- ``coordination`` : verbe, auxiliaire ou attribut dont le sujet a un dépendant ``conj`` → pluriel
  (« la science et la superstition étaient ») ;
- ``sujet`` : verbe conjugué ou auxiliaire → nombre de son sujet tel qu'il s'entend (déterminant le / les, pronom
  il / ils trahi par la liaison) ; le nombre prédit d'un sujet homophone (il / ils, relation / relations) n'est pas
  plus sûr que celui du verbe (accord à distance : « les enfants de la voisine jouaient ») ;
- ``nom`` : adjectif (``amod``) et déterminant (``det``) → nombre et genre de leur nom ;
- ``participe`` : participe passé conjugué avec « avoir » → masculin singulier (sans complément antéposé), hors
  passif (« a été déçue ») ;
- ``meme_lemme`` : entre flexions d'un même lemme (besoin / besoins), les traits prédits décident, pas la tête de
  graphie (réglage de la chaîne, ``Chaine.tete_meme_lemme``) ;
- ``upos`` : candidates de catégories différentes (eux / euh, a / à) : la catégorie prédite, si sa confiance atteint
  ``seuil_upos``, l'emporte sur la tête de graphie (``Chaine.tete_upos``).
"""

from __future__ import annotations

from dataclasses import replace

from lectura_nlp_fr.analyseur.analyse import Analyse
from lectura_nlp_fr.analyseur.recomposition import AMBIGU, LIAISON

REGLES = ("coordination", "sujet", "nom", "participe", "meme_lemme", "upos")
# Règles retenues (décision de l'utilisateur, 10/10) : « coordination », neutre sur l'oracle et +5 sur les phrases d'accord.
RETENUES = ("coordination",)
_PREDICATS = {"VERB", "AUX", "ADJ"}
# Nombre qui s'entend : déterminants de prononciation propre au singulier ou au pluriel (« leur » ne dit rien).
_DET_SING = {"lə", "la", "l", "œ̃", "yn", "sə", "sɛt", "sɛ", "mɔ̃", "ma", "tɔ̃", "ta", "sɔ̃", "sa", "nɔtʁ", "vɔtʁ", "kɛl", "ʃak"}
_DET_PLUR = {"le", "de", "se", "me", "te", "no", "vo", "kɛlz", "ply.zjœʁ", "plyzjœʁ"}
_VOYELLES = set("aeiouyɛɔøœəɑɑ̃ɛ̃ɔ̃œ̃")


def _phone(m) -> str:
    """Prononciation du mot sans la consonne de liaison (« lez » → « le »)."""
    if m is None or not getattr(m, "segments", None):
        return ""
    if m.jonction == LIAISON and m.forme_isolee:
        return m.forme_isolee.replace(".", "")
    return "".join(s.forme for s in m.segments).replace(".", "")


def _nombre(a: Analyse, nombre: str, genre: str | None = None) -> Analyse:
    feats = dict(a.feats)
    if "Number" in feats or a.upos in ("VERB", "AUX", "ADJ", "DET", "NOUN", "PRON"):
        feats["Number"] = nombre
    if genre and ("Gender" in feats or a.upos in ("ADJ", "DET")):
        feats["Gender"] = genre
    return replace(a, feats=feats)


class Accords:
    def __init__(self, regles: tuple[str, ...] | list[str] = RETENUES, seuil: float = 0.9, seuil_upos: float = 0.9):
        inconnues = set(regles) - set(REGLES)
        if inconnues:
            raise ValueError(f"Règles inconnues : {sorted(inconnues)} ({', '.join(REGLES)})")
        self.regles, self.seuil, self.seuil_upos = tuple(regles), seuil, seuil_upos
        self.journal: list[tuple[str, int, str]] = []          # (règle, position, trait posé) de la dernière phrase

    def brancher(self, chaine) -> None:
        chaine.correcteur = self
        chaine.tete_meme_lemme = "meme_lemme" not in self.regles
        chaine.tete_upos = self.seuil_upos if "upos" in self.regles else None

    def _sur(self, a: Analyse) -> bool:
        return a.tete is not None and a.tete >= 0 and a.confiance_tete >= self.seuil

    def ajuster_phone(self, mots, analyses: list[Analyse]) -> list[Analyse]:
        r = list(analyses)
        self.journal = []
        n = len(r)
        enfants: dict[int, list[int]] = {}
        for i, a in enumerate(r):
            if a.tete is not None and 0 <= a.tete < n:
                enfants.setdefault(a.tete, []).append(i)

        def poser(regle: str, i: int, nouvelle: Analyse) -> None:
            if nouvelle.feats != r[i].feats:
                # La tête de graphie (+3 points) l'emporterait sur le trait corrigé (2 points) : elle se tait ici.
                r[i] = replace(nouvelle, graphie="")
                self.journal.append((regle, i, "|".join(f"{k}={v}" for k, v in sorted(nouvelle.feats.items()))))

        def audible(i: int) -> str | None:
            """Nombre du groupe nominal ou du pronom sujet ``i`` tel qu'il s'entend, sinon None."""
            a = r[i]
            if a.upos in ("NOUN", "PROPN"):
                for k in enfants.get(i, []):
                    if r[k].relation == "det" and k < i:
                        ph = _phone(mots[k] if k < len(mots) else None)
                        if ph in _DET_SING:
                            return "Sing"
                        if ph in _DET_PLUR:
                            return "Plur"
                return None
            if a.upos == "PRON" and a.lemme in ("il", "elle") and i + 1 < len(mots) and mots[i] is not None:
                m = mots[i]
                if m.jonction in (LIAISON, AMBIGU) and _phone(m) != "".join(s.forme for s in m.segments).replace(".", ""):
                    return "Plur"                        # « i.l‿z‿ont » : liaison en z
                suivant = _phone(mots[i + 1])
                if m.jonction != LIAISON and suivant[:1] in _VOYELLES:
                    return "Sing"                        # « il‿a » : pas de liaison devant voyelle
            return None

        def sujet_de(h: int) -> int | None:
            for k in enfants.get(h, []):
                if r[k].relation.startswith("nsubj") and self._sur(r[k]):
                    return k
            return None

        def accordes(h: int) -> list[int]:
            """Le prédicat et ses auxiliaires et copules (« étaient » de « étaient mêlées »)."""
            return [h] + [k for k in enfants.get(h, []) if r[k].relation in ("aux", "aux:pass", "cop", "aux:tense")
                          and r[k].upos in ("AUX", "VERB")]

        if "sujet" in self.regles:
            for h in range(n):
                if r[h].upos not in _PREDICATS:
                    continue
                s = sujet_de(h)
                if s is not None and any(r[c].relation == "conj" for c in enfants.get(s, [])):
                    continue                             # sujet coordonné : règle « coordination »
                nombre = audible(s) if s is not None else None
                if nombre is None:
                    continue
                for k in accordes(h):
                    if r[k].feats.get("VerbForm") == "Fin":
                        poser("sujet", k, _nombre(r[k], nombre))
        if "coordination" in self.regles:
            for h in range(n):
                if r[h].upos not in _PREDICATS:
                    continue
                s = sujet_de(h)
                if s is None or not any(r[c].relation == "conj" and self._sur(r[c]) and r[c].upos in ("NOUN", "PROPN", "PRON")
                                        for c in enfants.get(s, [])):
                    continue
                for k in accordes(h):
                    if r[k].feats.get("VerbForm") == "Fin" or (k == h and r[h].upos == "ADJ"):
                        poser("coordination", k, _nombre(r[k], "Plur"))
        if "nom" in self.regles:
            for i, a in enumerate(r):
                if a.upos in ("ADJ", "DET") and a.relation in ("amod", "det") and self._sur(a):
                    t = r[a.tete]
                    if t.upos in ("NOUN", "PROPN") and "Number" in t.feats:
                        poser("nom", i, _nombre(a, t.feats["Number"], t.feats.get("Gender")))
        if "participe" in self.regles:
            for i, a in enumerate(r):
                if a.upos != "VERB" or a.feats.get("VerbForm") != "Part" or a.feats.get("Tense") != "Past":
                    continue
                if any(r[k].relation == "aux:pass" for k in enfants.get(i, [])):
                    continue                             # passif (« a été déçue ») : il s'accorde avec le sujet
                if any(r[k].relation == "aux:tense" and r[k].lemme == "avoir" and self._sur(r[k]) for k in enfants.get(i, [])):
                    poser("participe", i, _nombre(a, "Sing", "Masc"))
        return r
