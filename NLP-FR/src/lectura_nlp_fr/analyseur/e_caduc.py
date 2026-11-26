# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Chute de l'e caduc (schwa) dans la phrase : règle R3 du cadre (spec 02 §6), loi des trois consonnes.

Le lexique écrit le schwa plein (``sa.mə.di``, ``lə``) ; en parole courante il tombe quand il suit une voyelle et
une seule consonne et qu'une seule consonne le suit : « samedi » ``sam.di``, « le petit » ``lə pti``, « je le vois »
``ʒəl vwa``. Il reste quand sa chute ferait trois consonnes (« il te prend », « vendredi »), en tête de groupe
(après une pause) et devant une voyelle. La décision se prend de gauche à droite sur toute la phrase, chaque chute
modifiant le contexte de la suivante.
"""

from __future__ import annotations

from .tokeniseur import LIAISON, VOYELLES, phonemes

SCHWA = "ə"
_MARQUES = " .‿"


def _unites(phone: str) -> list[str]:
    """« pə.ti.z‿ » → ["p", "ə", ".", "t", "i", ".", "z", "‿"] : phonèmes et marques, dans l'ordre."""
    resultat: list[str] = []
    morceau = ""
    for c in phone:
        if c in _MARQUES:
            if morceau:
                resultat.extend(phonemes(morceau) or list(morceau))
                morceau = ""
            resultat.append(c)
        else:
            morceau += c
    if morceau:
        resultat.extend(phonemes(morceau) or list(morceau))
    return resultat


def _voyelle(u: str) -> bool:
    return bool(u) and u[0] in VOYELLES


def chutes(groupes: list[list[str]]) -> list[list[int]]:
    """Pour chaque groupe (suite de prononciations de mots sans pause), les positions des schwas qui tombent,
    par mot : rang du schwa parmi ceux du mot."""
    resultat: list[list[int]] = []
    for phones in groupes:
        suite: list[tuple[str, int, int]] = []          # (phonème, mot, rang du schwa dans le mot ou -1)
        for i, phone in enumerate(phones):
            rang = 0
            for u in _unites(phone):
                if u in _MARQUES:
                    continue
                suite.append((u, i, rang if u == SCHWA else -1))
                rang += u == SCHWA
        par_mot: list[list[int]] = [[] for _ in phones]
        gardes: list[str] = []
        for k, (u, mot, rang) in enumerate(suite):
            if u == SCHWA and len(gardes) >= 2 and not _voyelle(gardes[-1]) and _voyelle(gardes[-2]):
                apres = 0
                for v, _m, _r in suite[k + 1 :]:
                    if _voyelle(v):
                        break
                    apres += 1
                fin = all(not _voyelle(v) for v, _m, _r in suite[k + 1 :])
                if apres == 1 and not fin:
                    par_mot[mot].append(rang)
                    continue
            gardes.append(u)
        resultat.append(par_mot)
    return [x for groupe in resultat for x in groupe]


def sans_schwas(phone: str, rangs: list[int]) -> str:
    """Retire de la prononciation d'un mot les schwas de ces rangs et resyllabe : une syllabe restée sans voyelle
    rejoint la précédente (``sa.m.di`` → ``sam.di``) ou, en tête de mot, la suivante (``p.ti`` → ``pti``)."""
    if not rangs:
        return phone
    avant = phone[: len(phone) - len(phone.lstrip(" "))]
    corps = phone.strip(" ")
    apres = LIAISON if corps.endswith(LIAISON) else ""
    corps = corps.removesuffix(LIAISON)
    syllabes: list[list[str]] = [[]]
    videes: set[int] = set()             # syllabes qui ont perdu leur schwa
    rang = 0
    for u in _unites(corps):
        if u == ".":
            syllabes.append([])
            continue
        if u == SCHWA:
            rang += 1
            if rang - 1 in rangs:
                videes.add(len(syllabes) - 1)
                continue
        syllabes[-1].append(u)
    # Une syllabe vidée rejoint la précédente, ou la suivante en tête de mot ; les autres syllabes sans voyelle
    # (consonne de liaison « pə.ti.z‿ ») restent telles quelles.
    fusion: list[list[str]] = []
    rattacher_suivante = False
    for k, s in enumerate(syllabes):
        if not s:
            continue
        if k in videes and not any(_voyelle(u) for u in s):
            if fusion:
                fusion[-1].extend(s)
            else:
                fusion.append(list(s))
                rattacher_suivante = True
            continue
        if rattacher_suivante:
            fusion[-1].extend(s)
            rattacher_suivante = False
        else:
            fusion.append(list(s))
    return avant + ".".join("".join(s) for s in fusion) + apres


# ── Sens phonétique → orthographe : rendre les schwas tombés ───────────────────

# Écart de fréquence (zipf) pour préférer la forme avec schwa à une forme lue telle quelle (« pti » : p'tit).
_ECART_RESTAURATION = 1.5


def restaurer(chaine: str, index) -> str:
    """Remet le schwa tombé là où il rend un mot nettement plus fréquent : ``pti`` → ``pəti`` (petit),
    ``sam.di`` → ``samə.di``, et une consonne seule devant consonne → ``də``, ``ʒə``, ``mə``… Sans cela, une
    entrée en parole courante tombe sur des graphies familières (« p'tit », « j'suis ») ou sur rien."""
    from .tokeniseur import tokeniser_phone
    from .structures import TypeMot

    mots = [m for p in tokeniser_phone(chaine).phrases for m in p.mots]
    insertions: list[int] = []
    for i, mot in enumerate(mots):
        if mot.type is not TypeMot.MOT or len(mot.segments) != 1:
            continue
        unites = phonemes(mot.segments[0].forme)
        if not unites:
            continue
        suivant = mots[i + 1] if i + 1 < len(mots) and mots[i + 1].type is TypeMot.MOT else None
        debut_suivant = (phonemes(suivant.segments[0].forme) or [""])[0] if suivant and suivant.segments else ""
        if chaine[mot.fin : mot.fin + 1] == LIAISON and len(unites) == 1 and (_voyelle(debut_suivant) or debut_suivant in "jwɥ"):
            continue                     # « l‿wɛst » : élision, pas un schwa tombé (« d‿l‿ɛ̃ » : si)
        rang = _rang_du_schwa(unites, debut_suivant, index)
        if rang is not None:
            insertions.append(_position(chaine, mot.debut, mot.fin, rang))
    for position in sorted(insertions, reverse=True):
        chaine = chaine[:position] + SCHWA + chaine[position:]
    return chaine


def _zipf(index, cle: str) -> float | None:
    lectures = index.lectures(cle)
    return max((l.zipf for l in lectures.values()), default=None)


def _rang_du_schwa(unites: list[str], debut_suivant: str, index) -> int | None:
    """Rang (en phonèmes) où insérer le schwa, ou ``None``."""
    if len(unites) == 1 and not _voyelle(unites[0]):
        # Consonne seule devant consonne : clitique dont le schwa est tombé (« d la », « ʒ sɥi »).
        if debut_suivant and not _voyelle(debut_suivant) and index.lectures(unites[0] + SCHWA).get("mot"):
            return 1
        return None
    actuel = _zipf(index, "".join(unites))
    meilleur, rang = None, None
    # Entre deux consonnes du mot, ou en fin de mot entre sa consonne finale et la consonne du mot suivant.
    fin = len(unites) if debut_suivant and not _voyelle(debut_suivant) else len(unites) - 1
    for k in range(1, fin + 1):
        if _voyelle(unites[k - 1]) or (k < len(unites) and _voyelle(unites[k])):
            continue
        cle = "".join(unites[:k]) + SCHWA + "".join(unites[k:])
        lecture = index.lectures(cle).get("mot")
        # Un composé (« au-delà » o.də.la) compte aussi.
        zipfs = ([lecture.zipf] if lecture else []) + [c.zipf for c in index.composes(cle)]
        if zipfs and (meilleur is None or max(zipfs) > meilleur):
            meilleur, rang = max(zipfs), k
    if meilleur is not None and (actuel is None or meilleur >= actuel + _ECART_RESTAURATION):
        return rang
    return None


def _position(chaine: str, debut: int, fin: int, rang: int) -> int:
    """Position dans la chaîne juste après le phonème qui précède le schwa (avant un éventuel point de syllabe)."""
    position, vus = debut, 0
    for u in _unites(chaine[debut:fin]):
        position += len(u)
        if u not in _MARQUES:
            vus += 1
            if vus == rang:
                return position
    return position


# ── Schwa final (diction soignée, lecture syllabée) ────────────────────────────

# Attaques de deux consonnes admises en français (obstruante + liquide) ; une consonne seule est toujours une attaque.
_ATTAQUES = frozenset(a + b for a in "pbtdkɡfv" for b in "lʁ") - {"tl", "dl", "vl"}


def avec_schwa_final(phone: str) -> str:
    """« ta.bl » → « ta.blə », « paʁl » → « paʁ.lə » : schwa ajouté après la consonne finale, et la plus longue
    attaque admise passe dans la nouvelle syllabe (attaque maximale)."""
    avant = phone[: len(phone) - len(phone.lstrip(" "))]
    corps = phone.strip(" ")
    apres = LIAISON if corps.endswith(LIAISON) else ""
    corps = corps.removesuffix(LIAISON)
    debut, _, derniere = corps.rpartition(".")
    unites = phonemes(derniere) or list(derniere)
    if not unites or _voyelle(unites[-1]):
        return phone
    queue = 1
    if len(unites) >= 3 and not _voyelle(unites[-2]) and unites[-2] + unites[-1] in _ATTAQUES:
        queue = 2
    if not any(_voyelle(u) for u in unites):
        if not debut:
            return phone                 # mot sans voyelle (« pt ») : rien à porter
        syllabes = [debut, derniere + SCHWA]          # « ta.bl » : la dernière syllabe n'est qu'une attaque
    elif not any(_voyelle(u) for u in unites[:-queue]):
        return phone
    else:
        syllabes = ([debut] if debut else []) + ["".join(unites[:-queue]), "".join(unites[-queue:]) + SCHWA]
    return avant + ".".join(syllabes) + apres
