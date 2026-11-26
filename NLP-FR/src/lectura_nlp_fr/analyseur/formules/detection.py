# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Repère les formules d'un document orthographique et leur attache valeur et lecture."""

from __future__ import annotations

from ..structures import Canal, Document, Mot, Phrase, Segment, TypeMot
from ..abregements import ABREVIATION, INITIALE
from ..abregements import table as table_abregements
from ..abregements import SIGLE as SIGLE_
from . import MATHS, TYPES, TYPES_CROCHET, TYPES_LETTRES, Formule, analyser
from .autres_types import LETTRE, ROMAIN, SIGLE, Sigle, romain_en_contexte
from .maths import debute_une_expression
from .nombres import Element, MotLu
from .types import CODES_EN_LETTRES, MONNAIE

_MOINS = frozenset("-−")


def detecter_formules(document: Document) -> Document:
    if document.canal is not Canal.ORTHO:
        return document
    return Document(document.texte, document.canal, [Phrase(_dans(document.texte, p.mots)) for p in document.phrases])


def _dans(texte: str, mots: list[Mot]) -> list[Mot]:
    resultat: list[Mot] = []
    k = 0
    while k < len(mots):
        fusion = _formule_a(texte, mots, k)
        if fusion is None:
            resultat.append(mots[k])
            k += 1
        else:
            mot, k, *point = fusion
            resultat.append(mot)
            resultat.extend(point)
    return resultat


# Mots qui annoncent une numérotation en chiffres romains (« chapitre XII », « la IVe République » a son suffixe).
_AVANT_ROMAIN = frozenset("chapitre chapitres tome tomes livre livres acte actes scène scènes article articles titre "
                          "titres volume volumes partie parties section annexe planche siècle siècles millénaire "
                          "dynastie pape roi reine empereur numéro n° no chant chants leçon leçons "
                          "épisode épisodes psaume psaumes".split())
_APRES_ROMAIN = frozenset("siècle siècles millénaire millénaires".split())


def _romain_en_contexte(mots: list[Mot], k: int) -> bool:
    """Nombre romain sans suffixe : après un nom propre (« Louis XIV », « Jean-Paul II ») ou un mot qui annonce une
    numérotation, ou devant « siècle »."""
    avant = mots[k - 1] if k > 0 else None
    apres = mots[k + 1] if k + 1 < len(mots) else None
    if avant is not None and avant.type is TypeMot.MOT:
        if avant.forme.lower() in _AVANT_ROMAIN:
            return True
        if avant.forme[:1].isupper() and not avant.forme.isupper() and k > 1:
            return True                  # nom propre (pas en début de phrase, où toute initiale est capitale)
        if avant.forme[:1].isupper() and not avant.forme.isupper() and k == 1 and len(avant.forme) > 2:
            return True                  # « Louis XIV règne » en tête de phrase
    return apres is not None and apres.forme.lower() in _APRES_ROMAIN


def _romain_annonce(mots: list[Mot], k: int) -> bool:
    """Contexte sûr pour un nombre romain court (« XLV », « LX ») : un mot de numérotation avant (« Chapitre XLV »),
    un nom propre avant hors du début de phrase (« Pie XLV »), ou, en tête de phrase et suivi d'un point ou d'une
    virgule, un titre de chapitre écrit en I, V, X, L (« XXV, où l'on donne… », « XLV. »). Plus étroit que
    ``_romain_en_contexte`` : « Quand CD serait… » reste un sigle."""
    avant = mots[k - 1] if k > 0 else None
    apres = mots[k + 1] if k + 1 < len(mots) else None
    if avant is not None and avant.type is TypeMot.MOT:
        return avant.forme.lower() in _AVANT_ROMAIN or (k > 1 and avant.forme[:1].isupper() and not avant.forme.isupper())
    en_tete = all(m.type is TypeMot.PONCTUATION for m in mots[:k])      # rien, ou « « », « ( » devant
    return (en_tete and apres is not None and apres.forme in (".", ",") and set(mots[k].forme) <= set("IVXL"))


def _formule_a(texte: str, mots: list[Mot], k: int) -> tuple | None:
    mot = mots[k]
    signe = (
        mot.type is TypeMot.PONCTUATION
        and mot.forme in _MOINS
        and (k == 0 or mot.espace_avant)
        and k + 1 < len(mots)
        and mots[k + 1].type is TypeMot.FORMULE
        and not mots[k + 1].espace_avant
    )
    suivant = mots[k + 1] if k + 1 < len(mots) else None
    if mot.type is TypeMot.PONCTUATION and mot.forme in "[]":
        formule = analyser(texte, mot.debut, TYPES_CROCHET)
        if formule is None:
            return None
    elif debute_une_expression(mot, suivant):
        # « x+1 », « f(x)=… », « (a+b)² » : expression qui ne commence pas par un chiffre.
        formule = analyser(texte, mot.debut, (MATHS,))
        if formule is None:
            return None
    elif mot.forme in CODES_EN_LETTRES and suivant is not None and suivant.type is TypeMot.FORMULE:
        # Code de devise devant un nombre (« CHF 20 ») : la monnaie, avant le sigle épelé.
        formule = analyser(texte, mot.debut, (MONNAIE,))
        if formule is None:
            return None
    elif mot.abregement == SIGLE_ and mot.forme in table_abregements():
        return None                      # sigle connu : le lexique le prononce épelé, d'un seul tenant (« ka.ɛl.ɛm »)
    elif mot.abregement == INITIALE or (mot.abregement == SIGLE_ and "." in mot.forme and mot.forme not in table_abregements()):
        # Initiale (« J. », « R. ») : le nom de sa lettre, pas un sens du lexique (« R. » réponse).
        lettres = [(k, c) for k, c in enumerate(mot.forme) if c.isalpha()]
        formule = Formule(SIGLE.nom, Sigle("".join(c for _k, c in lettres)), mot.debut, mot.fin,
                          [MotLu(c, mot.debut + k, mot.debut + k + 1, composant=n, nature=LETTRE)
                           for n, (k, c) in enumerate(lettres)])
    elif mot.abregement == ABREVIATION and mot.forme in table_abregements() and table_abregements()[mot.forme].mot_a_mot:
        # Abréviation de plusieurs mots (« av. J.-C. », « et cetera ») : lue mot à mot par son développement.
        mots_lus = _developpement(mot.forme).split()
        formule = Formule(ABREVIATION, None, mot.debut, mot.fin,
                          [MotLu(m, mot.debut, mot.fin, composant=k) for k, m in enumerate(mots_lus)])
    elif mot.abregement:
        return None                      # acronyme (lu comme un mot), abréviation d'un mot : le lexique les dit
    elif mot.type is TypeMot.MOT and mot.forme[:1].isupper() and len(mot.forme) > 1:
        # Mot en capitales : nombre romain ou sigle, s'il couvre exactement le mot.
        formule = analyser(texte, mot.debut, TYPES_LETTRES)
        if formule is None and _romain_annonce(mots, k) and (force := romain_en_contexte(texte, mot.debut)):
            valeur, fin, lecture = force       # « Chapitre XLV », « XXV, où l'on… » : annoncé, même court
            formule = Formule(ROMAIN.nom, valeur, mot.debut, fin, lecture)
        if formule is None or formule.fin != mot.fin:
            return None
        if formule.type == "romain" and not formule.valeur.ordinal and not _romain_en_contexte(mots, k) \
                and not _romain_annonce(mots, k):
            return None                  # « XXX » (anonymisation de l'oral), « CIV » : pas un nombre hors contexte
    elif mot.type is TypeMot.FORMULE or signe:
        formule = analyser(texte, mot.debut, TYPES + (TYPES_LETTRES[1],))
        if formule is None:
            return None
    else:
        return None
    # La formule doit s'arrêter sur une frontière de mot.
    fin = next((j for j in range(k, len(mots)) if mots[j].fin == formule.fin), None)
    point = []
    if fin is None:
        # « 3500 FF. » : le dernier mot pris pour une abréviation (« FF. » frères) ; son point redevient ponctuation.
        fin = next((j for j in range(k, len(mots)) if mots[j].fin == formule.fin + 1), None)
        if fin is None or formule.type != MONNAIE.nom or texte[formule.fin] != "." or mots[fin].debut >= formule.fin:
            return None
        point = [Mot(TypeMot.PONCTUATION, ".", formule.fin, formule.fin + 1)]
    lecture = [_mot_lu(m) for m in formule.lecture]
    return (
        Mot(
            TypeMot.FORMULE,
            texte[formule.debut : formule.fin],
            formule.debut,
            formule.fin,
            espace_avant=mot.espace_avant,
            type_formule=formule.type,
            valeur=formule.valeur,
            lecture=lecture,
            abregement=mot.abregement or (SIGLE_ if formule.type == SIGLE.nom else ""),
        ),
        fin + 1,
        *point,
    )


def _developpement(forme: str) -> str:
    abrege = table_abregements().get(forme)
    return abrege.developpement if abrege else ""


def _mot_lu(lu: MotLu) -> Mot:
    """Chaque élément devient un segment, situé sur les caractères de la formule qu'il lit."""
    elements = lu.elements or (Element(lu.texte, lu.debut, lu.fin),)
    segments = [Segment(e.texte, e.debut, e.fin, "-" if e.colle else "") for e in elements]
    return Mot(
        TypeMot.MOT, lu.texte, lu.debut, lu.fin, segments, espace_avant=True, composant=lu.composant, nature=lu.nature
    )
