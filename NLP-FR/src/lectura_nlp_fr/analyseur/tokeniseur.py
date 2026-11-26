# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Tokeniseur : texte orthographique ou chaîne phonétique → Document.

Le texte d'origine n'est jamais réécrit. La normalisation (spec 01 §7 : NFC,
apostrophes, tirets) ne touche que la ``forme`` des mots ; les décalages visent
toujours la chaîne reçue.
"""

from __future__ import annotations

import unicodedata

from .abregements import INITIALE, SIGLE, TITRES, TITRES_SANS_POINT, a_points, table
from .decoupage import APO, SEG, TIR, TABLES_ORTHO, TABLES_PHONE, Piece, Tables, decouper_chaine
from .structures import Canal, Document, Mot, NiveauPhone, Phrase, Segment, TypeMot

APOSTROPHES = frozenset("'’ʼ")
TIRETS = frozenset("-‐‑−")
LIAISON = "‿"  # ‿
SYLLABE = "."
TILDE = "̃"

# Caractères de catégorie « ponctuation » qui sont en réalité des symboles de formule.
_SYMBOLES = frozenset("%&@#*/\\§°")
# Ponctuation admise entre deux chiffres d'une même formule.
_INTERNES_NOMBRE = frozenset(".,:/")
_FIN_DE_PHRASE = frozenset(".!?…")
# Mots-outils qui ouvrent une phrase : après « C. », ils signalent une fin de phrase, pas une initiale.
_DEBUTS_DE_PHRASE = frozenset(
    "Il Elle Ils Elles On Je Tu Nous Vous Le La Les L Un Une Des Ce Cet Cette Ces Cela Ça Mais Et Or Donc Puis "
    "Alors Ainsi En Dans Pour Par Sur Avec Si Quand Comme Il Y De Du Au Aux".split()
)
_FERMANTS = frozenset("»”\"')]}")
# Fermants sans ambiguïté, absorbés même après une espace (« Non. »).
_FERMANTS_SURS = frozenset("»”")

PHONEMES = frozenset(
    "a e ɛ i o ɔ u y ø œ ə ɑ̃ ɛ̃ ɔ̃ œ̃ j w ɥ p b t d k ɡ f v s z ʃ ʒ m n ɲ ŋ l ʁ".split()
)
_CARACTERES_PHONE = frozenset("".join(PHONEMES))
VOYELLES = frozenset("aeɛioɔuyøœəɑ")


def tokeniser(texte: str) -> Document:
    """Tokenise un texte orthographique."""
    mots = _mots_ortho(texte)
    return Document(texte, Canal.ORTHO, _phrases(texte, mots))


def tokeniser_phone(chaine: str, niveau: NiveauPhone | None = None) -> Document:
    """Tokenise une chaîne phonétique dont les mots sont séparés par des espaces.

    ``niveau`` est déduit de la chaîne s'il n'est pas donné : présence de « ' » ou
    « - » collés à un phonème (SEPARE), de « . » ou « ‿ » (SYLLABE), sinon BRUT.
    """
    if niveau is None:
        niveau = _niveau_phone(chaine)
    mots = _mots_phone(chaine, niveau)
    return Document(chaine, Canal.PHONE, _phrases(chaine, mots, casse=False), niveau)


# ── Orthographe ────────────────────────────────────────────────────────────────


def _est_lettre(c: str) -> bool:
    return unicodedata.category(c)[0] == "L"


def _est_chiffre(c: str) -> bool:
    return unicodedata.category(c)[0] == "N"


def _normaliser(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _mots_ortho(texte: str) -> list[Mot]:
    mots: list[Mot] = []
    n = len(texte)
    i = 0
    espace = False
    while i < n:
        c = texte[i]
        if c.isspace():
            espace = True
            i += 1
            continue
        abrege = _abregement_a(texte, i)
        if abrege:
            forme, j, nature = abrege
            nouveaux = [Mot(TypeMot.MOT, forme, i, j, [Segment(forme, i, j)], abregement=nature)]
        elif _est_lettre(c) or _est_chiffre(c):
            pieces, a_chiffre, j = _lire_chaine_ortho(texte, i)
            if a_chiffre:
                nouveaux = [Mot(TypeMot.FORMULE, _forme_formule(texte[i:j]), i, j)]
            else:
                nouveaux = [_mot_depuis_pieces(p) for p in decouper_chaine(pieces, TABLES_ORTHO)]
        elif c in TIRETS and _suit_t_euphonique(texte, i):
            pieces, _, j = _lire_chaine_ortho(texte, i)
            nouveaux = [_mot_depuis_pieces(p) for p in decouper_chaine(pieces, TABLES_ORTHO)]
        else:
            j = i + 1
            if c == ".":
                while j < n and texte[j] == ".":
                    j += 1
            est_symbole = c in _SYMBOLES or unicodedata.category(c)[0] == "S"
            type_ = TypeMot.FORMULE if est_symbole else TypeMot.PONCTUATION
            nouveaux = [Mot(type_, _forme_ponctuation(texte[i:j]), i, j)]
        nouveaux[0].espace_avant = espace
        mots.extend(nouveaux)
        espace = False
        i = j
    _abregements_sans_point(mots)
    return mots


# ── Abrègements ────────────────────────────────────────────────────────────────


def _abregement_a(texte: str, i: int) -> tuple[str, int, str] | None:
    """Abrègement écrit avec un point qui commence en ``i`` (« av. J.-C. », « M. », « etc. »), ou initiale
    (« J. » devant un nom ou une autre initiale) : (forme, fin, nature)."""
    if i > 0 and (_est_lettre(texte[i - 1]) or _est_chiffre(texte[i - 1])):
        return None
    # Sigle écrit avec des points (« R.E.M. », « B.C.E. ») : un seul abrègement, épelé.
    fin_sigle = i
    while texte[fin_sigle : fin_sigle + 1].isupper() and texte[fin_sigle + 1 : fin_sigle + 2] == ".":
        fin_sigle += 2
    if fin_sigle - i >= 4 and (fin_sigle == len(texte) or not _est_lettre(texte[fin_sigle])):
        forme = texte[i:fin_sigle]
        connu = table().get(forme)
        return forme, fin_sigle, connu.nature if connu else SIGLE
    initiale = _initiale_a(texte, i)
    if initiale and texte[i : i + 2] != "M.":
        return initiale                  # « R. » devant un nom : une initiale, pas « réponse »
    for forme in a_points().get(texte[i], ()):
        fin = i + len(forme)
        if texte.startswith(forme, i) and (fin == len(texte) or not (_est_lettre(texte[fin]) or _est_chiffre(texte[fin]))):
            une_capitale = len(forme) == 2 and forme[0].isupper() and forme != "M."
            if (table()[forme].ambigu or une_capitale) and not _suite_d_abreviation(texte, fin, forme in TITRES):
                continue                 # « pas. » ou « faire S. » en fin de phrase : le mot (la lettre) et le point final
            return forme, fin, table()[forme].nature
    return initiale


def _suite_d_abreviation(texte: str, fin: int, titre: bool = False) -> bool:
    """Après une abréviation à point qui est aussi un mot (« vol. », « ex. ») : un chiffre ou une minuscule suit
    (« vol. 3 », « par ex. la ») ; devant une majuscule ou en fin de texte, c'est le mot et le point final. Un titre
    (« St. ») admet aussi un nom propre (« St. Louis »)."""
    k = fin
    while k < len(texte) and texte[k] == " ":
        k += 1
    if k >= len(texte):
        return False
    if _est_chiffre(texte[k]) or texte[k].islower():
        return True
    fin_mot = k
    while fin_mot < len(texte) and _est_lettre(texte[fin_mot]):
        fin_mot += 1
    return titre and texte[k].isupper() and texte[k:fin_mot] not in _DEBUTS_DE_PHRASE


def _initiale_a(texte: str, i: int) -> tuple[str, int, str] | None:
    """Une capitale, un point, puis (espace ou tiret) une autre capitale : « J. » de « J. R. R. Tolkien »."""
    if not (texte[i].isupper() and texte[i + 1 : i + 2] == "."):
        return None
    fin_initiale = i + 2
    # Initiale composée : « J.-P. », « J.-C. » (si le lexique ne l'a pas déjà comme abréviation).
    while texte[fin_initiale : fin_initiale + 1] in TIRETS and texte[fin_initiale + 1 : fin_initiale + 2].isupper() \
            and texte[fin_initiale + 2 : fin_initiale + 3] == ".":
        fin_initiale += 3
    if fin_initiale > i + 2:
        return texte[i:fin_initiale], fin_initiale, INITIALE
    k = i + 2
    while k < len(texte) and texte[k] in " -‐":
        k += 1
    if k > i + 2 and k < len(texte) and texte[k].isupper():
        fin = k
        while fin < len(texte) and _est_lettre(texte[fin]):
            fin += 1
        if texte[k:fin] in _DEBUTS_DE_PHRASE:
            return None                  # « la vitamine C. Elle… » : fin de phrase, pas une initiale
        return texte[i : i + 2], i + 2, INITIALE
    return None


def _contexte_d_abreviation(mot: Mot, suivant: Mot | None) -> bool:
    """Une forme qui est aussi un mot n'est un abrègement que suivie d'un nombre (« No 5 »), ou, pour un titre,
    d'un nom propre (« St Louis », « Mme Roy »)."""
    if suivant is None or not suivant.espace_avant:
        return False
    if suivant.forme[:1].isdigit():
        return True
    return mot.forme in TITRES_SANS_POINT and suivant.forme[:1].isupper() and suivant.forme not in _DEBUTS_DE_PHRASE


def _abregements_sans_point(mots: list[Mot]) -> None:
    """Sigles, acronymes et abréviations sans point connus du lexique (« SNCF », « NASA », « Mme »), écrits avec
    leur casse ; pas dans un passage tout en capitales (titre : « LES DES DU HASARD »)."""
    capitales = [m.type is TypeMot.MOT and len(m.forme) > 1 and m.forme.isupper() for m in mots]
    for k, m in enumerate(mots):
        if m.type is not TypeMot.MOT or m.abregement or len(m.forme) < 2 or m.forme.islower():
            continue
        abrege = table().get(m.forme)
        if abrege is None or "." in m.forme:
            continue
        if capitales[k] and ((k > 0 and capitales[k - 1]) or (k + 1 < len(mots) and capitales[k + 1])):
            continue
        if abrege.ambigu == "romain":
            continue                     # « IV », « XV » : au type romain des formules
        if abrege.ambigu == "mot" and not _contexte_d_abreviation(m, mots[k + 1] if k + 1 < len(mots) else None):
            continue                     # « Son », « Bon », « ET » : des mots, sauf contexte sûr
        m.abregement = abrege.nature


def _suit_t_euphonique(texte: str, i: int) -> bool:
    """« -t-il » détaché du verbe par une espace (« a -t-il »)."""
    reste = texte[i + 1 : i + 9].lower()
    if reste[:1] != TABLES_ORTHO.t_euphonique or reste[1:2] not in TIRETS:
        return False
    return any(
        reste.startswith(s, 2) and not _est_lettre(reste[2 + len(s) : 3 + len(s)] or " ")
        for s in TABLES_ORTHO.sujets
    )


def _lire_chaine_ortho(texte: str, i: int) -> tuple[list[Piece], bool, int]:
    """Lit la chaîne maximale de lettres, chiffres et séparateurs internes à partir de ``i``."""
    n = len(texte)
    pieces: list[Piece] = []
    a_chiffre = False
    j = i
    while j < n:
        c = texte[j]
        if _est_lettre(c):
            k = j + 1
            while k < n and (_est_lettre(texte[k]) or unicodedata.category(texte[k])[0] == "M"):
                k += 1
            pieces.append(Piece(SEG, _normaliser(texte[j:k]), j, k))
        elif _est_chiffre(c):
            k = j + 1
            while k < n and _est_chiffre(texte[k]):
                k += 1
            pieces.append(Piece(SEG, texte[j:k], j, k))
            a_chiffre = True
        elif c in APOSTROPHES or c in TIRETS:
            suivant_ok = j + 1 < n and (_est_lettre(texte[j + 1]) or _est_chiffre(texte[j + 1]))
            apres_segment = bool(pieces) and pieces[-1].nature == SEG
            if c in TIRETS and not suivant_ok:
                break
            if c in APOSTROPHES and not apres_segment:
                break
            if pieces and pieces[-1].nature != SEG:
                break
            pieces.append(Piece(APO if c in APOSTROPHES else TIR, "'" if c in APOSTROPHES else "-", j, j + 1))
            k = j + 1
        elif (
            c in _INTERNES_NOMBRE
            and pieces
            and pieces[-1].forme[-1:].isdigit()
            and j + 1 < n
            and _est_chiffre(texte[j + 1])
        ):
            pieces.append(Piece(SEG, c, j, j + 1))
            k = j + 1
        else:
            break
        j = k
    return pieces, a_chiffre, j


def _forme_formule(s: str) -> str:
    s = _normaliser(s)
    return "".join("'" if c in APOSTROPHES else "-" if c in TIRETS else c for c in s)


def _forme_ponctuation(s: str) -> str:
    if s[0] in APOSTROPHES:
        return "'"
    if s[0] in TIRETS:
        return "-"
    return s


def _mot_depuis_pieces(pieces: list[Piece]) -> Mot:
    forme = "".join(p.forme for p in pieces)
    debut, fin = pieces[0].debut, pieces[-1].fin
    if all(p.nature != SEG for p in pieces):
        return Mot(TypeMot.PONCTUATION, forme, debut, fin)
    segments = []
    for k, p in enumerate(pieces):
        if p.nature != SEG:
            continue
        avant = pieces[k - 1].forme if k > 0 else ""
        apres = "'" if k + 2 == len(pieces) and pieces[k + 1].nature == APO else ""
        segments.append(Segment(p.forme, p.debut, p.fin, avant, apres, p.syllabes, p.jonction))
    return Mot(TypeMot.MOT, forme, debut, fin, segments)


# ── Phonétique ─────────────────────────────────────────────────────────────────


def _niveau_phone(chaine: str) -> NiveauPhone:
    n = len(chaine)
    syllabe = False
    for i, c in enumerate(chaine):
        voisin = (i > 0 and chaine[i - 1] in _CARACTERES_PHONE) or (
            i + 1 < n and chaine[i + 1] in _CARACTERES_PHONE
        )
        if (c in APOSTROPHES or c in TIRETS) and voisin:
            return NiveauPhone.SEPARE
        if c == LIAISON or (c == SYLLABE and _point_de_syllabe(chaine, i)):
            syllabe = True
    return NiveauPhone.SYLLABE if syllabe else NiveauPhone.BRUT


def _point_de_syllabe(chaine: str, i: int) -> bool:
    return (
        0 < i < len(chaine) - 1
        and chaine[i] == SYLLABE
        and chaine[i - 1] in _CARACTERES_PHONE
        and chaine[i + 1] in _CARACTERES_PHONE
    )


def phonemes(s: str) -> list[str] | None:
    """Découpe ``s`` en phonèmes de l'inventaire ; ``None`` si un caractère en sort."""
    resultat = []
    i = 0
    while i < len(s):
        p = s[i : i + 2] if s[i + 1 : i + 2] == TILDE else s[i]
        if p not in PHONEMES:
            return None
        resultat.append(p)
        i += len(p)
    return resultat


def _mots_phone(chaine: str, niveau: NiveauPhone) -> list[Mot]:
    separe = niveau is NiveauPhone.SEPARE
    mots: list[Mot] = []
    n = len(chaine)
    i = 0
    espace = False
    while i < n:
        c = chaine[i]
        if c.isspace():
            espace = True
            i += 1
            continue
        if c == LIAISON:
            if mots:
                mots[-1].lie_au_suivant = True
            i += 1
            continue
        pieces, j = _lire_chaine_phone(chaine, i, separe)
        if pieces:
            nouveaux = [_mot_phone(p) for p in decouper_chaine(pieces, TABLES_PHONE)]
        else:
            j = i + 1
            if _est_lettre(c) or unicodedata.category(c)[0] == "M":
                # Lettre hors inventaire : on prend toute la suite pour la signaler en bloc.
                while j < n and not chaine[j].isspace() and chaine[j] != LIAISON:
                    j += 1
                nouveaux = [Mot(TypeMot.INCONNU, chaine[i:j], i, j)]
            else:
                nouveaux = [Mot(TypeMot.PONCTUATION, _forme_ponctuation(c), i, j)]
        nouveaux[0].espace_avant = espace
        mots.extend(nouveaux)
        espace = False
        i = j
    _abregements_sans_point(mots)
    return mots


# ── Abrègements ────────────────────────────────────────────────────────────────


def _abregement_a(texte: str, i: int) -> tuple[str, int, str] | None:
    """Abrègement écrit avec un point qui commence en ``i`` (« av. J.-C. », « M. », « etc. »), ou initiale
    (« J. » devant un nom ou une autre initiale) : (forme, fin, nature)."""
    if i > 0 and (_est_lettre(texte[i - 1]) or _est_chiffre(texte[i - 1])):
        return None
    # Sigle écrit avec des points (« R.E.M. », « B.C.E. ») : un seul abrègement, épelé.
    fin_sigle = i
    while texte[fin_sigle : fin_sigle + 1].isupper() and texte[fin_sigle + 1 : fin_sigle + 2] == ".":
        fin_sigle += 2
    if fin_sigle - i >= 4 and (fin_sigle == len(texte) or not _est_lettre(texte[fin_sigle])):
        forme = texte[i:fin_sigle]
        connu = table().get(forme)
        return forme, fin_sigle, connu.nature if connu else SIGLE
    initiale = _initiale_a(texte, i)
    if initiale and texte[i : i + 2] != "M.":
        return initiale                  # « R. » devant un nom : une initiale, pas « réponse »
    for forme in a_points().get(texte[i], ()):
        fin = i + len(forme)
        if texte.startswith(forme, i) and (fin == len(texte) or not (_est_lettre(texte[fin]) or _est_chiffre(texte[fin]))):
            une_capitale = len(forme) == 2 and forme[0].isupper() and forme != "M."
            if (table()[forme].ambigu or une_capitale) and not _suite_d_abreviation(texte, fin, forme in TITRES):
                continue                 # « pas. » ou « faire S. » en fin de phrase : le mot (la lettre) et le point final
            return forme, fin, table()[forme].nature
    return initiale


def _suite_d_abreviation(texte: str, fin: int, titre: bool = False) -> bool:
    """Après une abréviation à point qui est aussi un mot (« vol. », « ex. ») : un chiffre ou une minuscule suit
    (« vol. 3 », « par ex. la ») ; devant une majuscule ou en fin de texte, c'est le mot et le point final. Un titre
    (« St. ») admet aussi un nom propre (« St. Louis »)."""
    k = fin
    while k < len(texte) and texte[k] == " ":
        k += 1
    if k >= len(texte):
        return False
    if _est_chiffre(texte[k]) or texte[k].islower():
        return True
    fin_mot = k
    while fin_mot < len(texte) and _est_lettre(texte[fin_mot]):
        fin_mot += 1
    return titre and texte[k].isupper() and texte[k:fin_mot] not in _DEBUTS_DE_PHRASE


def _initiale_a(texte: str, i: int) -> tuple[str, int, str] | None:
    """Une capitale, un point, puis (espace ou tiret) une autre capitale : « J. » de « J. R. R. Tolkien »."""
    if not (texte[i].isupper() and texte[i + 1 : i + 2] == "."):
        return None
    fin_initiale = i + 2
    # Initiale composée : « J.-P. », « J.-C. » (si le lexique ne l'a pas déjà comme abréviation).
    while texte[fin_initiale : fin_initiale + 1] in TIRETS and texte[fin_initiale + 1 : fin_initiale + 2].isupper() \
            and texte[fin_initiale + 2 : fin_initiale + 3] == ".":
        fin_initiale += 3
    if fin_initiale > i + 2:
        return texte[i:fin_initiale], fin_initiale, INITIALE
    k = i + 2
    while k < len(texte) and texte[k] in " -‐":
        k += 1
    if k > i + 2 and k < len(texte) and texte[k].isupper():
        fin = k
        while fin < len(texte) and _est_lettre(texte[fin]):
            fin += 1
        if texte[k:fin] in _DEBUTS_DE_PHRASE:
            return None                  # « la vitamine C. Elle… » : fin de phrase, pas une initiale
        return texte[i : i + 2], i + 2, INITIALE
    return None


def _contexte_d_abreviation(mot: Mot, suivant: Mot | None) -> bool:
    """Une forme qui est aussi un mot n'est un abrègement que suivie d'un nombre (« No 5 »), ou, pour un titre,
    d'un nom propre (« St Louis », « Mme Roy »)."""
    if suivant is None or not suivant.espace_avant:
        return False
    if suivant.forme[:1].isdigit():
        return True
    return mot.forme in TITRES_SANS_POINT and suivant.forme[:1].isupper() and suivant.forme not in _DEBUTS_DE_PHRASE


def _abregements_sans_point(mots: list[Mot]) -> None:
    """Sigles, acronymes et abréviations sans point connus du lexique (« SNCF », « NASA », « Mme »), écrits avec
    leur casse ; pas dans un passage tout en capitales (titre : « LES DES DU HASARD »)."""
    capitales = [m.type is TypeMot.MOT and len(m.forme) > 1 and m.forme.isupper() for m in mots]
    for k, m in enumerate(mots):
        if m.type is not TypeMot.MOT or m.abregement or len(m.forme) < 2 or m.forme.islower():
            continue
        abrege = table().get(m.forme)
        if abrege is None or "." in m.forme:
            continue
        if capitales[k] and ((k > 0 and capitales[k - 1]) or (k + 1 < len(mots) and capitales[k + 1])):
            continue
        if abrege.ambigu == "romain":
            continue                     # « IV », « XV » : au type romain des formules
        if abrege.ambigu == "mot" and not _contexte_d_abreviation(m, mots[k + 1] if k + 1 < len(mots) else None):
            continue                     # « Son », « Bon », « ET » : des mots, sauf contexte sûr
        m.abregement = abrege.nature


def _lire_chaine_phone(chaine: str, i: int, separe: bool) -> tuple[list[Piece], int]:
    n = len(chaine)
    pieces: list[Piece] = []
    j = i
    while j < n:
        c = chaine[j]
        if c in _CARACTERES_PHONE and c != TILDE:
            k = j + 1
            while k < n and (chaine[k] in _CARACTERES_PHONE or _point_de_syllabe(chaine, k)):
                k += 1
            # Une lettre hors inventaire collée à la suite invalide tout le bloc.
            if k < n and _est_lettre(chaine[k]):
                return [], i
            brut = chaine[j:k]
            syllabes = tuple(brut.split(SYLLABE)) if SYLLABE in brut else ()
            forme = brut.replace(SYLLABE, "")
            if phonemes(forme) is None:
                return [], i
            jonction = ""
            if len(syllabes) > 1 and not VOYELLES.intersection(syllabes[-1]):
                jonction, syllabes = syllabes[-1], syllabes[:-1]
            pieces.append(Piece(SEG, forme, j, k, syllabes, jonction))
        elif separe and (c in APOSTROPHES or c in TIRETS):
            if pieces and pieces[-1].nature != SEG:
                break
            suivant_ok = j + 1 < n and chaine[j + 1] in _CARACTERES_PHONE
            if c in TIRETS and not suivant_ok:
                break
            if c in APOSTROPHES and not pieces:
                break
            pieces.append(Piece(APO if c in APOSTROPHES else TIR, "'" if c in APOSTROPHES else "-", j, j + 1))
            k = j + 1
        else:
            break
        j = k
    return pieces, j


def _mot_phone(pieces: list[Piece]) -> Mot:
    return _mot_depuis_pieces(pieces)


# ── Phrases ────────────────────────────────────────────────────────────────────


def _phrases(texte: str, mots: list[Mot], casse: bool = True) -> list[Phrase]:
    """``casse`` : une minuscule après un point signale une abréviation, pas une fin de phrase."""
    phrases: list[Phrase] = []
    courant: list[Mot] = []
    k = 0
    while k < len(mots):
        mot = mots[k]
        courant.append(mot)
        k += 1
        if not _termine_phrase(mot, courant):
            if k < len(mots) and "\n\n" in texte[mot.fin : mots[k].debut].replace("\r", ""):
                phrases.append(Phrase(courant))
                courant = []
            continue
        # Ponctuation finale répétée et fermants collés (« ?! », « . » »).
        while k < len(mots) and mots[k].type is TypeMot.PONCTUATION and (
            mots[k].forme[0] in _FIN_DE_PHRASE
            or mots[k].forme in _FERMANTS_SURS
            or (mots[k].forme in _FERMANTS and not mots[k].espace_avant)
        ):
            courant.append(mots[k])
            k += 1
        suivant = mots[k] if k < len(mots) else None
        if mot.abregement and suivant is not None and not suivant.forme[:1].isupper():
            continue                     # « p. 12 », « janv. 2000 » : l'abréviation ne finit la phrase que devant une majuscule
        if suivant is None or (suivant.espace_avant and not (casse and suivant.forme[:1].islower())):
            phrases.append(Phrase(courant))
            courant = []
    if courant:
        phrases.append(Phrase(courant))
    return phrases


def _termine_phrase(mot: Mot, courant: list[Mot]) -> bool:
    if mot.abregement and mot.forme.endswith(".") and mot.abregement != INITIALE and mot.forme not in TITRES:
        return True                      # « etc. », « suiv. » peuvent finir la phrase (la majuscule qui suit en décide)
    if mot.type is not TypeMot.PONCTUATION or mot.forme[0] not in _FIN_DE_PHRASE:
        return False
    # Les initiales (« J. Dupont ») et « M. » sont des abrègements du tokeniseur : leur point n'est pas ici.
    return True
