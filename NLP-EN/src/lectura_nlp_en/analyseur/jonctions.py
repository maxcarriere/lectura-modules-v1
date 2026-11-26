# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Jonctions de la phrase anglaise (spec `NLP_EN/Lexique/spec/09_jonctions.md`) : à la place de ``liaisons.py`` et
``e_caduc.py`` du français.

- J1 *the* devant voyelle → ``ði`` ; J2 *to* devant voyelle → ``tu`` ;
- J3 forme forte d'un auxiliaire, d'une préposition ou de *to* en fin de groupe (*I can.*, *where are you from?*) ;
- J4 *a* / *an* contraires au son suivant : étiquette seulement (``a_V``, ``an_C``) ;
- J5 clitiques : voir ``clitique`` (réalisation de *'s*, *'d*, *'ll*, *'ve*, *n't* après l'hôte) ;
- J6 enchaînement consonne → voyelle : ``‿`` à la place de l'espace, sans resyllabation ;
- J7 *h* des pronoms faibles rétabli en tête de groupe (*Him?* ``hɪm``).

Les règles travaillent sur les couples de chaque mot (forme linéaire) : la phonétique de phrase, l'alignement et la
syllabation restent ainsi d'accord.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from .analyse import Couple
from .phonetique import (
    ACCENTS,
    LIAISON,
    PLEINES,
    SYLLABE,
    assimiler_s,
    commence_par_voyelle,
    dernier_phoneme,
    est_voyelle,
    finit_par_consonne,
    nombre_de_syllabes,
    phonemes,
    sans_marques,
)

ESPACE, ENCHAINEMENT, CLITIQUE, COLLE = "espace", "enchainement", "clitique", "colle"
FICHIER_FORMES_FORTES = Path(__file__).parent / "data" / "formes_fortes.tsv"
_CATEGORIES_FORTES = frozenset({"AUX", "ADP"})
_MARQUES_SYLLABE = frozenset((SYLLABE,) + ACCENTS)


@cache
def formes_fortes() -> dict[str, list[tuple[frozenset[str], str]]]:
    table: dict[str, list[tuple[frozenset[str], str]]] = {}
    for ligne in FICHIER_FORMES_FORTES.read_text(encoding="utf-8").splitlines():
        if not ligne.strip() or ligne.startswith("#"):
            continue
        forme, categories, _faible, forte = (ligne.split("\t") + [""] * 4)[:4]
        table.setdefault(forme, []).append((frozenset(categories.split(",")), forte))
    return table


def forme_forte(forme: str, upos: str, phone: str) -> str | None:
    """Forme forte (accentuée) d'un mot grammatical prononcé ``phone`` (sans accent) ; ``None`` s'il n'en a pas."""
    if any(a in phone for a in ACCENTS):
        return None
    for categories, forte in formes_fortes().get(forme.lower(), ()):
        if "*" in categories or upos in categories:
            return forte
    if nombre_de_syllabes(phone) != 1 or any(a in phone for a in ACCENTS):
        return None
    # Repli : accent et voyelle pleine (was wəz → ˈwʌz).
    ph = phonemes(sans_marques(phone)) or []
    return "ˈ" + "".join(PLEINES.get(p, p) for p in ph)


# ── Couples ────────────────────────────────────────────────────────────────────


def phone_des_couples(couples: tuple[Couple, ...]) -> str:
    return "".join(c.phone for c in couples)


def _marques_par_position(phone: str) -> tuple[list[str], dict[int, str]]:
    """Phonèmes d'une prononciation avec marques, et la marque de syllabe placée avant le phonème k."""
    ph: list[str] = []
    marques: dict[int, str] = {}
    morceau = ""
    for c in phone + "\0":
        if c in _MARQUES_SYLLABE or c == "\0":
            ph.extend(phonemes(morceau) or list(morceau))
            morceau = ""
            if c != "\0":
                marques[len(ph)] = c
        elif c not in (LIAISON, " "):
            morceau += c
    return ph, marques


def recoupler(couples: tuple[Couple, ...], nouveau: str) -> tuple[Couple, ...]:
    """Couples du mot pour une autre prononciation ``nouveau`` (avec marques) : les phonèmes qui changent sont donnés
    au couple qui portait les anciens (``ə=e`` → ``i=e``) ; une consonne ajoutée en tête va à la lettre muette qui
    l'écrit (``=h°`` → ``h=h``) ; les frontières de syllabe et l'accent sont refaits d'après ``nouveau``."""
    base = [c for c in couples if not c.frontiere]
    anciens = [phonemes(c.phone) or ([] if not c.phone else [c.phone]) for c in base]
    w = [p for ps in anciens for p in ps]
    s, marques = _marques_par_position(nouveau)
    p = 0
    while p < min(len(w), len(s)) and w[p] == s[p]:
        p += 1
    q = 0
    while q < min(len(w), len(s)) - p and w[len(w) - 1 - q] == s[len(s) - 1 - q]:
        q += 1
    milieu = s[p : len(s) - q]
    nouveaux: list[list[str]] = []
    k = 0                                     # indice du premier phonème ancien du couple
    donne = not milieu and len(w) - q == p    # rien à placer
    for c, ps in zip(base, anciens):
        garde = [x for j, x in enumerate(ps, k) if j < p or j >= len(w) - q]
        touche = any(p <= j < len(w) - q for j in range(k, k + len(ps)))
        if not donne and (touche or (not ps and k == p and c.graphe.lower() in ("h", "w", "gh"))):
            # le premier couple de la zone changée reçoit les nouveaux phonèmes, à leur place
            avant = [x for j, x in enumerate(ps, k) if j < p]
            apres = [x for j, x in enumerate(ps, k) if j >= len(w) - q]
            nouveaux.append(avant + milieu + apres)
            donne = True
        else:
            nouveaux.append(garde)
        k += len(ps)
    if not donne:                             # insertion sans couple d'accueil : au couple suivant la position p
        k = 0
        for i, ps in enumerate(anciens):
            if k + len(ps) > p or i == len(anciens) - 1:
                nouveaux[i] = nouveaux[i][: p - k] + milieu + nouveaux[i][p - k :]
                break
            k += len(ps)
    if sum(len(x) for x in nouveaux) != len(s):
        return (Couple(nouveau, "".join(c.graphe for c in base)),)
    return inserer_frontieres(tuple(Couple("".join(x), c.graphe) for x, c in zip(nouveaux, base)), marques, nouveaux)


def inserer_frontieres(base: tuple[Couple, ...], marques: dict[int, str], unites: list[list[str]]) -> tuple[Couple, ...]:
    """Remet les couples de frontière (``.=.``, ``ˈ=.``, ``ˌ=.``) : avant le premier couple prononcé de la syllabe
    (après les lettres muettes qui terminent la précédente) ; en tête du mot avant toute lettre muette ; à l'intérieur
    d'un couple de deux phonèmes, la marque est écrite dans son phonème (``ɡˈz=x``)."""
    resultat: list[Couple] = []
    k = 0
    for c, ps in zip(base, unites):
        if not ps:
            if k == 0 and 0 in marques and not resultat:
                resultat.append(Couple(marques[0], "."))
                marques = {j: m for j, m in marques.items() if j}
            resultat.append(c)
            continue
        if k in marques and not (k == 0 and resultat and resultat[0].frontiere):
            resultat.append(Couple(marques[k], "."))
        interne = "".join((marques.get(k + j, "") if j else "") + x for j, x in enumerate(ps))
        resultat.append(Couple(interne, c.graphe))
        k += len(ps)
    return tuple(resultat)


# ── Clitiques (J5) ─────────────────────────────────────────────────────────────


def clitique(forme: str, hote: str) -> tuple[Couple, ...] | None:
    """Couples d'un clitique absent du lexique avec son hôte, réalisé après la prononciation ``hote`` (RE8 pour 's) ;
    le premier couple porte la jonction (``‿`` : syllabe partagée ; ``.`` : syllabe à part)."""
    f = forme.lower().replace("’", "'")
    apostrophe = f.startswith("'")
    corps = f[1:] if apostrophe else f
    ecrit = forme[1:] if apostrophe else forme
    consonne = finit_par_consonne(hote)
    d = dernier_phoneme(hote)
    if f == "'":
        return (Couple("", "'"),)                                   # possessif après -s : muet
    if corps == "s":
        r = assimiler_s(hote)
    elif corps == "d":
        r = "əd" if d in ("t", "d") else "d"
    elif corps == "ll":
        r = "əl" if consonne else "l"
    elif corps == "ve":
        r = "əv" if consonne else "v"
    elif corps == "re":
        r = "ɚ"
    elif corps == "m":
        r = "m"
    elif corps in ("n't", "nt"):
        n = "ən" if consonne else "n"
        tete = (Couple(".", "."),) if consonne else ()
        if corps == "n't":
            return tete + (Couple(n, ecrit[0]), Couple(LIAISON, "'"), Couple("t", ecrit[-1]))
        return tete + (Couple(n, ecrit[0]), Couple(LIAISON + "t", ecrit[-1]))
    else:
        return None
    # 're se lie à l'hôte en une syllabe (you're ju‿ɚ, comme le lexique et le corpus cadre)
    syllabique = est_voyelle((phonemes(r) or [""])[0]) and corps != "re"
    jonction = SYLLABE if syllabique else LIAISON
    if apostrophe:
        return (Couple(jonction, "'"), Couple(r, ecrit))
    return (Couple(jonction + r, ecrit),)


# ── Règles de phrase ───────────────────────────────────────────────────────────


def appliquer(mots: list, enchainements: bool = True, fortes: bool = True) -> None:
    """Applique J1–J7 aux mots prononcés de la phrase (``MotAligne`` dans l'ordre de lecture, ponctuation comprise) et
    calcule ``phone`` (prononciation dans la phrase, avec ce qui la sépare du mot précédent) et ``jonction``."""
    n = len(mots)

    def prononce(m) -> bool:
        return m.origine != "ponctuation" and bool(m.couples) and bool(sans_marques(phone_des_couples(m.couples)))

    def suivant(i: int):
        """Mot prononcé suivant sans pause entre les deux (les clitiques muets sont sautés), ou None."""
        for j in range(i + 1, n):
            if mots[j].origine == "ponctuation":
                return None
            if prononce(mots[j]):
                return mots[j]
        return None

    def debut_de_groupe(i: int) -> bool:
        for j in range(i - 1, -1, -1):
            if mots[j].origine == "ponctuation":
                return True
            if prononce(mots[j]):
                return False
        return True

    for i, m in enumerate(mots):
        m.jonction, m.regle = ESPACE, ""
        if not prononce(m):
            continue
        a = m.analyse
        upos = a.upos if a else ""
        forme = m.mot.forme.lower()
        phone = phone_des_couples(m.couples)
        s = suivant(i)
        # le clitique attaché fait partie du mot : la fin de groupe se juge après lui
        j = i
        while j + 1 < n and getattr(mots[j + 1], "clitique", False):
            j += 1
        fin_de_groupe = suivant(j) is None
        voyelle = s is not None and commence_par_voyelle(phone_des_couples(s.couples))
        devant_not = upos == "AUX" and s is not None and s.mot.forme.lower() == "not" and s.mot.espace_avant
        if fortes and (fin_de_groupe or devant_not) and j == i and not getattr(m, "clitique", False) and (
            upos in _CATEGORIES_FORTES or (forme == "to" and upos == "PART")
            or (upos == "VERB" and any("VERB" in cats for cats, _f in formes_fortes().get(forme, ())))   # be existentiel
        ):
            forte = forme_forte(forme, upos, phone)
            if forte:
                m.couples, m.regle = recoupler(m.couples, forte), "forte"
                phone = phone_des_couples(m.couples)
        if not m.regle and forme == "the" and sans_marques(phone) == "ðə" and voyelle:
            m.couples, m.regle = recoupler(m.couples, "ði"), "the_V"
        elif not m.regle and forme == "to" and sans_marques(phone) == "tə" and voyelle:
            m.couples, m.regle = recoupler(m.couples, "tu"), "to_V"
        elif forme == "a" and upos == "DET" and voyelle:
            m.regle = "a_V"
        elif forme == "an" and upos == "DET" and s is not None and not voyelle:
            m.regle = "an_C"
        if debut_de_groupe(i) and upos in ("PRON", "AUX") and m.couples and _h_muet_initial(m.couples):
            m.couples = _h_rendu(m.couples)
            m.regle = m.regle or "h_initial"
    # Jonctions et prononciation dans la phrase.
    precedent = None
    for i, m in enumerate(mots):
        if m.origine == "ponctuation":
            if precedent is not None and not m.mot.espace_avant:
                precedent.jonction = COLLE
            m.phone = (" " if m.mot.espace_avant else "") + m.mot.forme      # la ponctuation reste dans la phrase
            continue
        if not prononce(m):
            m.phone = ""
            continue
        phone = phone_des_couples(m.couples)
        if precedent is None:
            sep = " " if i and m.mot.espace_avant else ""
        elif mots[i - 1] is not precedent and not m.mot.espace_avant and mots[i - 1].origine == "ponctuation":
            sep = ""                                              # well-known : « ˈwɛl-ˈnoʊn »
        elif getattr(m, "clitique", False) and precedent is mots[i - 1]:
            sep = ""
            precedent.jonction = CLITIQUE
        elif enchainements and mots[i - 1] is precedent and finit_par_consonne(phone_des_couples(precedent.couples)) \
                and commence_par_voyelle(phone):
            sep = LIAISON
            precedent.jonction = ENCHAINEMENT
            if not getattr(precedent, "clitique", False):
                # resyllabation comme le français (« a.vɛ.k‿ɛl ») : la consonne finale ouvre la syllabe suivante,
                # « ə.n‿ˈæp.əl », « ˈɡɛ.t‿ˈʌp » (décision de l'utilisateur, 12/10)
                avant = precedent.phone[: len(precedent.phone) - len(phone_des_couples(precedent.couples))]
                precedent.couples = enchainer(precedent.couples)
                precedent.phone = avant + phone_des_couples(precedent.couples)
        else:
            sep = " "
        if sep == LIAISON and phone[:1] in ACCENTS + (SYLLABE,) and phone[:1] == SYLLABE:
            phone = phone[1:]
        m.phone = sep + phone
        precedent = m


def enchainer(couples: tuple[Couple, ...]) -> tuple[Couple, ...]:
    """Détache la dernière consonne prononcée du mot dans une syllabe à part (frontière ``.=.`` avant son couple, ou
    marque dans le couple : ``k.s=x``) ; mot sans autre voyelle avant elle : inchangé (règle du français)."""
    reels = [k for k, c in enumerate(couples) if not c.frontiere and sans_marques(c.phone)]
    if not reels:
        return couples
    k = reels[-1]
    c = couples[k]
    ph = phonemes(sans_marques(c.phone)) or []
    if not ph or est_voyelle(ph[-1]):
        return couples
    avant = "".join(sans_marques(x.phone) for x in couples[:k])
    if not any(est_voyelle(p) for p in (phonemes(avant) or []) + ph[:-1]):
        return couples
    if len(ph) > 1:                                            # couple à deux phonèmes (ks=x, əl=le) : marque interne
        interne = "".join(ph[:-1]) + SYLLABE + ph[-1]
        return couples[:k] + (Couple(interne, c.graphe),) + couples[k + 1 :]
    if k and couples[k - 1].frontiere:                         # déjà en tête de syllabe
        return couples
    return couples[:k] + (Couple(SYLLABE, "."),) + couples[k:]


def _h_muet_initial(couples: tuple[Couple, ...]) -> bool:
    premiers = [c for c in couples if not c.frontiere]
    return bool(premiers) and premiers[0].phone == "" and premiers[0].graphe.lower() == "h"


def _h_rendu(couples: tuple[Couple, ...]) -> tuple[Couple, ...]:
    resultat, fait = [], False
    for c in couples:
        if not fait and not c.frontiere and c.phone == "" and c.graphe.lower() == "h":
            resultat.append(Couple("h", c.graphe))
            fait = True
        else:
            resultat.append(c)
    return tuple(resultat)
