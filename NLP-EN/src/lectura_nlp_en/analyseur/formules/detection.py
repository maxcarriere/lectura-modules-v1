# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Repère les formules d'un document orthographique et leur attache valeur et lecture.

Contextes propres à l'anglais :
- rang dynastique : « Henry VIII », « Pope John Paul II » → the eighth, the second ; numérotation : « World War II »
  → two ;
- numéros dits par paires après Route, Interstate, Flight, Room, Boeing… et numéros de rue (« 1600 Pennsylvania
  Avenue » sixteen hundred, « 123 Main Street » one twenty three) ;
- plage de jours avant une date écrite jour d'abord : « from 10 to 13 January » → from the tenth to the thirteenth
  of January ;
- unité d'une lettre (m, g, s, V, W, L…) séparée du nombre : seulement si rien après ne la fait lire autrement.
"""

from __future__ import annotations

import re

from ..structures import Canal, Document, Mot, Phrase, Segment, TypeMot
from ..abregements import ABREVIATION, INITIALE
from ..abregements import table as table_abregements
from ..abregements import SIGLE as SIGLE_
from . import MATHS, TYPES, TYPES_CROCHET, TYPES_LETTRES, Formule, analyser
from .autres_types import INTERVALLE, LETTRE, SIGLE, TELEPHONE, UNITES_COURTES, Sigle
from .maths import debute_une_expression
from .types import DATE_MOIS, _MOIS_ECRITS, Nombre
from .nombres import UNITES, Element, MotLu, lire_paires, ordinal_mot

_MOINS = frozenset("-−")
_PREFIXE = re.compile(r"(mid|pre|post|early|late|non|anti|pro|over|under)-(?=\d)", re.IGNORECASE)


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
            mot, k = fusion
            resultat.append(mot)
    return _plages_de_jours(resultat)


# Mots qui annoncent une numérotation en chiffres romains (« World War II », « Chapter XII », « Super Bowl XL »).
_AVANT_ROMAIN = frozenset("war chapter chapters volume volumes book part parts act scene section article title phase "
                          "type class stage level vatican bowl episode no number appendix plate annex grade tier "
                          "division league schedule rule".split())
_APRES_ROMAIN = frozenset()
# Mots après lesquels un numéro se dit par paires (« Route 66 », « Interstate 405 » four oh five, « Boeing 747 »).
_AVANT_PAIRES = frozenset("route highway interstate i flight room suite apartment apt gate platform track bus channel "
                          "boeing airbus model exit pier hangar".split())
# Types de voies : « 1600 Pennsylvania Avenue », « 123 Main St. ».
_ETATS_US = frozenset("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM "
                      "NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())
_NOMS_ETATS_US = frozenset("Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii "
                           "Idaho Illinois Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts Michigan "
                           "Minnesota Mississippi Missouri Montana Nebraska Nevada Ohio Oklahoma Oregon Pennsylvania "
                           "Tennessee Texas Utah Vermont Virginia Washington Wisconsin Wyoming Carolina Dakota Hampshire "
                           "Jersey Mexico York Island".split())
_VOIES = frozenset("street st st. avenue ave ave. road rd rd. boulevard blvd blvd. drive dr dr. lane ln way place pl "
                   "court ct parkway pkwy highway square terrace circle trail".split())


def _romain_en_contexte(mots: list[Mot], k: int) -> bool:
    """Nombre romain sans suffixe : après un nom propre (« Louis XIV », « John Paul II ») ou un mot qui annonce une
    numérotation."""
    avant = mots[k - 1] if k > 0 else None
    apres = mots[k + 1] if k + 1 < len(mots) else None
    if avant is not None and avant.type is TypeMot.MOT:
        if avant.forme.lower() in _AVANT_ROMAIN:
            return True
        if avant.forme[:1].isupper() and not avant.forme.isupper() and k > 1:
            return True                  # nom propre (pas en début de phrase, où toute initiale est capitale)
        if avant.forme[:1].isupper() and not avant.forme.isupper() and k == 1 and len(avant.forme) > 2:
            return True
    return apres is not None and apres.forme.lower() in _APRES_ROMAIN


def _dit_par_paires(mots: list[Mot], k: int, fin: int) -> bool:
    """Le nombre ``mots[k]`` est-il un numéro dit par paires (route, vol, chambre, numéro de rue) ?"""
    if k > 0 and mots[k - 1].forme.lower() in _AVANT_PAIRES:
        return True
    j = fin + 1
    noms = 0
    while j < len(mots) and noms < 4 and mots[j].type is TypeMot.MOT and mots[j].forme[:1].isupper():
        if mots[j].forme.lower() in _VOIES and noms:
            return True
        noms += 1
        j += 1
    return False


def _unite_courte_douteuse(mots: list[Mot], fin: int, formule: Formule) -> bool:
    """« 5 m long » oui ; « 74 W 10th Street », « grade 5 A », « 3 s and » : une lettre isolée après un nombre n'est
    une unité que si le mot suivant ne la fait pas lire autrement."""
    v = formule.valeur
    if formule.type != "mesure" or getattr(v, "unite", "") not in UNITES_COURTES:
        return False
    unite = mots[fin]
    if not unite.espace_avant:
        return False                     # « 5m », « 3g » : collé, c'est l'unité
    suivant = mots[fin + 1] if fin + 1 < len(mots) else None
    if suivant is None:
        return False
    return suivant.type is TypeMot.FORMULE or (suivant.type is TypeMot.MOT and suivant.forme[:1].isupper()) \
        or suivant.forme in ("'", "’", "&")


def _formule_a(texte: str, mots: list[Mot], k: int) -> tuple[Mot, int] | None:
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
    # « Chapter IV », « Part III » : nombre romain annoncé, même s'il est aussi un sigle (IV intraveineux)
    romain_annonce = k > 0 and mots[k - 1].forme.lower() in _AVANT_ROMAIN and bool(re.fullmatch("[IVXLCDM]+", mot.forme))
    if mot.type is TypeMot.PONCTUATION and mot.forme in "[]":
        formule = analyser(texte, mot.debut, TYPES_CROCHET)
        if formule is None:
            return None
    elif mot.forme == "(":
        # « (555) 123-4567 », « (0, 1] », « (a+b)² »
        formule = analyser(texte, mot.debut, (TELEPHONE, INTERVALLE, MATHS))
        if formule is None:
            return None
    elif mot.type is not TypeMot.FORMULE and debute_une_expression(mot, suivant):
        # « x+1 », « f(x)=… », « sin(x) » : expression qui ne commence pas par un chiffre.
        formule = analyser(texte, mot.debut, (MATHS,))
        if formule is None:
            return None
    elif mot.abregement == SIGLE_ and mot.forme in table_abregements() and not romain_annonce:
        return None                      # sigle connu : le lexique le prononce
    elif mot.abregement == INITIALE or (mot.abregement == SIGLE_ and "." in mot.forme and mot.forme not in table_abregements()):
        lettres = [(j, c) for j, c in enumerate(mot.forme) if c.isalpha()]
        formule = Formule(SIGLE.nom, Sigle("".join(c for _j, c in lettres)), mot.debut, mot.fin,
                          [MotLu(c, mot.debut + j, mot.debut + j + 1, composant=n, nature=LETTRE)
                           for n, (j, c) in enumerate(lettres)])
    elif mot.abregement == ABREVIATION and mot.forme in table_abregements() and table_abregements()[mot.forme].mot_a_mot:
        mots_lus = _developpement(mot.forme).split()
        formule = Formule(ABREVIATION, None, mot.debut, mot.fin,
                          [MotLu(m, mot.debut, mot.fin, composant=j) for j, m in enumerate(mots_lus)])
    elif mot.abregement and not romain_annonce:
        return None                      # acronyme (lu comme un mot), abréviation d'un mot : le lexique les dit
    elif mot.type is TypeMot.MOT and mot.forme.rstrip(".") in _MOIS_ECRITS and k + 1 < len(mots) \
            and mots[k + 1].type is TypeMot.FORMULE and (formule := analyser(texte, mot.debut, (DATE_MOIS,))) is not None:
        pass                             # « April 8, 2020 » : date à l'américaine, mois en tête
    elif (mot.type is TypeMot.MOT or mot.abregement) and mot.forme[:1].isupper() and len(mot.forme) > 1:
        # Mot en capitales : nombre romain ou sigle, s'il couvre exactement le mot.
        formule = analyser(texte, mot.debut, TYPES_LETTRES)
        if formule is None or formule.fin != mot.fin:
            return None
        if formule.type == "romain" and not formule.valeur.ordinal and not _romain_en_contexte(mots, k):
            return None                  # « XXX », « CIV », « MIX » : pas un nombre hors contexte
        if formule.type == "romain" and k > 0 and mots[k - 1].forme.lower() not in _AVANT_ROMAIN:
            # rang dynastique : « Henry VIII » → the eighth
            from .nombres import ecrire_entier, ordinal
            mots_lus = ["the"] + ordinal(ecrire_entier(formule.valeur.valeur))
            formule = Formule(formule.type, formule.valeur, formule.debut, formule.fin,
                              [MotLu(x, mot.debut, mot.fin) for x in mots_lus])
    elif mot.type is TypeMot.FORMULE and (prefixe := _PREFIXE.match(mot.forme)):
        # « mid-1980s », « pre-1900 », « late-19th » : le préfixe, puis la formule
        formule = analyser(texte, mot.debut + prefixe.end(), TYPES)
        if formule is None or formule.fin != mot.fin:
            return None
        formule = Formule(formule.type, formule.valeur, mot.debut, formule.fin,
                          [MotLu(prefixe.group(1).lower(), mot.debut, mot.debut + prefixe.end())] + formule.lecture)
    elif mot.type is TypeMot.FORMULE or signe:
        formule = analyser(texte, mot.debut, TYPES + (TYPES_LETTRES[1],))
        if formule is None:
            return None
    else:
        return None
    # La formule doit s'arrêter sur une frontière de mot.
    fin = next((j for j in range(k, len(mots)) if mots[j].fin == formule.fin), None)
    if fin is None:
        return None
    if _unite_courte_douteuse(mots, fin, formule):
        formule = analyser(texte, mot.debut, tuple(t for t in TYPES if t.nom != "mesure"))
        if formule is None:
            return None
        fin = next((j for j in range(k, len(mots)) if mots[j].fin == formule.fin), None)
        if fin is None:
            return None
    lecture_lue = formule.lecture
    v = formule.valeur
    if (formule.type == "nombre" and not v.decimales and not v.negatif) or \
            (formule.type == "date" and not v.mois and not v.decennie and not v.courte):
        chiffres = texte[formule.debut : formule.fin]
        if chiffres.isdigit() and len(chiffres) == 5 and k > 0 and (mots[k - 1].forme in _ETATS_US
                                                                     or mots[k - 1].forme in _NOMS_ETATS_US):
            # code postal après l'État (« NY 11222 ») : chiffre à chiffre
            lecture_lue = [MotLu(UNITES[int(c)], formule.debut + q, formule.debut + q + 1) for q, c in enumerate(chiffres)]
        elif chiffres.isdigit() and 3 <= len(chiffres) <= 5 and _dit_par_paires(mots, k, fin):
            lecture_lue = lire_paires(chiffres, list(range(formule.debut, formule.fin)))
    lecture = [_mot_lu(m) for m in lecture_lue]
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
            abregement=(mot.abregement if formule.type != "romain" else "") or (SIGLE_ if formule.type == SIGLE.nom else ""),
        ),
        fin + 1,
    )


# ── Plage de jours : « from 10 to 13 January » ─────────────────────────────────

_LIENS_DE_PLAGE = frozenset("to and until till through thru -".split()) | {"–"}
_JOUR_D_ABORD = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s")


def _plages_de_jours(mots: list[Mot]) -> list[Mot]:
    """« from 10 to 13 January 2020 » → from the tenth to the thirteenth of January twenty twenty."""
    for k in range(len(mots) - 2):
        a, lien, date = mots[k], mots[k + 1], mots[k + 2]
        if not (a.type is TypeMot.FORMULE and a.type_formule in ("nombre", "ordinal") and a.lecture
                and lien.forme.lower() in _LIENS_DE_PLAGE and date.type is TypeMot.FORMULE
                and date.type_formule == "date" and getattr(date.valeur, "mois", 0) and date.lecture
                and _JOUR_D_ABORD.match(date.forme)):
            continue
        rang = int(re.sub(r"\D", "", a.forme) or 0)
        if not 1 <= rang < date.valeur.jour:
            continue
        lecture_a = [_mot_lu(MotLu("the", a.debut, a.fin)), _mot_lu(MotLu(_ordinal(rang), a.debut, a.fin))]
        if date.lecture[0].forme == "the":     # date jour d'abord : déjà « the thirteenth of January »
            mots[k] = _avec_lecture(a, lecture_a)
            continue
        mois = [m for m in date.lecture if m.composant == 1]
        jour = [m for m in date.lecture if m.composant == 0]
        reste = [m for m in date.lecture if m.composant not in (0, 1)]
        if not mois or not jour:
            continue
        lecture_date = ([_mot_lu(MotLu("the", jour[0].debut, jour[0].fin))] + jour
                        + [_mot_lu(MotLu("of", mois[0].debut, mois[0].fin, composant=1))] + mois + reste)
        mots[k] = _avec_lecture(a, lecture_a)
        mots[k + 2] = _avec_lecture(date, lecture_date)
    return mots


def _ordinal(n: int) -> str:
    from .nombres import ecrire_entier, ordinal
    return " ".join(ordinal(ecrire_entier(n)))


def _avec_lecture(mot: Mot, lecture: list[Mot]) -> Mot:
    # « twenty first » : un mot de lecture par élément
    eclatee = []
    for m in lecture:
        parties = m.forme.split()
        if len(parties) == 1:
            eclatee.append(m)
        else:
            eclatee += [_mot_lu(MotLu(p, m.debut, m.fin, composant=m.composant)) for p in parties]
    return Mot(mot.type, mot.forme, mot.debut, mot.fin, espace_avant=mot.espace_avant, type_formule=mot.type_formule,
               valeur=mot.valeur, lecture=eclatee, abregement=mot.abregement)


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
