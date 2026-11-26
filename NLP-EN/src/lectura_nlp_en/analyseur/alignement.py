# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Sortie de la chaîne anglaise : l'alignement linéaire d'une phrase, et ce qu'on en dérive (même interface que le
français : ``MotAligne``, ``PhraseAlignee`` avec ``phone``, ``ortho``, ``couples``, ``lineaire``, ``format_lineaire``,
``phone_sep``, ``vers_dict``).

Chaque mot porte sa forme linéaire (couples phonème = graphème, frontières de syllabe ``.=.``, ``ˈ=.``, ``ˌ=.``) et sa
jonction avec le mot suivant (``jonctions.py``). L'orthographe, la phonétique syllabée et accentuée, la phonétique à
séparateurs et le format à trois lignes sont des lectures de cette seule structure.

Syllabation (spec 08 §1, ligne 21) : l'accent ``ˈ`` ``ˌ`` est un séparateur de syllabe, comme le point. Dans le format
à trois lignes, la colonne de coupure dit ``SYL`` (syllabe inaccentuée), ``SYL1`` (accent primaire) ou ``SYL2``
(secondaire) sur la première lettre de la syllabe, en tête de mot comprise quand la syllabe est accentuée. Option
``doubles`` (désactivée par défaut) : coupe des lettres doubles ``hap.p°y`` (la seconde lettre, muette, ouvre la
syllabe suivante) au lieu de ``happ.y``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .analyse import Analyse, Couple
from .jonctions import CLITIQUE, COLLE, ENCHAINEMENT, ESPACE
from .phonetique import ACCENTS, LIAISON, SYLLABE, phonemes, sans_marques
from .structures import Mot, TypeMot

SYLLABE_COUPLE = Couple(".", ".")
CONT_C, CONT_M, CONT_D = "_C", "_M", "_D"
_SEPARATEURS = frozenset("'- ")
_COUPURE_SEPARATEUR = {"'": "APO", "-": "TIR", " ": "ESP"}
_CODE_MARQUE = {SYLLABE: "SYL", "ˈ": "SYL1", "ˌ": "SYL2"}
_MARQUE_CODE = {v: k for k, v in _CODE_MARQUE.items()}
_LETTRES_CONSONNES = frozenset("bcdfghjklmnpqrstvwxz")

__all__ = ["CLITIQUE", "COLLE", "ENCHAINEMENT", "ESPACE", "MotAligne", "PhraseAlignee", "SYLLABE_COUPLE"]


@dataclass
class MotAligne:
    mot: Mot
    couples: tuple[Couple, ...] = ()
    phone_enrichi: str = ""           # prononciation du mot isolé (lexique ou modèle de mot)
    analyse: Analyse | None = None
    origine: str = ""                 # lexique, modele, formule, ponctuation, inconnu, composition
    jonction: str = ESPACE            # avec le mot suivant : espace, enchainement, clitique, colle
    regle: str = ""                   # règle de jonction appliquée (the_V, to_V, forte, a_V, an_C, h_initial)
    phone: str = ""                   # prononciation dans la phrase, précédée de ce qui la joint au mot précédent
    lecture: list[MotAligne] = field(default_factory=list)   # formule, abrègement épelé : les mots de sa lecture
    espace: bool | None = None        # espace devant le mot dans l'orthographe produite ; None : celui du texte
    clitique: bool = False            # le mot se rattache au précédent (do + n't, Bush + 's)

    @property
    def espace_avant(self) -> bool:
        return self.mot.espace_avant if self.espace is None else self.espace


@dataclass
class PhraseAlignee:
    mots: list[MotAligne]
    corrections: list = field(default_factory=list)

    def _lus(self) -> list[MotAligne]:
        """Mots prononcés, dans l'ordre : ceux d'une formule sont ceux de sa lecture."""
        return [lu for m in self.mots for lu in (m.lecture or [m])]

    @property
    def phone(self) -> str:
        """Phonétique de la phrase : « . » « ˈ » « ˌ » entre syllabes, espace ou « ‿ » entre mots."""
        return "".join(m.phone for m in self._lus()).strip()

    @property
    def jonctions(self) -> list[str]:
        return [m.jonction for m in self._lus()]

    @property
    def couples(self) -> list[Couple]:
        """Alignement linéaire de la phrase. Une formule y tient en un couple : sa lecture, sa forme écrite."""
        resultat: list[Couple] = []
        for m in self.mots:
            if m.espace_avant and resultat:
                resultat.append(Couple("", " "))
            if m.lecture:
                resultat.append(Couple(_lu(m), m.mot.forme))
            else:
                resultat.extend(m.couples or (Couple("", m.mot.forme),))
        return resultat

    @property
    def ortho(self) -> str:
        return "".join(c.graphe for c in self.couples if not c.frontiere)

    def lineaire(self, doubles: bool = False, x_entier: bool = False) -> list[tuple[str, str, str]]:
        """Format linéaire à trois lignes, une colonne par lettre (codes de l'ancien Aligneur V2, ``SYL`` complété par
        ``SYL1``, ``SYL2`` pour l'accent). ``x_entier`` est accepté pour l'interface française (sans effet : en
        anglais, le couple ``ɡˈz=x`` coupe déjà le x comme le dit la syllabation)."""
        colonnes: list[tuple[str, str, str]] = []
        precedent: MotAligne | None = None
        for m in self.mots:
            jonction = (precedent.lecture[-1].jonction if precedent.lecture else precedent.jonction) if precedent else ""
            if precedent and m.espace_avant:
                lie = jonction == ENCHAINEMENT
                colonnes.append((" ", LIAISON if lie else " ", "ENC" if lie else "ESP"))
            if m.lecture:
                colonnes.append((m.mot.forme, _lu(m).replace(LIAISON, " "), "FML"))
            elif m.origine == "ponctuation" and m.mot.forme == "-" and not m.espace_avant:
                colonnes.append(("-", SYLLABE, "TIR"))                # trait d'union coupé par le découpage
            elif m.origine == "ponctuation":
                colonnes.extend((c, c, "PONCT") for c in m.mot.forme)
            else:
                mot = colonnes_du_mot(m.couples or (Couple("", m.mot.forme),))
                colonnes.extend(_doubles(mot) if doubles else mot)
            precedent = m
        return colonnes

    def format_lineaire(self, **options) -> str:
        """Les trois lignes, colonnes alignées (espace notée « ␣ »)."""
        colonnes = [tuple("␣" if x == " " else x for x in c) for c in self.lineaire(**options)]
        largeurs = [max(len(x) for x in c) for c in colonnes]
        return "\n".join(" ".join(c[k].ljust(w) for c, w in zip(colonnes, largeurs)).rstrip() for k in range(3))

    @property
    def phone_sep(self) -> str:
        return self.separee()

    def separee(self, **options) -> str:
        """Phonétique à séparateurs : le vrai séparateur orthographique à chaque frontière de mot (``'``, ``-``,
        espace), « . » « ˈ » « ˌ » entre syllabes."""
        sortie, attente = "", ""
        for ortho, phone, coupure in self.lineaire(**options):
            if phone in (CONT_C, CONT_M):
                attente = _MARQUE_CODE.get(coupure, attente)      # lettre muette qui ouvre la syllabe (hap.p°y)
                continue
            if ortho in _SEPARATEURS:
                sortie += ortho
                attente = ""
            elif coupure in ("FML", "PONCT"):
                sortie += phone.strip() if coupure == "FML" else ortho
                attente = ""
            else:
                marque = _MARQUE_CODE.get(coupure, "") or attente
                attente = ""
                if marque == SYLLABE and (not sortie or sortie[-1] in _SEPARATEURS):
                    marque = ""
                sortie += marque + phone
        return sortie.strip()

    def syllabes(self) -> list[list[str]]:
        """Syllabes orthographiques de chaque mot prononcé (graphie syllabée : ``hap|py`` → ``["happ", "y"]``)."""
        resultat = []
        for m in self._lus():
            if m.origine == "ponctuation":
                continue
            morceaux = [""]
            for c in m.couples:
                if c.frontiere:
                    if morceaux[-1]:
                        morceaux.append("")
                else:
                    morceaux[-1] += c.graphe
            resultat.append([x for x in morceaux if x])
        return resultat

    def vers_dict(self, **options) -> dict:
        """Forme sérialisable (JSON) de la phrase ; ``options`` : celles de ``lineaire`` (``doubles``)."""
        mots = []
        for m in self.mots:
            a = m.analyse
            mots.append({
                "forme": m.mot.forme, "debut": m.mot.debut, "fin": m.mot.fin, "origine": m.origine,
                "phone": m.phone.strip(" ‿") if not m.lecture else _lu(m), "phone_mot": m.phone_enrichi,
                "jonction": m.jonction, "regle": m.regle,
                "couples": [[c.phone, c.graphe] for c in m.couples],
                "analyse": None if a is None else {
                    "upos": a.upos, "traits": a.feats, "lemme": a.lemme, "tete": a.tete, "relation": a.relation,
                    "confiance": round(a.confiance, 4),
                },
                "lecture": [lu.mot.forme for lu in m.lecture],
            })
        return {
            "ortho": self.ortho, "phone": self.phone, "phone_sep": self.separee(**options),
            "lineaire": [list(c) for c in self.lineaire(**options)], "mots": mots,
            "corrections": [vars(c) if hasattr(c, "__dict__") else c for c in self.corrections],
        }


def _lu(m: MotAligne) -> str:
    return "".join(x.phone for x in m.lecture).strip()


# ── Format linéaire d'un mot ──────────────────────────────────────────────────


def colonnes_du_mot(couples: tuple[Couple, ...]) -> list[tuple[str, str, str]]:
    """Colonnes (lettre, phonème, coupure) d'un mot d'après sa forme linéaire."""
    lignes: list[list[str]] = []
    marque = ""                                  # code de syllabe en attente pour la prochaine lettre
    for c in couples:
        if c.frontiere:
            marque = _CODE_MARQUE[c.phone]
            continue
        if c.graphe in _SEPARATEURS:
            phone = c.phone.strip()
            if phone in ACCENTS or phone == SYLLABE:
                marque = _CODE_MARQUE[phone]
                phone = SYLLABE
            elif LIAISON in phone:
                phone = LIAISON
            else:
                phone = SYLLABE if lignes else ""
            lignes.append([c.graphe, phone or SYLLABE, _COUPURE_SEPARATEUR[c.graphe]])
            continue
        unites, internes = _unites(c.phone)
        if 0 in internes:
            marque = _CODE_MARQUE[internes.pop(0)]
        for k, lettre in enumerate(c.graphe):
            if not unites:
                lignes.append([lettre, CONT_M, marque or "_"])
            elif k == 0:
                lignes.append([lettre, unites[0], marque or "_"])
            else:
                lignes.append([lettre, CONT_C, "_"])
            marque = ""
        for j, u in enumerate(unites[1:], 1):
            lignes.append([CONT_D, u, _CODE_MARQUE.get(internes.get(j, ""), "_")])
    return [tuple(l) for l in lignes]


def _unites(phone: str) -> tuple[list[str], dict[int, str]]:
    """Phonèmes d'un couple et marques internes (``ɡˈz`` → [ɡ, z], {1: ˈ}) ; ``‿`` et espaces ignorés."""
    unites: list[str] = []
    internes: dict[int, str] = {}
    morceau = ""
    for ch in phone + "\0":
        if ch in ACCENTS or ch == SYLLABE or ch == "\0":
            unites.extend(phonemes(morceau) or ([morceau] if morceau else []))
            morceau = ""
            if ch != "\0":
                internes[len(unites)] = ch                 # 0 : marque en tête du couple (« ˈmɪs.tɚ=Mr. »)
        elif ch not in (LIAISON, " "):
            morceau += ch
    return unites, internes


def _doubles(colonnes: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Option ``hap.p°y`` : une consonne double dont la syllabe suivante commence juste après elle est coupée entre
    ses deux lettres ; la première garde le phonème (coda de la syllabe accentuée), la seconde, muette, ouvre la
    syllabe suivante."""
    lignes = [list(c) for c in colonnes]
    for i in range(len(lignes) - 2):
        a, b, c = lignes[i], lignes[i + 1], lignes[i + 2]
        if (a[0].lower() == b[0].lower() and a[0].lower() in _LETTRES_CONSONNES and b[1] == CONT_C
                and a[1] not in (CONT_C, CONT_M, CONT_D) and c[2] in ("SYL", "SYL1", "SYL2")):
            b[1], b[2], c[2] = CONT_M, c[2], "_"
    return [tuple(l) for l in lignes]


def est_prononce(m: MotAligne) -> bool:
    return m.mot.type is not TypeMot.PONCTUATION and bool(sans_marques("".join(c.phone for c in m.couples)))
