# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Structure pivot du module : document → phrases → mots → segments.

Vocabulaire (spec 01 du cadre LeXiK) :

- un **segment** est une suite de lettres (ou de phonèmes) sans séparateur ;
- un **mot** est fait d'un ou de plusieurs segments reliés par un tiret ou une
  apostrophe (``grand-père``, ``aujourd'hui``) ; un mot d'un seul segment peut
  porter une apostrophe finale (``j'``) ou un tiret initial (``-tu``).

Tous les décalages (``debut``, ``fin``) visent la chaîne d'origine, jamais une
chaîne normalisée : ``document.texte[mot.debut:mot.fin]`` redonne le texte saisi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Canal(str, Enum):
    ORTHO = "ortho"
    PHONE = "phone"


class TypeMot(str, Enum):
    MOT = "mot"
    PONCTUATION = "ponctuation"
    # Chaîne contenant un chiffre ou un symbole : candidate à la lecture de formules.
    FORMULE = "formule"
    # Chaîne phonétique contenant un caractère hors inventaire.
    INCONNU = "inconnu"


class NiveauPhone(str, Enum):
    """Quantité d'information portée par une entrée phonétique."""

    BRUT = "brut"            # phonèmes et espaces
    SYLLABE = "syllabe"      # + « . » et « ‿ »
    SEPARE = "separe"        # + séparateurs de segment (« ' » et « - »), format phone_sep


@dataclass(frozen=True)
class Segment:
    forme: str                       # lettres ou phonèmes seuls, normalisés
    debut: int
    fin: int
    sep_avant: str = ""              # séparateur qui précède le segment dans le mot : "", "'", "-"
    sep_apres: str = ""              # apostrophe finale du mot (« j' »)
    syllabes: tuple[str, ...] = ()   # canal phonétique, quand les « . » sont fournis
    # Consonne(s) rattachée(s) à la syllabe du segment suivant (« e.ta.z‿y.ni » : syllabes
    # e, ta et jonction z). Elle reste dans ``forme`` ; c'est le lexique qui dit ensuite si
    # elle est latente (liaison, « e.ta[z] ») ou finale du mot (enchaînement, « aʁk »).
    jonction: str = ""


@dataclass
class Mot:
    type: TypeMot
    forme: str                       # forme normalisée, séparateurs compris
    debut: int
    fin: int
    segments: list[Segment] = field(default_factory=list)
    espace_avant: bool = False
    # Canal phonétique : le mot est suivi de « ‿ » (liaison, enchaînement ou élision,
    # séparateur orthographique encore inconnu).
    lie_au_suivant: bool = False
    # Canal phonétique, après recomposition : nature de la jonction avec le mot suivant
    # (« elision », « liaison », « enchainement », « ambigu », « inconnue ») et, pour une
    # liaison, forme du mot en isolation (« pəti » pour « pətit »).
    jonction: str = ""
    forme_isolee: str = ""
    # Formule reconnue : nom du type, valeur, et mots de sa lecture, chacun situé sur la
    # plage du texte d'origine qu'il lit.
    type_formule: str = ""
    valeur: object = None
    lecture: list[Mot] = field(default_factory=list)
    # Mot d'une lecture : numéro de la partie de la formule qu'il lit (jour, mois, année).
    composant: int = 0
    # Mot d'une lecture : « lettre » s'il s'agit d'une lettre épelée (nom de la lettre).
    nature: str = ""
    # Abrègement reconnu par le tokeniseur : « sigle », « acronyme », « abreviation » ou « initiale » (la lecture
    # selon la nature revient au module des formules).
    abregement: str = ""


@dataclass
class Phrase:
    mots: list[Mot]

    @property
    def debut(self) -> int:
        return self.mots[0].debut

    @property
    def fin(self) -> int:
        return self.mots[-1].fin


@dataclass
class Document:
    texte: str
    canal: Canal
    phrases: list[Phrase] = field(default_factory=list)
    niveau_phone: NiveauPhone | None = None

    @property
    def mots(self) -> list[Mot]:
        return [m for p in self.phrases for m in p.mots]

    def texte_de(self, element: Mot | Segment | Phrase) -> str:
        return self.texte[element.debut:element.fin]
