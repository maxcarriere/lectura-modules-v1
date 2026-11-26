# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Sortie de la chaîne : l'alignement linéaire d'une phrase, et ce qu'on en dérive.

Chaque mot porte la suite de ses couples (phonème, graphème) et sa jonction avec le mot
suivant. L'orthographe, la phonétique syllabée, la phonétique à séparateurs et la ligne
des jonctions sont des lectures de cette seule structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .analyse import Analyse, Couple
from .index_phone import forme_liee
from .structures import Mot, TypeMot
from .tokeniseur import LIAISON, VOYELLES, phonemes

H_ASPIRE = "*h*"
SYLLABE = Couple(".", ".")
# Nature de la jonction d'un mot avec le suivant.
ESPACE, ELISION, LIAISON_, ENCHAINEMENT, CLITIQUE, COLLE = "espace", "elision", "liaison", "enchainement", "clitique", "colle"

_SEMI_VOYELLES = frozenset("jwɥ")
_OBSTRUANTES = frozenset("pbtdkɡfv")
_LIQUIDES = frozenset("lʁ")


@dataclass
class MotAligne:
    mot: Mot
    couples: tuple[Couple, ...] = ()
    phone_enrichi: str = ""
    analyse: Analyse | None = None
    origine: str = ""                 # lexique, modele, formule, ponctuation, inconnu
    jonction: str = ESPACE            # avec le mot suivant
    regle: str = ""                   # règle de liaison consultée (L10…), s'il y en a une
    phone: str = ""                   # prononciation dans la phrase, jonction comprise
    lecture: list[MotAligne] = field(default_factory=list)   # formule : les mots de sa lecture
    # Espace devant le mot dans l'orthographe produite ; ``None`` : celui du texte d'entrée.
    espace: bool | None = None
    schwa_final: bool = False         # schwa final ajouté (option) : il s'élide devant voyelle si l'on enchaîne
    source: str = ""                  # entrée d'un lexique branché (« lexicon ») ; "" : lexique du transducer

    @property
    def espace_avant(self) -> bool:
        return self.mot.espace_avant if self.espace is None else self.espace


@dataclass
class PhraseAlignee:
    mots: list[MotAligne]
    corrections: list = field(default_factory=list)     # mode correcteur : ce qui a été changé dans l'entrée

    def _lus(self) -> list[MotAligne]:
        """Mots prononcés, dans l'ordre : ceux d'une formule sont ceux de sa lecture."""
        return [lu for m in self.mots for lu in (m.lecture or [m])]

    @property
    def phone(self) -> str:
        """Phonétique de la phrase : « . » entre syllabes, « ‿ » quand une syllabe relie deux mots."""
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
                resultat.append(Couple("".join(lu.phone for lu in m.lecture).strip(), m.mot.forme))
            else:
                resultat.extend(m.couples or (Couple("", m.mot.forme),))
        return resultat

    @property
    def ortho(self) -> str:
        return "".join(c.graphe for c in self.couples if c != SYLLABE)

    def lineaire(self, x_entier: bool = False, doubles: bool = False) -> list[tuple[str, str, str]]:
        """Format linéaire à trois lignes, une colonne par lettre (codes de l'ancien Aligneur V2).

        Chaque colonne est (orthographe, phonétique, coupure). Phonétique : le phonème de la lettre, ``_C``
        (suite d'un graphème : « u » de « ou »), ``_M`` (lettre muette) ; orthographe ``_D`` : phonème de plus
        (« x » = /ks/). Séparateurs (espace, apostrophe, tiret) : leur propre colonne, phonétique « ‿ » quand la
        syllabe enjambe la frontière, « . » sinon, espace pour une espace simple. Coupure : ``SYL`` (début de
        syllabe dans le mot), ``ESP``, ``APO``, ``TIR``, ``LIA`` (liaison), ``ENC`` (enchaînement), ``PONCT``,
        ``FML`` (formule, une colonne : sa forme et sa lecture), ``_`` sinon.

        Options de syllabation orthographique : ``x_entier`` — une frontière ne coupe jamais les deux phonèmes d'un
        « x » (« e.xis.ter » /ɛ.ɡzis.te/ et non /ɛɡ.zis.te/) ; ``doubles`` — une consonne double porte son phonème
        sur la seconde lettre, la première est muette, et la frontière passe entre les deux (« bal|lon »,
        « pas|ser », « at|taque »).
        """
        colonnes: list[tuple[str, str, str]] = []
        precedent: MotAligne | None = None
        for m in self.mots:
            jonction = _jonction_finale(precedent) if precedent else ""
            debut_tiret = bool(m.couples) and m.couples[0].graphe.startswith("-") and not m.lecture
            if precedent and m.espace_avant and not debut_tiret and jonction != ELISION:
                lie = jonction in (LIAISON_, ENCHAINEMENT)
                colonnes.append((" ", LIAISON if lie else " ", _COUPURE_JONCTION.get(jonction, "ESP")))
            if m.lecture:
                lu = "".join(x.phone for x in m.lecture).replace(LIAISON, "").strip()
                colonnes.append((m.mot.forme, lu, "FML"))
            elif m.origine == "ponctuation":
                colonnes.extend((c, c, "PONCT") for c in m.mot.forme)
            else:
                mot = _colonnes_du_mot(m, jonction if debut_tiret else "")
                colonnes.extend(_syllabation_orthographique(mot, x_entier, doubles))
            precedent = m
        return colonnes

    def format_lineaire(self, **options) -> str:
        """Les trois lignes, colonnes alignées (espace notée « ␣ ») ; ``options`` : celles de ``lineaire``."""
        colonnes = [tuple("␣" if x == " " else x for x in c) for c in self.lineaire(**options)]
        largeurs = [max(len(x) for x in c) for c in colonnes]
        return "\n".join(" ".join(c[k].ljust(w) for c, w in zip(colonnes, largeurs)).rstrip() for k in range(3))

    @property
    def phone_sep(self) -> str:
        """Phonétique à séparateurs (troisième niveau d'entrée : « e.ta.z-y.ni », « le.z a.mi ») : le vrai
        séparateur orthographique à chaque frontière de mot, « . » entre syllabes."""
        return self.separee()

    def vers_dict(self, **options) -> dict:
        """Forme sérialisable (JSON) de la phrase : ce que renvoient le serveur et le mode API.

        ``options`` : celles de ``lineaire`` (``x_entier``, ``doubles``).

        L'analyseur voit les mots prononcés (une formule y est sa lecture : « quatorze juillet mille… ») ; ici, les
        têtes sont ramenées aux indices de ``mots``, et une formule prend l'analyse du mot de sa lecture qui la
        rattache au reste de la phrase (« juillet », « euros »), sa forme écrite pour lemme."""
        # Indice dans ``mots`` de chaque mot prononcé, et plage de chaque mot dans les mots prononcés.
        indice, plages = [], []
        for i, m in enumerate(self.mots):
            plages.append((len(indice), len(indice) + (len(m.lecture) or 1)))
            indice.extend([i] * (len(m.lecture) or 1))
        mots = []
        for m, (debut, fin) in zip(self.mots, plages):
            a, lemme = m.analyse, None
            if m.lecture:
                # Racine de la formule : le premier mot de sa lecture gouverné hors de la formule.
                internes = [lu.analyse for lu in m.lecture if lu.analyse is not None]
                a = next((x for x in internes if x.tete is None or not debut <= x.tete < fin), a)
                lemme = m.mot.forme
            tete = a.tete if a is None or a.tete is None or a.tete < 0 or a.tete >= len(indice) else indice[a.tete]
            mots.append({
                "forme": m.mot.forme, "debut": m.mot.debut, "fin": m.mot.fin, "origine": m.source or m.origine,
                "phone": ("".join(lu.phone for lu in m.lecture) if m.lecture else m.phone).strip(),
                "jonction": m.jonction,
                "couples": [[c.phone, c.graphe] for c in m.couples],
                "analyse": None if a is None else {
                    "upos": a.upos, "traits": a.feats, "lemme": a.lemme if lemme is None else lemme, "tete": tete,
                    "relation": a.relation, "confiance": round(a.confiance, 4),
                },
                "lecture": [lu.mot.forme for lu in m.lecture],
                "formule": m.mot.type_formule if m.lecture else "",
            })
        return {
            "ortho": self.ortho, "phone": self.phone, "phone_sep": self.separee(**options),
            "lineaire": [list(c) for c in self.lineaire(**options)], "mots": mots,
            "corrections": [vars(c) if hasattr(c, "__dict__") else c for c in self.corrections],
        }

    def separee(self, **options) -> str:
        """``phone_sep`` avec les options de syllabation de ``lineaire``."""
        sortie = ""
        for ortho, phone, coupure in self.lineaire(**options):
            if phone in (CONT_C, CONT_M):
                continue
            if ortho in _SEPARATEURS:
                sortie += ortho
            elif coupure == "FML":
                sortie += phone
            elif coupure == "PONCT":
                sortie += ortho
            else:
                # Pas de point juste après un séparateur : il marque déjà la frontière.
                point = coupure == "SYL" and sortie and sortie[-1] not in _SEPARATEURS
                sortie += ("." if point else "") + phone
        return sortie.strip()


# ── Format linéaire ────────────────────────────────────────────────────────────

CONT_C, CONT_M, CONT_D = "_C", "_M", "_D"
_SEPARATEURS = frozenset("'- ")
_COUPURE_SEPARATEUR = {"'": "APO", "-": "TIR", " ": "ESP"}
_COUPURE_JONCTION = {LIAISON_: "LIA", ENCHAINEMENT: "ENC", ELISION: "APO", CLITIQUE: "TIR"}
# Espace interne d'un composé du lexique dite « ‿ » (« les autres » le.z‿otʁ, « tout à fait ») : liaison après une
# consonne de liaison écrite, enchaînement sinon (« pour autant »).
_LETTRES_LIAISON = frozenset("sxztdnpg")


_LETTRES_CONSONNES = frozenset("bcdfghjklmnpqrstvwxz")


def _syllabation_orthographique(colonnes: list[tuple[str, str, str]], x_entier: bool, doubles: bool) -> list[tuple[str, str, str]]:
    lignes = [list(c) for c in colonnes]
    reel = lambda ligne: ligne[1] not in (CONT_C, CONT_M, LIAISON, ".", " ") and ligne[0] not in _SEPARATEURS
    if x_entier:
        for i in range(len(lignes) - 1):
            if lignes[i][0].lower() == "x" and reel(lignes[i]) and lignes[i + 1][0] == CONT_D and lignes[i + 1][2] == "SYL":
                lignes[i][2], lignes[i + 1][2] = "SYL", "_"      # /ɛɡ.zis/ → /ɛ.ɡzis/ : le x passe entier
    if doubles:
        for i in range(len(lignes) - 1):
            a, b = lignes[i], lignes[i + 1]
            if (a[0].lower() == b[0].lower() and a[0].lower() in _LETTRES_CONSONNES and reel(a) and b[1] == CONT_C):
                b[1], a[1] = a[1], CONT_M
                if a[2] == "SYL":
                    a[2], b[2] = "_", "SYL"
    return [tuple(l) for l in lignes]


def _jonction_finale(m: MotAligne) -> str:
    """Jonction d'un mot avec le suivant ; pour une formule, celle du dernier mot de sa lecture."""
    return m.lecture[-1].jonction if m.lecture else m.jonction


def _phonemes_reels(phone: str) -> list[tuple[str, bool]]:
    """Phonèmes d'une prononciation syllabée, avec « début de syllabe » : « pə.ti.z‿ » → p ə t(✓) i z(✓)."""
    texte = phone.replace(" ", "").replace(LIAISON, ".")
    unites = phonemes(texte.replace(".", "")) or list(texte.replace(".", ""))
    debuts, k = set(), 0
    for i, morceau in enumerate(texte.split(".")):
        u = phonemes(morceau) or list(morceau)
        if u and i > 0:
            debuts.add(k)
        k += len(u)
    return [(u, i in debuts) for i, u in enumerate(unites)]


def _separateur(graphe: str, phone: str, m: MotAligne, jonction_avant: str, en_tete: bool,
                lettre_avant: str = "") -> list[str]:
    """Colonne d'un séparateur du mot : « ‿ » si la syllabe enjambe la frontière, « . » sinon."""
    if phone in (LIAISON, "."):
        pass
    elif not en_tete:
        phone = LIAISON if m.jonction == ELISION and m.phone.endswith(LIAISON) else "."
    else:                                   # tiret en tête de clitique : jonction du mot précédent
        phone = LIAISON if jonction_avant in (LIAISON_, ENCHAINEMENT) else "."
    coupure = _COUPURE_SEPARATEUR[graphe]
    if en_tete and jonction_avant in (LIAISON_, ENCHAINEMENT):
        coupure = _COUPURE_JONCTION[jonction_avant]
    elif graphe == " " and phone == LIAISON and not en_tete:
        coupure = "LIA" if lettre_avant.lower() in _LETTRES_LIAISON else "ENC"
    return [graphe, phone, coupure]


_VOYELLES_ECRITES = set("aeiouyàâäéèêëîïôöùûüœæ")


def _colonnes_du_mot(m: MotAligne, jonction_avant: str) -> list[tuple[str, str, str]]:
    from .index_phone import alternatives

    lignes: list[list[str]] = []          # [ortho, phone, coupure]
    syllabe_marquee = False
    for couple in m.couples:
        if couple == SYLLABE:
            syllabe_marquee = True
            continue
        if couple.graphe in _SEPARATEURS:
            lignes.append(_separateur(couple.graphe, couple.phone, m, jonction_avant, not lignes,
                                      lignes[-1][0] if lignes else ""))
            continue
        base = alternatives(couple.phone)[0] if couple.phone else ""
        unites = phonemes(base) or (list(base) if base else [])
        premiere = True
        for lettre in couple.graphe:
            if lettre in _SEPARATEURS:      # entrée sans alignement fin : « -il » d'un seul couple
                lignes.append(_separateur(lettre, "", m, jonction_avant, not lignes))
            elif not unites:
                lignes.append([lettre, CONT_M, "_"])
            elif premiere:
                lignes.append([lettre, unites[0], "SYL" if syllabe_marquee and lignes else "_"])
                syllabe_marquee = premiere = False
            else:
                lignes.append([lettre, CONT_C, "_"])
        for u in unites[1:]:
            lignes.append([CONT_D, u, "_"])
    reels = [ligne for ligne in lignes if ligne[1] not in (CONT_C, CONT_M, LIAISON, ".") and ligne[0] not in _SEPARATEURS]
    dits = _phonemes_reels(m.phone)
    # Consonne de liaison réalisée : sur la dernière lettre muette (« petits » : le « s »), sinon en plus.
    if m.jonction == LIAISON_ and len(dits) == len(reels) + 1:
        consonne = dits[-1][0]
        muettes = [ligne for ligne in lignes if ligne[1] in (CONT_C, CONT_M)]
        if muettes:
            muettes[-1][1] = consonne
            reels.append(muettes[-1])
        else:
            lignes.append([CONT_D, consonne, "_"])
            reels.append(lignes[-1])
    elif m.jonction == LIAISON_ and len(dits) == len(reels) and reels and reels[-1][1] != dits[-1][0]:
        reels[-1][1] = dits[-1][0]           # « dix » : /s/ devient /z/
    # Prononciation et syllabes dans la phrase (variante dite, resyllabation des liaisons et enchaînements).
    if len(dits) == len(reels):
        for ligne, (u, _debut) in zip(reels, dits):
            ligne[1] = u
        for ligne in lignes:
            if ligne[2] == "SYL":
                ligne[2] = "_"
        for ligne, (_u, debut) in zip(reels, dits):
            if debut:
                ligne[2] = "SYL"
    # Le h muet ouvre la syllabe qui suit (« ca.hier », « de.hors ») : la marque passe de la voyelle au h.
    for i in range(1, len(lignes)):
        if (lignes[i][2] == "SYL" and lignes[i][0].lower() in _VOYELLES_ECRITES
                and lignes[i - 1][0].lower() == "h" and lignes[i - 1][1] == CONT_M):
            lignes[i - 1][2], lignes[i][2] = "SYL", "_"
    return [tuple(ligne) for ligne in lignes]


# ── Marques de la prononciation ────────────────────────────────────────────────


def decomposer(phone_enrichi: str) -> tuple[bool, str, str]:
    """(h aspiré, prononciation canonique syllabée, marque de consonne latente)."""
    h = phone_enrichi.startswith(H_ASPIRE)
    corps = phone_enrichi[len(H_ASPIRE) :] if h else phone_enrichi
    latente = ""
    if corps.endswith("]") and "[" in corps:
        debut = corps.rindex("[")
        corps, latente = corps[:debut], corps[debut:]
    resultat = ""
    i = 0
    while i < len(corps):
        c = corps[i]
        if c == "{":
            fin = corps.index("}", i)
            resultat += corps[i + 1 : fin].split("|")[0]
            i = fin + 1
        elif c in "()":
            i += 1
        else:
            resultat += c
            i += 1
    return h, resultat, latente


def devant_consonne(corps: str, latente: str) -> str:
    """Second remplacement d'une marque à deux contextes : « dis[s>z;s>] » devant consonne → « di »."""
    if ";" not in latente:
        return corps
    avant, _, apres = latente.strip("[]").split(";")[1].partition(">")
    return corps[: len(corps) - len(avant)] + apres if corps.endswith(avant) else corps


def lier(corps: str, latente: str) -> str:
    """Prononciation en liaison, la consonne ouvrant la syllabe suivante : « le.z‿ », « bɔ.n‿ », « di.z‿ »."""
    marque = latente.strip("[]").replace(";", ",").split(",")[0]
    if ">" in marque:
        avant, _, apres = marque.partition(">")
        corps, ajout = corps[: len(corps) - len(avant)], apres
    else:
        ajout = marque
    ph = phonemes(ajout) or [ajout]
    return corps + "".join(ph[:-1]) + "." + ph[-1] + LIAISON


def enchainer(corps: str) -> str | None:
    """Détache la fin consonantique d'un mot pour ouvrir la syllabe suivante : « a.vɛ.k‿ », « ka.tʁ‿ »."""
    ph = phonemes(corps.replace(".", "").replace(LIAISON, ""))
    if not ph or ph[-1][0] in VOYELLES:
        return None
    n = 1
    if len(ph) >= 2 and ph[-1] in _LIQUIDES and ph[-2] in _OBSTRUANTES and not (ph[-2] in "td" and ph[-1] == "l"):
        n = 2
    queue = "".join(ph[-n:])
    tete = corps[: len(corps) - len(queue)] if corps.endswith(queue) else None
    if tete is None:           # une frontière de syllabe sépare déjà ces consonnes : on ne touche à rien
        return None
    if not VOYELLES.intersection(tete):
        return corps + LIAISON     # mot sans autre syllabe : il se lie tel quel
    return tete.rstrip(".") + "." + queue + LIAISON


def commence_par_voyelle(corps: str) -> bool:
    debut = corps.lstrip(".")[:1]
    return debut in VOYELLES or debut in _SEMI_VOYELLES


def est_prononce(m: MotAligne) -> bool:
    return m.mot.type is not TypeMot.PONCTUATION and bool(m.phone_enrichi)
