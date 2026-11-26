# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""La chaîne anglaise complète, dans les deux sens (même rôle que la chaîne française) :

- **lecture** : texte → découpage (tokeniseur EWT, abrègements, formules lues) → analyse du modèle de phrase (étalon +
  tête de sélection) → prononciation de chaque mot (lexique d'après forme, UPOS, lemme et traits ; repli modèle de mot
  GPA) → contractions (forme entière du lexique, sinon hôte + clitique, RE8) → jonctions de phrase (``jonctions.py``)
  → alignement linéaire, syllabation et accent (``alignement.py``) ;
- **écriture** : phonétique (mots séparés par des espaces, « . » « ˈ » « ˌ » « ‿ » facultatifs, accent toléré) →
  mots (``tokeniser_phone``, ``recomposition``) → analyse du modèle de phrase en canal phonétique, graphie choisie
  parmi les homophones par la tête de sélection → repli GPA (P2G) → orthographe alignée.
"""

from __future__ import annotations

from dataclasses import replace

from .alignement import MotAligne, PhraseAlignee
from .analyse import Analyse, Analyseur, Couple, Entree, Jeton, Lexique, ModeleDeMot, choisir
from .abregements import table as table_abregements
from .formules.detection import detecter_formules
from .jonctions import appliquer, clitique, phone_des_couples
from .phonetique import LIAISON, SIFFLANTES, SYLLABE, commence_par_voyelle, dernier_phoneme, sans_marques
from .recomposition import CLITIQUE, ENCHAINEMENT, cle, recomposer
from .structures import Mot, TypeMot
from .tokeniseur import FORMES_CLITIQUES, decomposer, tokeniser, tokeniser_phone

_ZIPF_RARE = 3.0          # homophone rare d'une forme forte (frum pour ˈfɹʌm) : écarté au profit du mot grammatical
_CLITIQUE_ECRIT = {"s": "'s", "z": "'s", "ɪz": "'s", "d": "'d", "əd": "'d", "l": "'ll", "əl": "'ll", "m": "'m",
                   "v": "'ve", "əv": "'ve", "ɚ": "'re", "t": "n't", "nt": "n't", "ənt": "n't"}


class Chaine:
    def __init__(self, analyseur: Analyseur, lexique: Lexique, modele: ModeleDeMot | None = None,
                 enchainements: bool = True, formes_fortes: bool = True, **_options):
        self.analyseur = analyseur
        self.lexique = lexique
        self.modele = modele
        # Jonctions (spec 09) : enchaînement consonne → voyelle noté « ‿ » ; forme forte en fin de groupe.
        self.enchainements = enchainements
        self.formes_fortes = formes_fortes

    # ── Lecture : texte → phonétique ──────────────────────────────────────────

    def lire(self, texte: str, **_options) -> list[PhraseAlignee]:
        return self.lire_textes([texte])[0]

    def lire_textes(self, textes: list[str]) -> list[list[PhraseAlignee]]:
        """Plusieurs textes à la fois : les phrases sont analysées par paquets (plus rapide qu'un texte à la fois)."""
        preps = [[self._preparer(p.mots) for p in detecter_formules(tokeniser(t)).phrases] for t in textes]
        a_plat = [pr for prs in preps for pr in prs]
        analyses = self._analyser_lot([pr[0] for pr in a_plat], "ortho")
        resultats, k = [], 0
        for prs in preps:
            resultats.append([self._terminer(pr, analyses[k + i]) for i, pr in enumerate(prs)])
            k += len(prs)
        return resultats

    def _analyser_lot(self, phrases: list[list[Jeton]], canal: str) -> list[list[list[Analyse]]]:
        if hasattr(self.analyseur, "analyser_lot"):
            return self.analyseur.analyser_lot(phrases, canal)
        f = self.analyseur.analyser if canal == "ortho" else self.analyseur.analyser_phone
        return [f(j) if j else [] for j in phrases]

    def _phrase(self, mots: list[Mot]) -> PhraseAlignee:
        prep = self._preparer(mots)
        return self._terminer(prep, self._analyser_lot([prep[0]], "ortho")[0])

    def _preparer(self, mots: list[Mot]) -> tuple:
        """Jetons de surface de la phrase pour l'analyseur, et ce qu'il faut pour relier ses analyses aux mots dits."""
        lus_par_mot: list[list[Mot]] = []         # mots prononcés de chaque mot du découpage
        jetons: list[Jeton] = []
        rangs: list[list[int]] = []               # pour chaque mot prononcé : (jeton, rang du mot dans le jeton)
        groupes: list[list[int]] = []             # contractions : indices des mots prononcés (hôte, clitiques)
        lus: list[Mot] = []
        for k, m in enumerate(mots):
            if m.type is TypeMot.PONCTUATION:
                lus_m, jeton = [m], Jeton(m.forme, "p")
            elif m.abregement and not self.lexique.lectures(m.forme):
                lecture = self._lecture_abregement(m)
                lus_m, jeton = lecture, Jeton(m.forme, f"a:{m.abregement}", lecture=tuple(x.forme for x in lecture))
            elif m.abregement:
                lus_m, jeton = [m], Jeton(m.forme, f"a:{m.abregement}")
            elif m.type is TypeMot.FORMULE and m.lecture:
                lus_m, jeton = list(m.lecture), None
            elif m.type is TypeMot.FORMULE:
                lus_m, jeton = [m], Jeton(m.forme, "s")
            else:
                lus_m, jeton = [m], Jeton(m.forme, "m")
            lus_par_mot.append(lus_m)
            if jeton is None:                     # formule lue : un jeton par mot de la lecture
                for lu in lus_m:
                    jetons.append(Jeton(lu.forme, f"f:{m.type_formule}"))
                    rangs.append([len(jetons) - 1, 0])
                    lus.append(lu)
                continue
            if k and _est_clitique(mots[k - 1], m) and jetons and jetons[-1].type == "m":
                # contraction : le clitique rejoint le jeton de son hôte (do + n't → « don't »)
                hote = jetons[-1]
                hote.mots = (hote.mots or (hote.forme,)) + (m.forme,)
                hote.forme += m.forme
                rangs.append([len(jetons) - 1, len(hote.mots) - 1])
                lus.append(m)
                if groupes and groupes[-1][-1] == len(lus) - 2:
                    groupes[-1].append(len(lus) - 1)
                else:
                    groupes.append([len(lus) - 2, len(lus) - 1])
                continue
            jetons.append(jeton)
            for lu in lus_m:
                rangs.append([len(jetons) - 1, 0])
                lus.append(lu)
        return jetons, rangs, groupes, lus, lus_par_mot, mots

    def _terminer(self, prep: tuple, analyses_jetons: list[list[Analyse]]) -> PhraseAlignee:
        jetons, rangs, groupes, lus, lus_par_mot, mots = prep
        analyses = []
        for j, r in rangs:
            a = analyses_jetons[j]
            analyses.append(a[min(r, len(a) - 1)] if a else None)
        alignes = [self._mot(lu, a) for lu, a in zip(lus, analyses)]
        for g in groupes:
            self._contraction([alignes[i] for i in g])
        appliquer(alignes, self.enchainements, self.formes_fortes)
        resultat, k = [], 0
        for m, lus_m in zip(mots, lus_par_mot):
            n = len(lus_m)
            if lus_m != [m]:
                origine = "formule" if m.type is TypeMot.FORMULE and not m.abregement else "abregement"
                resultat.append(MotAligne(m, origine=origine, analyse=alignes[k].analyse, lecture=alignes[k : k + n],
                                          jonction=alignes[k + n - 1].jonction))
            else:
                resultat.append(alignes[k])
            k += n
        return PhraseAlignee(resultat)

    def _lecture_abregement(self, m: Mot) -> list[Mot]:
        """Abrègement absent du lexique : sigle et initiale épelés (lettres des Spéciaux), abréviation développée."""
        if m.lecture:
            return list(m.lecture)
        if m.abregement in ("sigle", "initiale"):
            lettres = []
            for i, c in enumerate(m.forme):
                if c.isalpha():
                    lettres.append(Mot(TypeMot.MOT, c.upper(), m.debut + i, m.debut + i + 1, nature="lettre"))
            return lettres or [m]
        if m.abregement == "abreviation":
            a = table_abregements().get(m.forme)
            if a and a.developpement:
                return [Mot(TypeMot.MOT, x, m.debut, m.fin) for x in a.developpement.split()]
        return [m]

    def _mot(self, mot: Mot, analyse: Analyse | None) -> MotAligne:
        if mot.type is TypeMot.PONCTUATION:
            return MotAligne(mot, (Couple("", mot.forme),), analyse=analyse, origine="ponctuation")
        entree = self._entree(mot, analyse)
        if entree is not None:
            couples = a_la_casse(entree.couples, mot.forme) or (Couple(entree.phone_enrichi, mot.forme),)
            return MotAligne(mot, couples, entree.phone_enrichi, _analyse_de(analyse, entree), "lexique")
        if "-" in mot.forme.strip("-") and mot.type is TypeMot.MOT:
            couples = self._compose(mot, analyse)
            if couples:
                return MotAligne(mot, couples, phone_des_couples(couples), analyse, "composition")
        couples = None
        if self.modele and any(c.isalpha() for c in mot.forme) and all(c.isalpha() or c in "'-." for c in mot.forme):
            couples = self.modele.aligner(mot.forme.strip("."), analyse)
        if couples:
            couples = a_la_casse(couples, mot.forme.strip(".")) or couples
            if mot.forme.endswith("."):
                couples = couples + (Couple("", "."),)
            return MotAligne(mot, couples, phone_des_couples(couples), analyse, "modele")
        return MotAligne(mot, (Couple("", mot.forme),), analyse=analyse, origine="inconnu")

    def _entree(self, mot: Mot, analyse: Analyse | None) -> Entree | None:
        if mot.nature == "lettre":
            lettres = [e for e in self.lexique.speciales(mot.forme) if e.type == "lettre"] \
                if hasattr(self.lexique, "speciales") else []
            return choisir(lettres or self.lexique.lectures(mot.forme), None, mot.forme)
        entrees = self.lexique.lectures(mot.forme)
        return choisir(entrees, analyse, mot.forme)

    def _compose(self, mot: Mot, analyse: Analyse | None) -> tuple[Couple, ...] | None:
        """Mot à trait d'union absent du lexique (*search-engine*) : ses parties, jointes par le couple du tiret qui
        porte la frontière de syllabe de la partie suivante (``ˈ=-`` si elle commence par une syllabe accentuée)."""
        resultat: list[Couple] = []
        for k, partie in enumerate(mot.forme.split("-")):
            if not partie:
                resultat.append(Couple("", "-"))
                continue
            sous = Mot(TypeMot.MOT, partie, mot.debut, mot.fin)
            e = self._entree(sous, None)
            couples = a_la_casse(e.couples, partie) if e and e.couples else None
            if couples is None and self.modele and partie.isalpha():
                couples = self.modele.aligner(partie, analyse)
                couples = a_la_casse(couples, partie) if couples else None
            if not couples:
                return None
            if k:
                tete = couples[0].phone if couples[0].frontiere else SYLLABE
                couples = couples[1:] if couples[0].frontiere else couples
                resultat.append(Couple(tete, "-"))
            resultat.extend(couples)
        return tuple(resultat)

    def _contraction(self, groupe: list[MotAligne]) -> None:
        """Hôte + clitiques : forme entière du lexique partagée entre les mots, sinon clitique réalisé après l'hôte."""
        entier = "".join(m.mot.forme for m in groupe)
        entrees = self.lexique.lectures(entier)
        entree = max(entrees, key=lambda e: (e.ortho == entier, e.frequence)) if entrees else None
        if entree and entree.couples:
            parts = partager(a_la_casse(entree.couples, entier) or entree.couples, [len(m.mot.forme) for m in groupe])
            if parts:
                for m, cs in zip(groupe, parts):
                    m.couples, m.phone_enrichi, m.origine = cs, phone_des_couples(cs), "lexique"
                for m in groupe[1:]:
                    m.clitique = True
                return
        hote = phone_des_couples(groupe[0].couples)
        for m in groupe[1:]:
            cs = clitique(m.mot.forme, hote)
            if cs is not None:
                m.couples, m.phone_enrichi, m.origine = cs, phone_des_couples(cs), "composition"
            m.clitique = True
            hote += phone_des_couples(m.couples)

    def _aligner_homophone(self, e: Entree, a: Analyse | None) -> tuple[Couple, ...]:
        """Couples d'une entrée sans alignement (index des homophones du lexique embarqué) : G2P du modèle de mot, gardé
        s'il redonne la prononciation de l'entrée ; sinon un seul couple."""
        if self.modele and e.ortho.isalpha():
            couples = self.modele.aligner(e.ortho, Analyse(e.upos, dict(e.feats), e.lemme))
            if couples and sans_marques(phone_des_couples(couples)) == sans_marques(e.phone_enrichi):
                return a_la_casse(couples, e.ortho) or couples
        return (Couple(e.phone_enrichi, e.ortho),)

    def _graphie_composee(self, m: Mot, a: Analyse | None) -> MotAligne:
        """Mot phonétique à trait d'union (``ˈwɛl-ˈnoʊn``) absent du lexique : chaque partie, jointes par ``-``."""
        couples: list[Couple] = []
        for k, partie in enumerate(p for p in m.forme.split("-") if p):
            sous = self._graphie(Mot(TypeMot.MOT, partie, m.debut, m.fin), None, partie)
            if k:
                couples.append(Couple("", "-"))
            couples.extend(sous.couples)
        return MotAligne(m, tuple(couples), m.forme, a, "composition")

    # ── Écriture : phonétique → texte ─────────────────────────────────────────

    def ecrire(self, chaine: str, formules: bool = True, **_options) -> list[PhraseAlignee]:
        """Phonétique → texte. ``formules`` : les suites de mots qui disent une formule (*three dollars fifty*) sont
        écrites en chiffres (``formules.reconnaitre``), comme le français."""
        return self.ecrire_textes([chaine], formules)[0]

    def ecrire_textes(self, chaines: list[str], formules: bool = True) -> list[list[PhraseAlignee]]:
        """Plusieurs chaînes phonétiques à la fois (analyse par paquets)."""
        preps = [[self._preparer_phone(p.mots) for p in recomposer(tokeniser_phone(c), self.lexique).phrases]
                 for c in chaines]
        a_plat = [pr for prs in preps for pr in prs]
        analyses = self._analyser_lot([pr[0] for pr in a_plat], "phone")
        resultats, k = [], 0
        for prs in preps:
            phrases = [self._phrase_phone(pr, analyses[k + i]) for i, pr in enumerate(prs)]
            k += len(prs)
            if formules:
                for p in phrases:
                    p.mots = _formules_dites(p.mots)
            resultats.append(phrases)
        return resultats

    def _preparer_phone(self, mots: list[Mot]) -> tuple:
        # Jetons de surface : un clitique rejoint son hôte (« ˈbɑb‿z »), comme les contractions du modèle de phrase.
        jetons: list[Jeton] = []
        rangs: list[tuple[int, int]] = []
        for k, m in enumerate(mots):
            if m.type is TypeMot.PONCTUATION:
                jetons.append(Jeton(m.forme, "p"))
            elif m.nature == CLITIQUE and jetons and jetons[-1].type == "m":
                jetons[-1].phone += LIAISON + m.forme
                jetons[-1].mots = (jetons[-1].mots or ("",)) + ("",)
                rangs.append((len(jetons) - 1, len(jetons[-1].mots) - 1))
                continue
            else:
                c = cle(m.forme)
                variantes = (_faibles()[c],) if c in _faibles() else ()
                if c == "ɪz" and k and mots[k - 1].type is TypeMot.MOT and dernier_phoneme(mots[k - 1].forme) in SIFFLANTES:
                    # « ˈbʊʃ ɪz » : Bush is ou Bush's ; le modèle de phrase choisit (candidats 's), is par défaut
                    variantes += ("z",)
                jetons.append(Jeton("", "m", phone=m.forme, variantes=variantes))
            rangs.append((len(jetons) - 1, 0))
        return jetons, rangs, mots

    def _phrase_phone(self, prep: tuple, analyses_jetons: list[list[Analyse]]) -> PhraseAlignee:
        jetons, rangs, mots = prep
        alignes: list[MotAligne] = []
        for k, (m, (j, r)) in enumerate(zip(mots, rangs)):
            a = analyses_jetons[j][0] if analyses_jetons and analyses_jetons[j] else None
            if m.type is TypeMot.PONCTUATION:
                alignes.append(MotAligne(m, (Couple("", m.forme),), analyse=a, origine="ponctuation", phone=m.forme))
                continue
            if m.type is TypeMot.INCONNU:
                alignes.append(MotAligne(m, (Couple(m.forme, ""),), analyse=a, origine="inconnu", phone=m.forme))
                continue
            jeton = jetons[j]
            if r == 0 and len(jeton.mots) > 1 and a is not None and a.entree is not None and "'" in a.entree.ortho:
                # l'analyseur a reconnu la suite hôte + clitique comme un mot du lexique (*Bob's*, *bobs*)
                e = a.entree
                aligne = MotAligne(m, e.couples or (Couple(e.phone_enrichi, e.ortho),), e.phone_enrichi, a, "lexique")
                aligne.absorbe = len(jeton.mots) - 1
            elif r > 0:
                hote = alignes[-1]
                if getattr(hote, "absorbe", 0):
                    hote.absorbe -= 1
                    hote.mot = replace(hote.mot, fin=m.fin, forme=hote.mot.forme + LIAISON + m.forme)
                    continue
                ecrit = _CLITIQUE_ECRIT.get(cle(m.forme), "'" + cle(m.forme))
                aligne = MotAligne(m, (Couple(m.forme, ecrit),), m.forme, a, "clitique")
                aligne.clitique = True
            elif len(jeton.mots) > 1:
                # hôte d'un clitique : graphie de l'hôte seul (l'analyse vaut pour le jeton entier)
                aligne = self._graphie(m, a if a is None or a.entree is None else replace(a, entree=None), m.forme)
            else:
                fin = all(x.type is TypeMot.PONCTUATION for x in mots[k + 1 : k + 2])
                if "z" in jeton.variantes and cle(m.forme) == "ɪz" and a is not None and a.entree is not None \
                        and a.entree.ortho == "'s" and alignes and alignes[-1].origine != "ponctuation":
                    aligne = MotAligne(m, (Couple(SYLLABE, "'"), Couple("ɪz", "s")), "ɪz", a, "lexique")
                    aligne.clitique = True
                else:
                    aligne = self._graphie(m, a, jeton.phone, fin_de_groupe=fin)
            alignes.append(aligne)
        _a_ou_an(alignes)
        for k, m in enumerate(alignes):
            precedent = alignes[k - 1] if k else None
            if m.origine == "ponctuation":
                m.espace = m.mot.espace_avant and m.mot.forme in "([{\"“«"
            elif m.clitique:
                m.espace = False
            else:
                m.espace = precedent is not None and not (precedent.origine == "ponctuation" and precedent.mot.forme in "([{“«")
            m.phone = ("" if not k else (LIAISON if precedent and precedent.mot.jonction in (CLITIQUE, ENCHAINEMENT) else " ")) + m.mot.forme
            m.jonction = m.mot.jonction or "espace"
        _majuscule_initiale(alignes)
        return PhraseAlignee(alignes)

    def _graphie(self, m: Mot, a: Analyse | None, phone_cherche: str, fin_de_groupe: bool = False) -> MotAligne:
        """Graphie d'un mot prononcé : choix de l'analyseur parmi les homophones (tête de sélection), sinon accord avec
        l'analyse puis fréquence, sinon modèle de mot (P2G)."""
        entree = a.entree if a is not None else None
        c = cle(m.forme)
        if c in _faibles() and (entree is None or entree.frequence < _ZIPF_RARE):
            # forme forte ou de jonction (ˈfɹʌm, ði) prise pour un homophone rare (frum, thee) : le mot grammatical
            faible = [e for e in self.lexique.homophones(_faibles()[c]) if e.frequence >= _ZIPF_RARE]
            entree = choisir(faible, a) if faible else entree
        forte = _fortes().get(c)
        if forte and fin_de_groupe and (entree is None or entree.ortho.lower() != forte):
            # forme forte en fin de groupe (J3 : « I want to. » ˈtu, « what for? » ˈfɔɹ) : le mot grammatical plutôt
            # que son homophone (two, four), seule place où la chaîne pose une forme forte
            propres = [e for e in self.lexique.lectures(forte) if e.upos in _CATEGORIES_FORTES or e.ortho.lower() == "to"]
            entree = choisir(propres, a) or entree
        if entree is None and "-" in m.forme.strip("-"):
            return self._graphie_composee(m, a)
        if entree is None:
            cands = self.lexique.homophones(phone_cherche) or self.lexique.homophones(m.forme)
            if not cands and cle(m.forme) in _faibles():
                cands = self.lexique.homophones(_faibles()[cle(m.forme)])     # forme forte : ˈfɹʌm → from
            cands = [e for e in cands if not (e.speciale and e.type in ("symbole",))]
            entree = choisir(cands, a) if cands else None
        if entree is not None:
            couples = entree.couples or self._aligner_homophone(entree, a)
            return MotAligne(m, couples, entree.phone_enrichi, a, "lexique")
        # mot absent du lexique : analyse improvisée par l'étalon, sans lemme fiable (décodé lettre à lettre) → GPA sans lemme
        couples = self.modele.graphier(m.forme, replace(a, lemme="") if a is not None else None) if self.modele else None
        if couples:
            return MotAligne(m, couples, phone_des_couples(couples), a, "modele")
        return MotAligne(m, (Couple(m.forme, ""),), analyse=a, origine="inconnu")


# ── Outils ────────────────────────────────────────────────────────────────────


def _est_clitique(precedent: Mot, mot: Mot) -> bool:
    return (not mot.espace_avant and mot.debut == precedent.fin and mot.type is TypeMot.MOT
            and precedent.type is TypeMot.MOT and mot.forme.lower() in FORMES_CLITIQUES
            and decomposer(precedent.forme + mot.forme) is not None)


def _analyse_de(analyse: Analyse | None, entree: Entree) -> Analyse:
    """Analyse retenue pour la sortie : celle de l'analyseur, ou celle de l'entrée du lexique faute d'analyse."""
    if analyse is not None:
        return analyse
    return Analyse(entree.upos, dict(entree.feats), entree.lemme)


def _faibles() -> dict[str, str]:
    """Forme forte ou de jonction (clé sans marques) → forme faible du lexique (``ˈfɹʌm`` → ``fɹəm``, ``ði`` → ``ðə``)."""
    global _FAIBLES
    if _FAIBLES is None:
        from .jonctions import FICHIER_FORMES_FORTES

        _FAIBLES = {"ði": "ðə", "tu": "tə"}
        for ligne in FICHIER_FORMES_FORTES.read_text(encoding="utf-8").splitlines():
            if ligne and not ligne.startswith("#"):
                _forme, _cats, faible, forte = (ligne.split("\t") + [""] * 4)[:4]
                if faible and sans_marques(forte) != sans_marques(faible):
                    _FAIBLES.setdefault(sans_marques(forte), faible)
    return _FAIBLES


_FAIBLES: dict[str, str] | None = None
_CATEGORIES_FORTES = frozenset({"AUX", "ADP", "PART"})


def _fortes() -> dict[str, str]:
    """Forme forte (clé sans marques) → mot grammatical de la table (``tu`` → to, ``fɔɹ`` → for)."""
    from .jonctions import formes_fortes

    if not hasattr(_fortes, "table"):
        _fortes.table = {}
        for forme, lignes in formes_fortes().items():
            for cats, forte in lignes:
                if cats & _CATEGORIES_FORTES:
                    _fortes.table.setdefault(sans_marques(forte), forme)
    return _fortes.table


def _forme_faible(phone: str) -> str:
    """Prononciation donnée à l'analyseur : ``ði``, ``tu`` (jonctions J1, J2) ramenés à ``ðə``, ``tə``, que le lexique
    et la tête de sélection connaissent."""
    c = cle(phone)
    return _faibles()[c] if c in ("ði", "tu") else phone


def partager(couples: tuple[Couple, ...], longueurs: list[int]) -> list[tuple[Couple, ...]] | None:
    """Partage la forme linéaire d'une contraction entre ses mots, aux frontières de lettres (*don't* → *do* + *n't*).
    Une frontière de syllabe va au mot de la lettre qui la suit ; un couple à cheval (``n=nn`` de *gonna*) est coupé :
    le phonème reste à la première partie, la seconde est muette."""
    bornes, total = [], 0
    for n in longueurs:
        total += n
        bornes.append(total)
    parts: list[list[Couple]] = [[] for _ in longueurs]
    pos, attente = 0, []
    for c in couples:
        if c.frontiere:
            attente.append(c)
            continue
        k = next((i for i, b in enumerate(bornes) if pos < b), len(bornes) - 1)
        parts[k].extend(attente)
        attente = []
        reste, phone = c.graphe, c.phone
        while reste:
            k = next((i for i, b in enumerate(bornes) if pos < b), len(bornes) - 1)
            prend = min(len(reste), bornes[k] - pos) if bornes[k] > pos else len(reste)
            parts[k].append(Couple(phone, reste[:prend]))
            phone, reste, pos = "", reste[prend:], pos + prend
    if attente:
        parts[-1].extend(attente)
    if pos != total or any(not p for p in parts):
        return None
    return [tuple(p) for p in parts]


def a_la_casse(couples: tuple[Couple, ...], forme: str) -> tuple[Couple, ...]:
    """Rend aux graphèmes la casse et l'apostrophe du texte (majuscule de début de phrase sur une entrée en minuscules,
    *DON'T*) ; ``()`` si la graphie ne correspond pas."""
    ecrit = "".join(c.graphe for c in couples if not c.frontiere)
    norm = lambda s: s.lower().replace("’", "'")
    if ecrit == forme:
        return couples
    if norm(ecrit) != norm(forme):
        return ()
    resultat, reste = [], forme
    for c in couples:
        if c.frontiere:
            resultat.append(c)
        else:
            resultat.append(replace(c, graphe=reste[: len(c.graphe)]))
            reste = reste[len(c.graphe) :]
    return tuple(resultat)


def _formules_dites(alignes: list[MotAligne]) -> list[MotAligne]:
    """Remplace les suites de mots qui disent une formule par sa forme écrite (une formule = un mot à lecture)."""
    from .formules import reconnaitre

    ecrits = ["".join(c.graphe for c in m.couples if not c.frontiere) if m.origine == "lexique" else "\u2205"
              for m in alignes]
    resultat, k = [], 0
    for r in reconnaitre(ecrits):
        resultat.extend(alignes[k : r.debut])
        lus = alignes[r.debut : r.fin]
        mot = Mot(TypeMot.FORMULE, r.ecriture, lus[0].mot.debut, lus[-1].mot.fin, type_formule=r.type, valeur=r.valeur)
        resultat.append(MotAligne(mot, origine="formule", analyse=lus[0].analyse, lecture=lus, espace=lus[0].espace,
                                  jonction=lus[-1].jonction))
        k = r.fin
    return resultat + alignes[k:]


def _a_ou_an(alignes: list[MotAligne]) -> None:
    """*a* / *an* écrits d'après le son suivant (spec 09, J4)."""
    for k, m in enumerate(alignes[:-1]):
        ecrit = "".join(c.graphe for c in m.couples if not c.frontiere).lower()
        if ecrit not in ("a", "an") or m.origine != "lexique":
            continue
        suivant = alignes[k + 1]
        if suivant.origine == "ponctuation":
            continue
        voyelle = commence_par_voyelle(suivant.mot.forme)
        if ecrit == "a" and voyelle:
            m.couples = (Couple("ə", "a"), Couple("n", "n"))
        elif ecrit == "an" and not voyelle:
            m.couples = (Couple("ə", "a"),)


def _majuscule_initiale(alignes: list[MotAligne]) -> None:
    for m in alignes:
        if m.origine == "ponctuation":
            continue
        for k, c in enumerate(m.couples):
            if c.graphe[:1].isalpha():
                m.couples = m.couples[:k] + (replace(c, graphe=c.graphe[0].upper() + c.graphe[1:]),) + m.couples[k + 1 :]
                return
        return
