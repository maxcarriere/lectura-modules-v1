# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Recomposition d'une phrase phonétique à l'aide du lexique.

Le tokeniseur phonétique traite « ‿ » comme un blanc : il rend des unités, pas encore
des mots. Cette étape :

1. reconnaît les mots composés et les locutions du lexique, et leur rend leurs
   séparateurs (``o.ʒuʁ.d‿ɥi`` → ``oʒuʁd'ɥi``, ``tutafɛ`` → ``tut a fɛ``) ;
2. marque les élisions (``ʒ‿ɛm`` → ``ʒ'`` + ``ɛm``) et le t euphonique
   (``a.t‿il`` → ``a`` + ``-t-il``) ;
3. dit si la consonne qui précède « ‿ » est latente (liaison) ou finale (enchaînement).

Le tiret des clitiques inversés (``ɛ.t‿il``, « est-il ») n'est pas décidé ici : il dépend
de l'analyse grammaticale. Une chaîne où des mots sont collés sans « ‿ » ni entrée du
lexique reste telle quelle : c'est le rôle du modèle de segmentation.
"""

from __future__ import annotations

from dataclasses import replace

from .decoupage import TABLES_PHONE
from .index_phone import ABREGE, ELIDEE, LIEE, MOT, IndexPhone
from .structures import Document, Mot, NiveauPhone, Phrase, Segment, TypeMot
from .tokeniseur import SYLLABE, VOYELLES, tokeniser_phone

ELISION, LIAISON, ENCHAINEMENT, AMBIGU, INCONNUE = "elision", "liaison", "enchainement", "ambigu", "inconnue"

# Un composé dont toutes les parts sont des mots doit atteindre la fréquence de la plus rare, à cet écart près.
_ECART_COMPOSE = 1.5
# Longueur maximale, en unités, d'un composé cherché dans le lexique.
_MAX_UNITES = 6


def recomposer(document: Document, index: IndexPhone) -> Document:
    phrases = []
    for phrase in document.phrases:
        mots = phrase.mots
        if document.niveau_phone is not NiveauPhone.SEPARE:
            mots = _composes(document, mots, index)
            mots = _clitiques_colles(document, mots, index)
            mots = _elisions_et_euphonie(mots, index)
        phrases.append(Phrase(_jonctions(mots, index, document.niveau_phone)))
    return Document(document.texte, document.canal, phrases, document.niveau_phone)


# ── 1. Composés et locutions ───────────────────────────────────────────────────


def _composes(document: Document, mots: list[Mot], index: IndexPhone) -> list[Mot]:
    resultat: list[Mot] = []
    i = 0
    while i < len(mots):
        for j in range(min(len(mots), i + _MAX_UNITES), i, -1):
            groupe = mots[i:j]
            if not _chaine_liee(groupe):
                continue
            nouveaux = _lire_compose(document, groupe, index)
            if nouveaux:
                resultat.extend(nouveaux)
                i = j
                break
        else:
            resultat.append(mots[i])
            i += 1
    return resultat


def _chaine_liee(groupe: list[Mot]) -> bool:
    return all(m.type is TypeMot.MOT for m in groupe) and all(m.lie_au_suivant for m in groupe[:-1])


def _lire_compose(document: Document, groupe: list[Mot], index: IndexPhone) -> list[Mot] | None:
    cle = "".join(m.forme for m in groupe)
    candidats = index.composes(cle)
    if not candidats:
        return None
    meilleur = max(candidats, key=lambda c: c.zipf)
    # Chaque unité est déjà un mot : le composé ne l'emporte que s'il est attesté en corpus et
    # pas beaucoup plus rare que ses parts (« petits enfants » avant « petits-enfants »).
    lectures = [index.lectures(m.forme) for m in groupe]
    if len(groupe) > 1 and all(MOT in l or LIEE in l for l in lectures):
        parts = min(max(x.zipf for x in l.values()) for l in lectures)
        if meilleur.zipf <= 0 or meilleur.zipf < parts - _ECART_COMPOSE:
            return None
    # Une unité seule qui est déjà un mot plus fréquent que le composé reste un mot.
    if len(groupe) == 1:
        lues = index.lectures(cle)
        seul = lues.get(MOT) or lues.get(ABREGE)       # « ɛtseteʁa » : etc., plutôt que la locution « et cetera »
        if seul and seul.zipf >= meilleur.zipf:
            return None

    positions = [k for m in groupe for k in range(m.debut, m.fin) if document.texte[k] != SYLLABE]
    modele = tokeniser_phone(meilleur.phone_sep, NiveauPhone.SEPARE).mots
    if any(not m.segments for m in modele) or "".join(s.forme for m in modele for s in m.segments) != cle:
        return None
    nouveaux = []
    curseur = 0
    for mot in modele:
        segments = []
        for s in mot.segments:
            debut, fin = positions[curseur], positions[curseur + len(s.forme) - 1] + 1
            segments.append(replace(s, debut=debut, fin=fin))
            curseur += len(s.forme)
        nouveaux.append(replace(mot, debut=segments[0].debut, fin=segments[-1].fin, segments=segments))
    nouveaux[0].espace_avant = groupe[0].espace_avant
    nouveaux[-1].lie_au_suivant = groupe[-1].lie_au_suivant
    return nouveaux


# ── 1 bis. Verbe et clitiques collés ───────────────────────────────────────────


def _clitiques_colles(document: Document, mots: list[Mot], index: IndexPhone) -> list[Mot]:
    """« pu.ve.vu », « dɔ.nə.lə.mwa », « vjɛ̃.til » : une unité inconnue qui se termine par des
    clitiques, derrière un mot connu, est une suite verbe + clitiques à tiret."""
    resultat: list[Mot] = []
    for mot in mots:
        parts = None
        if _simple(mot) and not index.lectures(mot.forme) and not index.composes(mot.forme):
            parts = _detacher_clitiques(mot.forme, index)
        if parts is None:
            resultat.append(mot)
            continue
        positions = [k for k in range(mot.debut, mot.fin) if document.texte[k] != SYLLABE]
        (verbe, isolee), clitiques = parts[0], parts[1:]
        fin = positions[len(verbe) - 1] + 1
        segment = Segment(verbe, mot.debut, fin)
        resultat.append(
            Mot(TypeMot.MOT, verbe, mot.debut, fin, [segment], mot.espace_avant,
                jonction=LIAISON if isolee else "", forme_isolee=isolee)
        )
        curseur = len(verbe)
        for clitique in clitiques:
            segments = []
            for piece in clitique:
                debut, apres = positions[curseur], positions[curseur + len(piece) - 1] + 1
                segments.append(Segment(piece, debut, apres, sep_avant="-"))
                curseur += len(piece)
            forme = "".join("-" + piece for piece in clitique)
            resultat.append(Mot(TypeMot.MOT, forme, segments[0].debut, segments[-1].fin, segments))
        resultat[-1].lie_au_suivant = mot.lie_au_suivant
    return resultat


def _detacher_clitiques(forme: str, index: IndexPhone) -> list | None:
    """[(verbe, forme isolée si liaison), clitique, …] ; un clitique est une suite de pièces (« t », « il »)."""
    t = TABLES_PHONE
    for clitique in sorted(t.clitiques - {t.t_euphonique}, key=len, reverse=True):
        if not forme.endswith(clitique) or len(forme) == len(clitique):
            continue
        reste = forme[: -len(clitique)]
        lectures = index.lectures(reste)
        if MOT in lectures:
            return [(reste, ""), (clitique,)]
        if LIEE in lectures:
            return [(reste, lectures[LIEE].base), (clitique,)]
        if reste.endswith(t.t_euphonique) and clitique in t.sujets and MOT in index.lectures(reste[:-1]):
            return [(reste[:-1], ""), (t.t_euphonique, clitique)]
        avant = _detacher_clitiques(reste, index)
        if avant:
            return avant + [(clitique,)]
    return None


# ── 2. Élisions et t euphonique ────────────────────────────────────────────────


# Écart de fréquence (zipf) sous lequel une forme élidée l'emporte devant voyelle sur la forme pleine.
_ECART_ELISION = 0.5

# Semi-voyelle isolée devant voyelle : la voyelle correspondante prononcée en une syllabe avec la suivante
# (« il y a » = i.l‿j‿a : le « y » /i/ dit /j/), et non une forme élidée (« y' » familier).
_SEMI_VOYELLES = {"j": "i"}


def _voyelle_devant_voyelle(mot: Mot, suivant: Mot, lectures: dict, index: IndexPhone) -> Mot | None:
    voyelle = _SEMI_VOYELLES.get(mot.forme)
    if voyelle is None or len(mot.segments) != 1 or not suivant.forme or suivant.forme[0] not in VOYELLES:
        return None
    pleine = index.lectures(voyelle).get(MOT)
    elidee = lectures.get(ELIDEE)
    if pleine is None or (elidee and elidee.zipf >= pleine.zipf):
        return None
    # Dite en semi-voyelle, elle fait syllabe avec la voyelle suivante : toujours enchaînée.
    return replace(mot, forme=voyelle, segments=[replace(mot.segments[0], forme=voyelle)], jonction=ENCHAINEMENT)


def _elisions_et_euphonie(mots: list[Mot], index: IndexPhone) -> list[Mot]:
    resultat: list[Mot] = []
    i = 0
    while i < len(mots):
        mot = mots[i]
        suivant = mots[i + 1] if i + 1 < len(mots) else None
        if not _simple(mot) or suivant is None or suivant.type is not TypeMot.MOT:
            resultat.append(mot)
            i += 1
            continue
        lectures = index.lectures(mot.forme)
        voyelle = _voyelle_devant_voyelle(mot, suivant, lectures, index)
        if voyelle:
            resultat.append(voyelle)
            i += 1
            continue
        # Devant voyelle, la forme élidée l'emporte si elle est plus fréquente que la pleine (lié au mot suivant),
        # ou presque aussi fréquente, même sans marque de liaison : « jusque à », « lorsque il » ne s'écrivent pas,
        # et le CTC n'indique pas toujours l'élision. Une élidée familière rare (« com' », « sal' ») ne prend pas.
        lue = lectures.get(ELIDEE)
        pleine = lectures.get(MOT)
        devant_voyelle = suivant.forme[0] in VOYELLES
        elidee = not VOYELLES.intersection(mot.forme) or bool(
            lue
            and devant_voyelle
            and (
                (mot.lie_au_suivant and (pleine is None or lue.zipf > pleine.zipf))
                or (pleine is not None and lue.zipf >= pleine.zipf - _ECART_ELISION)
            )
        )
        if elidee:
            resultat.append(_elider(mot))
            i += 1
            continue
        t = TABLES_PHONE
        base = mot.forme[:-1]
        consonne = mot.forme[-1]
        verbe = index.lectures(base).get(MOT)
        # « at » (hâte) existe, mais « a » + t euphonique est bien plus probable devant « il ».
        sans_lecture = LIEE not in lectures and (MOT not in lectures or (verbe and verbe.zipf > lectures[MOT].zipf))
        if mot.lie_au_suivant and sans_lecture and verbe and _simple(suivant):
            if consonne == t.t_euphonique and suivant.forme in t.sujets:
                resultat.extend(_t_euphonique(mot, suivant))
                i += 2
                continue
            if consonne in t.elides_apres_tiret and suivant.forme in t.apres_elide:
                gauche, clitique = _detacher_consonne(mot)
                seg = replace(clitique.segments[0], sep_avant="-", sep_apres="'")
                resultat.append(gauche)
                resultat.append(replace(clitique, forme=f"-{consonne}'", segments=[seg], jonction=ELISION))
                i += 1
                continue
        resultat.append(mot)
        i += 1
    return resultat


def _simple(mot: Mot) -> bool:
    if mot.type is not TypeMot.MOT or len(mot.segments) != 1:
        return False
    return not mot.segments[0].sep_avant and not mot.segments[0].sep_apres


def _elider(mot: Mot) -> Mot:
    seg = replace(mot.segments[0], sep_apres="'", syllabes=(), jonction="")
    return replace(mot, forme=mot.forme + "'", segments=[seg], lie_au_suivant=False, jonction=ELISION)


def _detacher_consonne(mot: Mot) -> tuple[Mot, Mot]:
    """Sépare la dernière consonne d'une unité : « vat » → « va » + « t »."""
    seg = mot.segments[0]
    n = len(seg.jonction) or 1
    coupe = seg.fin - n
    syllabes = seg.syllabes if seg.jonction else ()
    gauche = replace(seg, forme=seg.forme[:-n], fin=coupe, syllabes=syllabes, jonction="")
    droite = Segment(seg.forme[-n:], coupe, seg.fin)
    return (
        replace(mot, forme=gauche.forme, fin=coupe, segments=[gauche], lie_au_suivant=False),
        Mot(TypeMot.MOT, droite.forme, coupe, seg.fin, [droite]),
    )


def _t_euphonique(mot: Mot, sujet: Mot) -> list[Mot]:
    verbe, t = _detacher_consonne(mot)
    segments = [replace(t.segments[0], sep_avant="-"), replace(sujet.segments[0], sep_avant="-")]
    forme = f"-{t.forme}-{sujet.forme}"
    clitique = Mot(TypeMot.MOT, forme, t.debut, sujet.fin, segments, lie_au_suivant=sujet.lie_au_suivant)
    return [verbe, clitique]


# ── 3. Liaison ou enchaînement ─────────────────────────────────────────────────


def _jonctions(mots: list[Mot], index: IndexPhone, niveau: NiveauPhone | None) -> list[Mot]:
    resultat = []
    for i, mot in enumerate(mots):
        suivant = mots[i + 1] if i + 1 < len(mots) else None
        if mot.type is TypeMot.MOT and not mot.jonction and suivant is not None and suivant.type is TypeMot.MOT:
            mot = _jonction(mot, index, niveau)
        resultat.append(mot)
    return resultat


def _jonction(mot: Mot, index: IndexPhone, niveau: NiveauPhone | None) -> Mot:
    dernier = mot.segments[-1]
    lie = mot.lie_au_suivant or bool(dernier.jonction)
    if dernier.sep_apres:
        return replace(mot, jonction=ELISION, lie_au_suivant=False)
    if dernier.forme[-1] in VOYELLES or dernier.forme[-1] == "̃":
        return mot
    # Un mot à plusieurs segments est cherché par son dernier segment (« etaz » de « etaz-yni »).
    lectures = index.lectures(dernier.forme if len(mot.segments) > 1 else mot.forme)
    liee, finale = lectures.get(LIEE), lectures.get(MOT)
    if not lie:
        # Sans marque de liaison, seule une forme qui n'existe qu'en liaison est reconnue.
        if niveau is NiveauPhone.BRUT and liee and not finale and len(mot.segments) == 1:
            return replace(mot, jonction=LIAISON, forme_isolee=liee.base)
        return mot
    if liee and finale:
        # Liaison (« tʁɛ[z] » de très) ou consonne du mot (« tʁɛz », treize) : la suite tranchera.
        return replace(mot, jonction=AMBIGU, forme_isolee=liee.base)
    if liee:
        return replace(mot, jonction=LIAISON, forme_isolee=liee.base)
    if finale or len(mot.segments) > 1:
        return replace(mot, jonction=ENCHAINEMENT, segments=mot.segments[:-1] + [_rattacher(dernier)])
    return replace(mot, jonction=INCONNUE)


def _rattacher(segment: Segment) -> Segment:
    """En enchaînement, la consonne appartient au mot : elle rejoint sa dernière syllabe."""
    if not segment.jonction or not segment.syllabes:
        return segment
    syllabes = segment.syllabes[:-1] + (segment.syllabes[-1] + segment.jonction,)
    return replace(segment, syllabes=syllabes, jonction="")
