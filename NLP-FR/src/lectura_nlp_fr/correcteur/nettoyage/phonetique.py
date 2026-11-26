# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Tolérance phonétique : les erreurs du décodeur CTC qu'un lexique peut rattraper.

Symétrique du nettoyage orthographique (``nettoyage.py``) pour l'entrée phonétique. Un mot que le
lexique ne connaît sous aucune de ses lectures est confronté à des candidats proches : e caduc en
plus ou en moins, substitution d'un phonème que le CTC confond souvent (timbre des voyelles,
nasales, sonorité des consonnes), phonème doublé ou voyelle redoublée, mot coupé en deux mots
connus, mot fusionné avec son voisin inconnu. Le candidat est retenu s'il est fréquent et
clairement meilleur que les autres ; sinon le mot reste tel quel et le modèle de mot l'écrira.

Couche optionnelle : ``Chaine.ecrire(chaine, tolerance=True)``. Elle travaille sur la chaîne
phonétique avant toute analyse, et rend la chaîne corrigée avec la liste des corrections.
"""

from __future__ import annotations

from dataclasses import dataclass

from lectura_nlp_fr.analyseur.decoupage import TABLES_PHONE
from lectura_nlp_fr.analyseur.formules.phone import mot_de
from lectura_nlp_fr.analyseur.index_phone import IndexPhone, cle_de, neutraliser
from lectura_nlp_fr.analyseur.recomposition import recomposer
from lectura_nlp_fr.analyseur.structures import Mot, TypeMot
from lectura_nlp_fr.analyseur.tokeniseur import LIAISON, VOYELLES, phonemes, tokeniser_phone
from .nettoyage import Correction

SCHWA = "ə"
# Confusions fréquentes du CTC actuel (comptées sur ses erreurs, ancien module STT), hors timbre des
# voyelles moyennes que l'index neutralise déjà (e/ɛ, o/ɔ, ø/œ).
CONFUSIONS = [
    ("ø", "ə"), ("o", "ə"), ("ɔ", "ə"), ("ø", "o"), ("ɔ̃", "ɑ̃"), ("ɑ̃", "ɛ̃"), ("e", "i"), ("o", "u"), ("a", "ɛ"),
    ("a", "ɑ̃"), ("ɛ", "ɛ̃"), ("ɔ", "ɔ̃"),       # nasalité
    ("d", "t"), ("s", "z"), ("l", "n"),
]
_CONFUSIONS: dict[str, set[str]] = {}
for _a, _b in CONFUSIONS:
    _CONFUSIONS.setdefault(_a, set()).add(_b)
    _CONFUSIONS.setdefault(_b, set()).add(_a)
# Bonus par nature de candidat, en points de fréquence (zipf).
_BONUS = {"schwa": 1.0, "confusion": 0.5, "double": 0.5, "coupe": 0.0, "elision": 1.0, "fusion": 0.5}
# Fréquence minimale du candidat selon le nombre de phonèmes du mot fautif ; écart minimal avec le second.
_SEUIL = {1: 9.0, 2: 6.0, 3: 4.5}
_SEUIL_LONG = 3.0
_SEUIL_COUPE = 4.5
_ECART = 0.3
# Un mot connu mais rare est suspect ; un candidat doit alors le dépasser nettement.
_ZIPF_SUSPECT = 3.0
_GAIN = 2.0


@dataclass(frozen=True)
class Candidat:
    cle: str            # suite de phonèmes sans marque ; une espace sépare deux mots
    motif: str
    score: float


class Tolerant:
    def __init__(self, index: IndexPhone, segmentation: bool = False):
        self.index = index
        # Coupure d'un mot inconnu en deux mots connus et élision non marquée : désactivées par défaut,
        # mesurées sans gain (les inconnus de la parole sont surtout des noms propres ; « ʒam » → j'âme).
        # Elles attendent la recherche globale, qui saura qu'un clitique élidé ne précède pas un nom.
        self.segmentation = segmentation

    # ── Lexique ────────────────────────────────────────────────────────────────

    def frequence(self, cle: str) -> float | None:
        """Fréquence (zipf) la plus haute des lectures d'une suite de phonèmes, voyelles moyennes
        confondues ; ``None`` si le lexique ne la connaît pas."""
        zipfs = [l.zipf for p in self.index.prononciations(cle, neutre=True) for l in self.index.lectures(cle_de(p)).values()]
        return max(zipfs) if zipfs else None

    def frequence_mot(self, mot: Mot) -> float | None:
        """Fréquence du mot sous sa meilleure lecture (forme pleine, forme isolée, ou sans sa consonne
        finale quand une jonction suit : liaison possible même si la recomposition n'a pas tranché)."""
        cle = "".join(s.forme for s in mot.segments)
        cles = [cle]
        if mot.forme_isolee:
            cles.append(mot.forme_isolee)
        if mot.lie_au_suivant and len(cle) > 1 and cle[-1] not in VOYELLES:
            cles.append(cle[:-1])
        zipfs = [f for f in map(self.frequence, cles) if f is not None]
        return max(zipfs) if zipfs else None

    def suspect(self, mot: Mot) -> bool:
        f = self.frequence_mot(mot)
        return f is None or f < _ZIPF_SUSPECT

    # ── Candidats ──────────────────────────────────────────────────────────────

    def candidats(self, cle: str, inconnu: bool = True) -> list[Candidat]:
        """Candidats pour un mot suspect. Un mot connu mais rare n'est rapproché que par un e caduc ou un
        phonème doublé : une confusion le ferait glisser vers un homonyme plus courant (passé simple →
        imparfait par a/ɛ, nom propre vers un nom commun)."""
        unites = phonemes(cle)
        if not unites:
            return []
        bruts: dict[str, Candidat] = {}

        def proposer(variante: list[str] | str, motif: str, bonus: float = 0.0) -> None:
            texte = "".join(variante) if isinstance(variante, list) else variante
            if texte == cle or texte in bruts or not texte.strip():
                return
            frequences = [self.frequence(p) for p in texte.replace(LIAISON, " ").split()]
            if any(f is None for f in frequences) or (motif == "coupe" and min(frequences) < _SEUIL_COUPE):
                return
            bruts[texte] = Candidat(texte, motif, min(frequences) + _BONUS[motif] + bonus)

        n = len(unites)
        if unites == [SCHWA]:
            return [Candidat("", "hesitation", 9.0)]     # « euh » ou e caduc détaché : rien à écrire
        for i, u in enumerate(unites):
            if u == SCHWA:
                proposer(unites[:i] + unites[i + 1 :], "schwa")
            for autre in _CONFUSIONS.get(u, ()) if inconnu else ():
                proposer(unites[:i] + [autre] + unites[i + 1 :], "confusion")
            if i + 1 < n and unites[i + 1] == u:
                proposer(unites[:i] + unites[i + 1 :], "double")
            elif i + 1 < n and u in VOYELLES and unites[i + 1] in VOYELLES:
                proposer(unites[:i] + unites[i + 1 :], "double", -0.5)
                proposer(unites[: i + 1] + unites[i + 2 :], "double", -0.5)
        for i in range(n + 1):
            if (i == 0 or unites[i - 1] not in VOYELLES) and (i == n or unites[i] not in VOYELLES):
                proposer(unites[:i] + [SCHWA] + unites[i:], "schwa", -0.5)
        for i in range(1, n) if self.segmentation else ():
            gauche, droite = "".join(unites[:i]), "".join(unites[i:])
            if gauche in TABLES_PHONE.elidees and droite[0] in VOYELLES:
                proposer(gauche + LIAISON + droite, "elision")        # « dœ̃ » → d‿œ̃ : élision que le CTC n'a pas marquée
            elif inconnu and i >= 2 and n - i >= 2:
                proposer(gauche + " " + droite, "coupe")
        # Deux variantes qui ne diffèrent que par le timbre d'une voyelle moyenne sont la même entrée.
        uniques: dict[str, Candidat] = {}
        for c in sorted(bruts.values(), key=lambda c: -c.score):
            uniques.setdefault(neutraliser(c.cle), c)
        return list(uniques.values())

    def corriger_mot(self, cle: str, recue: float | None = None) -> Candidat | None:
        """Meilleur candidat pour un mot suspect de fréquence ``recue`` (``None`` : inconnu)."""
        candidats = self.candidats(cle, inconnu=recue is None)
        if not candidats:
            return None
        meilleur = candidats[0]
        n = len(phonemes(cle) or cle)
        if meilleur.score < _SEUIL.get(n, _SEUIL_LONG) or (recue is not None and meilleur.score < recue + _GAIN):
            return None
        if len(candidats) > 1 and meilleur.score - candidats[1].score < _ECART - 1e-9:
            return None
        return meilleur

    # ── Chaîne ─────────────────────────────────────────────────────────────────

    def nettoyer(self, chaine: str) -> tuple[str, list[Correction]]:
        """Chaîne phonétique du module (mots séparés par des espaces, « . » et « ‿ » facultatifs) →
        chaîne corrigée et corrections faites. Les mots sont ceux de la recomposition, comme dans la chaîne : un
        composé ou une locution qu'elle a réunis (« s‿ɛ.t‿a.diʁ », « ɑ̃ fas ») et un nombre dit en lettres
        (« di.sɛt ») ne sont jamais suspects. Le reste de la chaîne (espaces, ponctuation) est gardé tel quel."""
        jetons = tokeniser_phone(chaine)
        origines = {(m.debut, m.fin) for p in jetons.phrases for m in p.mots}
        mots = [m for p in recomposer(jetons, self.index).phrases for m in p.mots]
        corrections: list[Correction] = []
        remplacements: list[tuple[int, int, str]] = []
        i = 0
        while i < len(mots):
            mot = mots[i]
            if mot.type is TypeMot.MOT and self._a_examiner(mot, origines) and self.suspect(mot):
                cle = "".join(s.forme for s in mot.segments)
                suivant = mots[i + 1] if i + 1 < len(mots) else None
                fusion = self._fusion(mot, suivant, chaine) if suivant is not None and self._a_examiner(suivant, origines) else None
                if fusion:
                    corrections.append(Correction(mot.debut, suivant.fin, chaine[mot.debut : suivant.fin], fusion, "fusion", 0.0))
                    remplacements.append((mot.debut, suivant.fin, fusion))
                    i += 2
                    continue
                choix = self.corriger_mot(cle, self.frequence_mot(mot))
                if choix:
                    corrections.append(Correction(mot.debut, mot.fin, chaine[mot.debut : mot.fin], choix.cle, choix.motif, choix.score))
                    remplacements.append((mot.debut, mot.fin, choix.cle))
            i += 1
        resultat = chaine
        for debut, fin, texte in reversed(remplacements):
            if not texte:
                # Hésitation supprimée : avec l'espace qui la précède, ou la liaison qui la suit.
                if debut > 0 and resultat[debut - 1] in " " + LIAISON:
                    debut -= 1
                elif resultat[fin : fin + 1] in (" ", LIAISON):
                    fin += 1
            resultat = resultat[:debut] + texte + resultat[fin:]
        return resultat, corrections

    @staticmethod
    def _a_examiner(mot: Mot, origines: set[tuple[int, int]]) -> bool:
        """Ni réunion de la recomposition (composé, locution), ni nombre dit en lettres."""
        return (mot.debut, mot.fin) in origines and "\u2205" in mot_de(mot)

    def _fusion(self, mot: Mot, suivant: Mot | None, chaine: str) -> str | None:
        """Deux mots inconnus côte à côte qui, réunis, en font un connu : « mo.bi.li » + « ze » → mobilize."""
        if suivant is None or suivant.type is not TypeMot.MOT or mot.lie_au_suivant or not self.suspect(suivant):
            return None
        cle = "".join(s.forme for s in mot.segments) + "".join(s.forme for s in suivant.segments)
        f = self.frequence(cle)
        recues = [x for x in (self.frequence_mot(mot), self.frequence_mot(suivant)) if x is not None]
        minimum = max([_SEUIL.get(len(phonemes(cle) or cle), _SEUIL_LONG)] + [r + _GAIN for r in recues])
        if f is None or f + _BONUS["fusion"] < minimum:
            return None
        return cle
