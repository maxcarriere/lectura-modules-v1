# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Candidats hors du P2G et leur juge en contexte.

- Mots inconnus du lexique : voisins orthographiques (distance ≤ 2) et phonétiques (prononciation lue par le modèle de
  mot, tolérance 1), donnés par `lectura_lexicon`.
- Flexions audibles (un / une, est / sont, mange / mangeons) : formes du même lemme qui ne diffèrent que par un trait
  (Number, Gender, Person), toutes les autres valeurs gardées.

Juge : modèle de langue écrit (KenLM 4-g du Module, copie figée) sur toute la phrase, plus un a priori
(distance, fréquence). Le modèle de langue est construit sur Wikipédia, de la littérature du domaine public et des
dialogues : ~2 % des phrases de WiCoPaCo dev figurent dans sa part Wikipédia (mesuré le 14/10 sur 300 phrases) ;
FLE, UD et prose n'en dépendent pas.
"""

from __future__ import annotations

import unicodedata

import math
from dataclasses import dataclass
from pathlib import Path

TRAITS_FLEXION = ("Number", "Gender", "Person")
_LN10 = math.log(10)


@dataclass
class Candidat:
    forme: str
    origine: str          # « ortho », « phone », « flexion »
    distance: int
    zipf: float
    score: float = 0.0
    phone: str = ""


class Juge:
    """log10 P(phrase) par le modèle de langue écrit, découpe des mots de la relecture du Module."""

    def __init__(self, chemin: str | Path):
        import kenlm

        from lectura_nlp_fr.analyseur.relecture import mots_ecrits

        self._lm = kenlm.Model(str(chemin))
        self._mots = mots_ecrits

    def note(self, texte: str) -> float:
        return self._lm.score(" ".join(self._mots(texte)), bos=True, eos=True)


def _sans_accents(forme: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", forme) if not unicodedata.combining(ch))


def _traits(feats: str) -> dict[str, str]:
    return dict(t.split("=", 1) for t in feats.split("|") if "=" in t)


# mots-outils qu'on retrouve collés à leur voisin (« croisadeet », « télévisésdont », « participentà »)
_OUTILS = {"de", "et", "à", "ou", "dont", "qui", "que", "en", "la", "le", "les", "un", "une", "des", "du", "sous", "sur",
           "pour", "par", "dans", "mais", "est", "sont", "ont", "pas", "plus", "ne", "on", "il", "ils", "elle", "elles",
           "ce", "ces", "ses", "son", "sa", "au", "aux", "avec", "comme", "où", "puis", "donc", "car", "ni", "si"}


class Generateur:
    def __init__(self, lexique):
        self.lex = lexique                        # lectura_lexicon.Lexicon

    def hors_lexique(self, forme: str, phone: str, elision: bool = True) -> list[Candidat]:
        """Voisins orthographiques (≤ 2) et phonétiques ; une seule entrée par forme (« français » / « Français »
        rendus pareil : marge nulle sinon) ; un voisin qui ne diffère que par les signes diacritiques (« francais »,
        « chateau ») est marqué « accent » (coût plus faible dans le cœur : c'est la faute la plus courante)."""
        vus: dict[str, Candidat] = {}
        bas = forme.lower()
        squelette = _sans_accents(bas)
        for v in self.lex.voisins_orthographiques(bas, distance_max=2, limite=20, validite_min="proposable"):
            cle = v.ortho.lower()
            if v.propre or cle == bas or (cle in vus and vus[cle].zipf >= v.zipf):
                continue
            origine = "accent" if _sans_accents(cle) == squelette else "ortho"
            vus[cle] = Candidat(v.ortho, origine, v.distance, v.zipf)
        if squelette != bas:
            # « aôut » → « août » : deux accents déplacés font une distance 2, noyée parmi les voisins ; les formes de
            # même squelette se cherchent depuis le squelette lui-même
            for v in self.lex.voisins_orthographiques(squelette, distance_max=2, limite=30, validite_min="proposable"):
                cle = v.ortho.lower()
                if v.propre or cle == bas or cle in vus or _sans_accents(cle) != squelette:
                    continue
                vus[cle] = Candidat(v.ortho, "accent", min(2, sum(a != b for a, b in zip(cle, bas)) or 1), v.zipf)
        if phone:
            # même prononciation au timbre près (o/ɔ, e/ɛ, ø/œ : « fote » → « faute », pas « fête ») : distance 0
            for h in self.lex.homophones(phone.strip(), neutre=True):
                cle = h.ortho.lower()
                if h.propre or h.validite != "proposable" or cle == bas or (cle in vus and vus[cle].origine == "accent"):
                    continue
                vus[cle] = Candidat(h.ortho, "phone", 0, h.zipf)       # remplace un voisin orthographique (« faute » à 2)
            for v in self.lex.voisins_phonetiques(phone, tolerance=1)[:20]:
                if v.propre or v.validite != "proposable" or v.ortho.lower() in vus or v.ortho.lower() == bas:
                    continue
                vus[v.ortho.lower()] = Candidat(v.ortho, "phone", v.distance, v.zipf)
        for s in self.scissions(forme):
            parties = s.replace("'", "' ").split()
            # fréquence : celle des parties pleines (le clitique « c' » ou « j' » ne compte pas : « c'est », « j'ai »)
            zipf = min(self.lex.frequence(x) for x in parties if not x.endswith("'")) if any(not x.endswith("'") for x in parties) else 0.0
            vus.setdefault(s, Candidat(s, "scission", 1, zipf))
        if elision and forme[1:].islower():
            # « lortograf » → « l'orthographe », « jaimme » → « j'aime » : apostrophe oubliée devant un mot lui-même mal
            # écrit ; les candidats du reste (voisins proches, même son), précédés du clitique
            for a in self._CLITIQUES_PHONES:
                reste = bas[len(a):]
                if not bas.startswith(a) or len(reste) < 3 or reste[:1] not in "aeiouyhàâéèêëîïôöùûüœ" \
                        or self.lex.validite(reste) == "proposable":
                    continue
                ph = phone.strip(" ‿") if phone else ""
                ph_reste = ph[len(self._CLITIQUES_PHONES[a]):].lstrip(".") if ph.startswith(self._CLITIQUES_PHONES[a]) else ""
                for c in self.hors_lexique(reste, ph_reste, elision=False):
                    # même son exact, une lettre ou un accent : pas « Malietoa » → « M'halitose » (son approché)
                    if (c.origine == "accent" or c.origine == "ortho" and c.distance <= 1 or c.origine == "phone" and c.distance == 0) \
                            and c.forme[:1].islower():
                        f = f"{a}'{c.forme}"
                        vus.setdefault(f, Candidat(f, "elision", c.distance + 1, c.zipf, phone=c.phone))
        return list(vus.values())

    _CLITIQUES_PHONES = {"l": "l", "j": "ʒ", "c": "s", "d": "d", "n": "n", "m": "m", "t": "t", "s": "s", "qu": "k"}

    _ELISIONS = ("l", "d", "c", "s", "j", "n", "m", "t", "qu", "jusqu", "lorsqu", "puisqu", "quoiqu")

    def scissions(self, forme: str) -> list[str]:
        """Deux mots collés (« estsur », « provisoireainsi ») ou apostrophe oubliée (« Lappareil », « sapplique ») :
        coupes dont les deux parties sont des mots proposables du lexique. Pas de coupe dans un mot à majuscule
        intérieure (« PianoSociety », « aiméeOh » : sigle, nom propre, collage de deux phrases)."""
        bas = forme.lower()
        if not bas.isalpha() or len(bas) < 3:
            return []                                         # « jai » → « j'ai » (trois lettres, élision seulement)
        majuscules = [i for i, ch in enumerate(forme) if ch.isupper() and i > 0]
        minuscule = forme[:1].islower()
        res = []
        for i in range(1, len(bas)):
            a, b = bas[:i], bas[i:]
            if len(b) < 2 and b != "à":
                continue                                      # « participentà » : seule « à » fait un mot d'une lettre
            if majuscules and (majuscules != [i] or a not in self._ELISIONS):
                continue                                      # « lAdonis » → « l'Adonis » ; pas « PianoSociety », « aiméeOh »
            if a in self._ELISIONS and b[:1] in "aeiouyhàâéèêëîïôöùûüœ" \
                    and (self.lex.validite(b) == "proposable" or majuscules and self.lex.validite(forme[i:]) == "proposable"):
                res.append(f"{a}'{b}")
            elif i >= 2 and len(bas) >= 4 and self.lex.validite(a) == "proposable" and self.lex.validite(b) == "proposable":
                fa, fb = self.lex.frequence(a), self.lex.frequence(b)
                # deux mots courants, ou (mot en minuscules) un mot-outil collé à un mot quelconque d'au moins quatre
                # lettres (« télévisésdont », « croisadeet », « participentà » ; pas « Géville », « Leveinard »)
                if (fa >= 3.0 and fb >= 3.0) or (minuscule and (a in _OUTILS and len(b) >= 4 or b in _OUTILS and len(a) >= 4)
                                                 and min(fa, fb) >= 1.5):
                    res.append(f"{a} {b}")
        return res[:6]

    def flexions(self, forme: str, phone: str, homophones: bool = False) -> list[Candidat]:
        """Formes du même lemme et de la même catégorie qui ne diffèrent que par un trait de ``TRAITS_FLEXION`` ;
        celles qui se prononcent pareil seulement si ``homophones`` (prononciation hors de la tête de graphie)."""
        # pas les pronoms : le sujet dit l'intention du scripteur, c'est l'accord qui s'y plie
        lectures = [l for l in self.lex.lectures(forme.lower()) if l.upos in ("NOUN", "ADJ", "VERB", "AUX", "DET")]
        if any("'" in l.ortho for l in lectures):
            return []
        vus: dict[str, Candidat] = {}
        for l in lectures:
            t0 = _traits(l.feats)
            for autre in self.lex.formes_de(f"{l.lemme}#{l.upos}"):
                if autre.ortho == l.ortho or (autre.phone == l.phone and not homophones) or autre.ortho in vus:
                    continue
                t1 = _traits(autre.feats)
                diff = {k for k in set(t0) | set(t1) if t0.get(k) != t1.get(k)}
                if (len(diff) == 1 and diff <= set(TRAITS_FLEXION) and autre.ortho.replace("-", "").isalpha()
                        and autre.ortho[:1].isalpha() and autre.ortho[-1:].isalpha()
                        and self.lex.validite(autre.ortho) == "proposable"):
                    vus[autre.ortho] = Candidat(autre.ortho, "flexion", 1, self.lex.frequence(autre.ortho),
                                                phone=autre.phone)
        return list(vus.values())

    def quasi_homophones(self, forme: str, phone: str) -> list[Candidat]:
        """Formes du même lemme qui ne diffèrent que par le timbre d'une voyelle moyenne (e/ɛ, o/ɔ, ø/œ), confondues
        par beaucoup de locuteurs : a était → a été, j'ai mangeait → j'ai mangé."""
        lemmes = {l.lemme for l in self.lex.lectures(forme.lower())}
        son = "".join(c for c in phone if c not in " .‿")
        vus = []
        for h in self.lex.homophones(phone.strip(), neutre=True, avec_lectures=True):
            if (h.propre or h.validite != "proposable" or h.ortho == forme.lower() or not h.ortho.isalpha()
                    or not lemmes & {l.lemme for l in h.lectures}):
                continue
            autre = "".join(c for c in (h.lectures[0].phone if h.lectures else "") if c not in " .‿")
            if autre and autre != son:
                vus.append(Candidat(h.ortho, "quasi", 1, h.zipf, phone=h.lectures[0].phone))
        return vus
