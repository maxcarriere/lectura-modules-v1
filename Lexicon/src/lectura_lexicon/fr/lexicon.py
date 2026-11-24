# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Moteur local du français : fonctions lexicales sur une base au format rapide (``lexicon.db``, construite par
``lectura_lexicon.conversion`` ou remise avec la licence commerciale). Utilisé par ``Lexicon(langue="fr")`` en mode
local, et par le faux serveur des tests comme le serait le serveur de l'API.

Bibliothèque standard seule (sqlite3). Les fonctions qui demandent les analyses (lemme, traits) rendent une liste
vide en taille ``mini`` ; ``lectures`` y donne seulement les prononciations.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from .cles import (anagramme, cle_phone, commun_final, commun_inverse, fin_inverse, qualite_commune, distance, empreinte, minuscule, neutraliser, phonemes, qualite_rime,
                   rime_finale, suppressions, syllabes_de)
from .donnees import ACCEPTEE_NOYAU, NON_VALIDE, PROPRE_SEUL, RECTIFIEE, SPECIAL, UTILISATEUR
from .utilisateur import Dictionnaire, chemin_par_defaut
from .donnees import VARIANTE as _VARIANTE

from .._types import ACCEPTEE, INCONNUE, PROPOSABLE, RARE, VARIANTE, Forme, Lecture, Seuils
_RANG = {INCONNUE: 0, RARE: 1, VARIANTE: 2, ACCEPTEE: 3, PROPOSABLE: 4}
TAILLES = ("complet", "standard", "mini")
CASSES = ("toutes", "regrouper", "minuscules")    # (0.5) variantes de casse dans les homophones et les voisins


def _filtrer(formes: list[Forme], propres: bool = True, casse: str = "toutes") -> list[Forme]:
    """(0.5, comme lexicon-en 0.3) Filtre de présentation, l'ordre restant celui de ``formes`` : sans ``propres``, ni
    noms propres seuls ; ``casse`` : « toutes » (défaut, tout garder), « regrouper » (une forme par graphie en
    minuscules : la graphie en minuscules si elle est là, sinon la première), « minuscules » (seulement les graphies
    écrites en minuscules)."""
    if casse not in CASSES:
        raise ValueError(f"casse « {casse} » : attendu {', '.join(CASSES)}")
    if not propres:
        formes = [f for f in formes if not f.propre]
    if casse == "minuscules":
        return [f for f in formes if f.ortho == minuscule(f.ortho)]
    if casse == "regrouper":
        choix: dict[str, Forme] = {}
        for f in formes:
            m = minuscule(f.ortho)
            if m not in choix or (f.ortho == m and choix[m].ortho != m):
                choix[m] = f
        gardees = {id(f) for f in choix.values()}
        return [f for f in formes if id(f) in gardees]
    return formes


def _dans_dossier(dossier: Path, taille: str | None) -> Path | None:
    if taille is None and (dossier / "lexicon.db").exists():      # base posée seule (``convertir``)
        return dossier / "lexicon.db"
    for t in ([taille] if taille else TAILLES):
        if (dossier / t / "lexicon.db").exists():
            return dossier / t / "lexicon.db"
        if (dossier / t / "lexicon.tsv.xz").exists():
            from .installation import installee
            return installee(dossier / t / "lexicon.tsv.xz")
    return None


def trouver_donnees(taille: str | None = None) -> Path:
    """``LECTURA_LEXICON_DATA`` (fichier ou dossier), ``LECTURA_MODELS_DIR/lexicon``, ``~/.lectura/models/lexicon`` ;
    dans un dossier, la plus grande taille présente (ou ``taille``). Une taille livrée
    compressée (``lexicon.tsv.xz``, sans ``lexicon.db``) est installée dans le cache au premier usage."""
    env = os.environ.get("LECTURA_LEXICON_DATA")
    if env and Path(env).is_file():
        return Path(env)
    dossiers = [Path(env)] if env else []
    if os.environ.get("LECTURA_MODELS_DIR"):
        dossiers.append(Path(os.environ["LECTURA_MODELS_DIR"]) / "lexicon")
    dossiers.append(Path.home() / ".lectura" / "models" / "lexicon")
    for d in dossiers:
        chemin = _dans_dossier(d, taille)
        if chemin is not None:
            return chemin
    raise FileNotFoundError(_absente(taille))


def _absente(taille: str | None) -> str:
    """Message clair quand aucune base n'est trouvée en mode local."""
    return (f"aucune base Lexicon (français) trouvée en local (taille {taille or 'quelconque'}). Le paquet ne contient "
            "aucune base. Trois possibilités : (1) ne rien indiquer et utiliser l'API publique de Lectura "
            "(Lexicon(langue='fr'), mode par défaut) ; (2) donner le chemin d'une base au format rapide, par "
            "l'argument chemin= ou la variable LECTURA_LEXICON_DATA ; (3) construire cette base depuis un lexique "
            "que vous possédez (LeXiK téléchargée, Lexique 3, GLAFF, CSV/TSV) : python -m lectura_lexicon convertir "
            "--help. Les bases prêtes à l'emploi de Lectura accompagnent la licence commerciale (contact via "
            "https://www.lectura.world).")


_ACCENTS = {"a": "aàâä", "e": "eéèêë", "i": "iîï", "o": "oôö", "u": "uùûü", "y": "yÿ", "c": "cç"}


def _glob_sans_accents(motif: str) -> str:
    """Motif GLOB où chaque lettre vaut aussi ses formes accentuées (« ecole » → [eéèêë]c[oôö]l[eéèêë])."""
    from .cles import sans_accents

    return "".join(f"[{_ACCENTS[c]}]" if c in _ACCENTS else "[[]" if c == "[" else c for c in sans_accents(motif))


class Lexicon:
    def __init__(self, chemin: str | Path | None = None, taille: str | None = None, seuils: Seuils | None = None,
                 dictionnaire: Dictionnaire | str | Path | bool | None = None):
        """``dictionnaire`` : mots de l'utilisateur (``utilisateur.Dictionnaire``, chemin de son fichier, ``True`` pour
        le fichier par défaut) ; sans lui, ``ajouter`` en crée un en mémoire."""
        chemin = Path(chemin) if chemin else trouver_donnees(taille)
        if chemin.is_dir():
            dossier, chemin = chemin, _dans_dossier(chemin, taille)
            if chemin is None:
                raise FileNotFoundError(f"pas de données de taille {taille or 'quelconque'} dans {dossier}. "
                                        + _absente(taille))
        elif chemin.name.endswith(".tsv.xz"):
            from .installation import installee
            chemin = installee(chemin)
        self.chemin = chemin
        self._db = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True, check_same_thread=False)
        self.meta = dict(self._db.execute("SELECT cle, valeur FROM metadonnees"))
        self.taille = self.meta.get("taille", "?")
        self.seuils = seuils or Seuils()
        self._codes: dict[str, dict[int, str]] = {}
        for espace, i, valeur in self._db.execute("SELECT espace, id, valeur FROM codes"):
            self._codes.setdefault(espace, {})[i] = valeur
        # analyses présentes : une base nue indexée en a dans toutes ses tailles ; la mini 0.5 n'en a pas
        self._analyses = self._db.execute("SELECT 1 FROM analyses LIMIT 1").fetchone() is not None
        self._n_suppr = int(self.meta.get("suppressions", 1))
        self._colonnes_lemmes = {r[1] for r in self._db.execute("PRAGMA table_info(lemmes)")}
        # données 0.5 : étiquette MULTEXT des analyses (absente des données plus anciennes : NULL)
        colonnes_analyses = {r[1] for r in self._db.execute("PRAGMA table_info(analyses)")}
        self._multext = "a.multext" if "multext" in colonnes_analyses else "NULL"
        self._marque = "a.marque" if "marque" in colonnes_analyses else "NULL"     # (0.5) marques du Wiktionnaire
        self._rimes_larges: dict[tuple[str, str], list] = {}   # fins de rime très répandues, en mémoire
        if dictionnaire is True:
            dictionnaire = Dictionnaire(chemin_par_defaut())
        elif isinstance(dictionnaire, (str, Path)):
            dictionnaire = Dictionnaire(dictionnaire)
        self.dictionnaire: Dictionnaire | None = dictionnaire if isinstance(dictionnaire, Dictionnaire) else None
        self._ids_utilisateur: tuple[int, list] = (-1, [])
        # données 0.4 : clés venues seulement de lectures masquées (lettres épelées, abréviations) écartées
        visibles = "masquee" in {r[1] for r in self._db.execute("PRAGMA table_info(phones)")}
        self._visible = (lambda alias: f" AND {alias}.masquee = 0") if visibles else (lambda alias: "")

    # ── Formes ─────────────────────────────────────────────────────────────────

    @lru_cache(maxsize=200_000)
    def _lignes_min(self, mini: str) -> tuple[tuple, ...]:
        return tuple(self._db.execute("SELECT id, ortho, zipf, zipf_lemme, drapeaux FROM formes WHERE min = ?", (mini,)))

    # ── Dictionnaire de l'utilisateur ─────────────────────────────────────────

    def ajouter(self, ortho: str, phone: str = "", upos: str = "", lemme: str = "", **options):
        """Ajoute un mot au dictionnaire de l'utilisateur (créé en mémoire s'il n'y en a pas) : il devient une forme
        acceptée et proposable, avec sa prononciation pour les homophones et l'écriture du Transducer branché."""
        if self.dictionnaire is None:
            self.dictionnaire = Dictionnaire()
        return self.dictionnaire.ajouter(ortho, phone, upos, lemme, **options)

    def retirer(self, ortho: str) -> bool:
        return self.dictionnaire.retirer(ortho) if self.dictionnaire is not None else False

    def _mots_utilisateur(self) -> list:
        """Mots du dictionnaire, numérotés : la forme d'identifiant ``-(k + 1)`` est le k-ième (refait à chaque
        changement du dictionnaire)."""
        d = self.dictionnaire
        if d is None:
            return []
        if self._ids_utilisateur[0] != d.version:
            self._ids_utilisateur = (d.version, d.mots())
        return self._ids_utilisateur[1]

    def _lignes_utilisateur(self, mots) -> list[tuple]:
        index = {id(m): k for k, m in enumerate(self._mots_utilisateur())}
        return [(-(index[id(m)] + 1), m.ortho, m.zipf, 0.0, UTILISATEUR) for m in mots if id(m) in index]

    def _correspondances(self, forme: str) -> list[tuple]:
        """Formes de la base (et du dictionnaire de l'utilisateur) qui valent ``forme`` : graphie exacte ; en début de
        phrase (« Chat ») ou en capitales (« CHAT », « PARIS »), aussi la graphie en minuscules ou la graphie à
        majuscule. Une forme en minuscules ne vaut pas un nom propre (« paris » ≠ « Paris »)."""
        lignes = self._lignes_min(minuscule(forme))
        if self.dictionnaire is not None and len(self.dictionnaire):
            self._mots_utilisateur()
            lignes = lignes + tuple(self._lignes_utilisateur(self.dictionnaire.lectures_min(minuscule(forme))))
        exactes = [l for l in lignes if l[1] == forme]
        if exactes or forme == minuscule(forme):
            return exactes
        if forme.isupper() and len(forme) > 1:
            return list(lignes)
        return [l for l in lignes if l[1] == minuscule(forme)]

    def _niveau(self, ligne: tuple) -> str:
        _, _, zipf, zl, drapeaux = ligne
        if drapeaux & NON_VALIDE:              # jeton « Non classé » de LeXiK : jamais un mot sûr, quel que soit son zipf
            return INCONNUE
        s = self.seuils
        if zipf >= s.acceptee or (drapeaux & ACCEPTEE_NOYAU and zl >= s.acceptee_lemme):
            if drapeaux & _VARIANTE:
                return VARIANTE
            return PROPOSABLE if zipf >= s.proposable else ACCEPTEE
        return RARE

    def validite(self, forme: str) -> str:
        """« proposable » (assez courante pour être proposée), « acceptee » (juste, à ne jamais signaler),
        « variante » (graphie ancienne ou concurrente : enfans, loix, sçavoir ; acceptée, jamais proposée ; voir
        ``usuelle``), « rare » (dans LeXiK sous les seuils : taille complète, et mini élargie depuis la 0.5) ou
        « inconnue ». Une forme vue seulement dans la table « Non classé » de LeXiK (drapeau ``non_valide``, mini 0.5)
        est « inconnue » : sa fréquence reste donnée par ``frequence`` et ``forme``."""
        return max((self._niveau(l) for l in self._correspondances(forme)), key=_RANG.get, default=INCONNUE)

    def existe(self, forme: str) -> bool:
        """Vrai si la forme est un mot sûr : validité « variante », « acceptee » ou « proposable »."""
        return _RANG[self.validite(forme)] >= _RANG[VARIANTE]

    def est_valide(self, forme: str) -> bool:
        """Synonyme de ``existe`` (0.5) : mot sûr ; jamais vrai pour une forme ``non_valide``."""
        return self.existe(forme)

    def non_valide(self, forme: str) -> bool:
        """(0.5) Vrai si toutes les graphies qui valent ``forme`` viennent seulement de la table « Non classé » de
        LeXiK (jetons de corpus jamais validés : another, Takada) : présentes avec leur fréquence, jamais sûres."""
        lignes = self._correspondances(forme)
        return bool(lignes) and all(l[4] & NON_VALIDE for l in lignes)

    def usuelle(self, forme: str) -> str | None:
        """Graphie usuelle d'une forme variante (enfans → enfants), quand LeXiK la donne."""
        for i, *_ in self._correspondances(forme):
            r = self._db.execute("SELECT usuelle FROM usuelles WHERE forme = ?", (i,)).fetchone()
            if r:
                return r[0]
        return None

    def rectifiee(self, forme: str) -> bool:
        """Graphie de l'orthographe rectifiée de 1990 (gout, paraitre, cout) ; sa graphie classique est donnée par
        ``usuelle`` quand elle est variante. Données construites avant la v0.3.2 : toujours faux."""
        return any(l[4] & RECTIFIEE for l in self._correspondances(forme))

    def frequence(self, forme: str) -> float:
        """Zipf de la forme (graphie exacte, sinon comme ``validite``) ; 0 si inconnue."""
        return max((l[2] for l in self._correspondances(forme)), default=0.0)

    def forme(self, forme: str, avec_lectures: bool = True) -> Forme | None:
        lignes = self._correspondances(forme)
        if not lignes:
            return None
        l = max(lignes, key=lambda x: (_RANG[self._niveau(x)], x[2]))
        return self._forme(l, avec_lectures=avec_lectures)

    def _forme(self, ligne: tuple, dist: int = 0, avec_lectures: bool = False) -> Forme:
        i, ortho, zipf, _, drapeaux = ligne
        return Forme(ortho, zipf, self._niveau(ligne), bool(drapeaux & PROPRE_SEUL), bool(drapeaux & SPECIAL), dist,
                     self._lectures_id(i, ortho, zipf) if avec_lectures else (), non_valide=bool(drapeaux & NON_VALIDE))

    # ── Lectures ───────────────────────────────────────────────────────────────

    def lectures(self, forme: str, toutes: bool = False) -> list[Lecture]:
        """Analyses de la forme (comme ``validite`` pour la casse) : lemme, UPOS, traits, prononciation, zipf.
        Sans ``toutes``, les analyses masquées (zipf 0 venues d'un paradigme généré, alors qu'une autre analyse de la
        forme est attestée) sont écartées."""
        res: list[Lecture] = []
        for i, ortho, zipf, _, _ in self._correspondances(forme):
            res.extend(l for l in self._lectures_id(i, ortho, zipf) if toutes or not l.masquee)
        return res

    @lru_cache(maxsize=100_000)
    def _lectures_id(self, i: int, ortho: str, zipf: float) -> tuple[Lecture, ...]:
        if i < 0:                                   # mot du dictionnaire de l'utilisateur
            mots = self._mots_utilisateur()
            if -i - 1 >= len(mots):
                return ()
            m = mots[-i - 1]
            upos = m.categorie()
            return (Lecture(m.ortho, m.lemme or m.ortho, upos if self._analyses else "", "", m.phone, m.zipf,
                            f"{m.lemme or m.ortho}#{upos}" if self._analyses else "", ("utilisateur",)),)
        if not self._analyses:
            return tuple(Lecture(ortho, phone=p, zipf=zipf) for p in self._phones_de(i))
        c = self._codes
        lignes = self._db.execute(
            "SELECT l.lemme, a.upos, a.traits, a.phone, a.zipf, l.id_lemme, a.sources, a.confiance, a.masquee, a.phone_enrichi, "
            f"{self._multext}, {self._marque} FROM analyses a JOIN lemmes l ON l.id = a.lemme WHERE a.forme = ? "
            "ORDER BY a.zipf DESC", (i,))
        msd = c.get("multext", {})
        return tuple(Lecture(ortho, lemme, c["upos"][u], c["traits"][t], phone, z, il,
                             tuple(c["sources"][s].split(",")) if s is not None and c["sources"][s] else (), conf or "",
                             bool(m), pe or "", msd.get(x, "") if x is not None else "", mq or "")
                     for lemme, u, t, phone, z, il, s, conf, m, pe, x, mq in lignes)

    def _phones_de(self, i: int) -> list[str]:
        (cles,) = self._db.execute("SELECT cles FROM formes WHERE id = ?", (i,)).fetchone()
        return [self._db.execute("SELECT cle FROM cles_phone WHERE id = ?", (int(k),)).fetchone()[0]
                for k in cles.split()] if cles else []

    def phones(self, forme: str) -> list[str]:
        """Prononciations de la forme (syllabées en taille standard, clés sans marque en mini)."""
        vues: list[str] = []
        for l in self.lectures(forme):
            if l.phone and l.phone not in vues:
                vues.append(l.phone)
        return vues

    # ── Homophones ─────────────────────────────────────────────────────────────

    def homophones(self, phone: str, neutre: bool = False, avec_lectures: bool = False, propres: bool = True,
                   casse: str = "toutes") -> list[Forme]:
        """Formes qui se prononcent ``phone`` (marques ignorées), de la plus fréquente à la moins fréquente ; avec
        ``neutre``, aussi celles qui n'en diffèrent que par le timbre d'une voyelle moyenne (e/ɛ, o/ɔ, ø/œ).
        (0.5) ``propres=False`` écarte les noms propres seuls ; ``casse`` : « toutes » (défaut), « regrouper » (une
        forme par graphie en minuscules), « minuscules » (graphies en minuscules seulement) ; ``ValueError`` sinon."""
        cles = {cle_phone(phone)}
        if neutre:
            cles |= self._cles_neutres(cle_phone(phone))
        return _filtrer(self._formes_des_cles(cles, avec_lectures), propres, casse)

    def _formes_des_cles(self, cles, avec_lectures: bool, distances: dict[str, int] | None = None) -> list[Forme]:
        res: dict[int, Forme] = {}
        for cle in cles:
            for ligne in self._db.execute(
                    "SELECT f.id, f.ortho, f.zipf, f.zipf_lemme, f.drapeaux FROM cles_phone c JOIN phones p ON p.cle = c.id "
                    "JOIN formes f ON f.id = p.forme WHERE c.cle = ?" + self._visible("p"), (cle,)):
                if ligne[4] & NON_VALIDE:      # jetons « Non classé » : hors homophones et voisins phonétiques
                    continue
                d = (distances or {}).get(cle, 0)
                if ligne[0] not in res or d < res[ligne[0]].distance:
                    res[ligne[0]] = self._forme(ligne, d, avec_lectures)
            if self.dictionnaire is not None and len(self.dictionnaire):
                d = (distances or {}).get(cle, 0)
                for ligne in self._lignes_utilisateur(self.dictionnaire.par_cle(cle)):
                    res[ligne[0]] = self._forme(ligne, d, avec_lectures)
        return sorted(res.values(), key=lambda f: (f.distance, -f.zipf, f.ortho))

    def _cles_neutres(self, cle: str) -> set[str]:
        """Clés de la base de même forme neutralisée (variantes de timbre de la clé)."""
        ph = phonemes(cle)
        variantes = [""]
        for p in ph:
            choix = {"e": "eɛ", "ɛ": "eɛ", "o": "oɔ", "ɔ": "oɔ", "ø": "øœ", "œ": "øœ"}.get(p, None)
            variantes = [v + c for v in variantes for c in (choix or [p])]
            if len(variantes) > 64:
                break
        return {v for v in variantes if neutraliser(v) == neutraliser(cle)}

    # ── Voisins ────────────────────────────────────────────────────────────────

    def voisins_orthographiques(self, forme: str, distance_max: int = 2, limite: int = 20,
                                validite_min: str = PROPOSABLE, propres: bool = True,
                                casse: str = "toutes") -> list[Forme]:
        """Formes à une distance d'édition ≤ ``distance_max`` (lettres en minuscules, transposition comptée 1),
        de validité ≥ ``validite_min``, triées par distance puis fréquence. Index : suppressions de lettres des formes
        (``meta['suppressions']``) contre suppressions de la requête jusqu'à ``distance_max`` ; une distance 2 qui
        demande deux suppressions côté forme (deux lettres oubliées, deux substitutions) n'est trouvée qu'avec un
        index à 2 suppressions."""
        mini = minuscule(forme)
        cles = [empreinte(x) for x in suppressions(mini, distance_max)]
        trouves: dict[int, Forme] = {}
        lignes = self._db.execute(
            f"SELECT DISTINCT f.id, f.ortho, f.zipf, f.zipf_lemme, f.drapeaux, f.min FROM voisins v "
            f"JOIN formes f ON f.id = v.forme WHERE v.cle IN ({','.join('?' * len(cles))})", tuple(cles))
        distances: dict[str, int] = {}      # une graphie en minuscules pour plusieurs casses (chat, Chat)
        for *ligne, cand in lignes:
            if cand == mini or _RANG[self._niveau(ligne)] < _RANG[validite_min]:
                continue
            d = distances.get(cand)
            if d is None:
                d = distances[cand] = distance(mini, cand, distance_max)
            if d <= distance_max:
                trouves[ligne[0]] = self._forme(ligne, d)
        if self.dictionnaire is not None and len(self.dictionnaire):     # quelques mots : distance à chacun
            for ligne in self._lignes_utilisateur(self._mots_utilisateur()):
                cand = minuscule(ligne[1])
                d = distance(mini, cand, distance_max)
                if cand != mini and d <= distance_max:
                    trouves[ligne[0]] = self._forme(ligne, d)
        return _filtrer(sorted(trouves.values(), key=lambda f: (f.distance, -f.zipf, f.ortho)), propres, casse)[:limite]

    def voisins_phonetiques(self, phone: str, tolerance: int = 1, neutre: bool = True, limite: int = 20,
                            validite_min: str = PROPOSABLE, propres: bool = True,
                            casse: str = "toutes") -> list[Forme]:
        """Formes dont la prononciation est à ≤ ``tolerance`` phonèmes près de ``phone`` (avec ``neutre``, timbre des
        voyelles moyennes ignoré), triées par distance puis fréquence. « otomobil » → automobile."""
        cle = cle_phone(phone)
        ph = phonemes(cle)
        req = [empreinte(x) for x in suppressions(ph, tolerance)]
        cles: dict[str, int] = {}
        for (c,) in self._db.execute(
                f"SELECT DISTINCT c.cle FROM voisins_phones v JOIN cles_phone c ON c.id = v.phone "
                f"WHERE v.cle IN ({','.join('?' * len(req))})", tuple(req)):
            a, b = (phonemes(neutraliser(cle)), phonemes(neutraliser(c))) if neutre else (ph, phonemes(c))
            d = distance(a, b, tolerance)
            if d <= tolerance:
                cles[c] = d
        res = [f for f in self._formes_des_cles(cles, False, cles) if _RANG[f.validite] >= _RANG[validite_min]]
        return _filtrer(res, propres, casse)[:limite]

    # ── Paradigmes (taille standard / complet) ─────────────────────────────────

    def formes_de(self, lemme: str, upos: str | None = None, toutes: bool = False) -> list[Lecture]:
        """Toutes les formes du lemme (``lemme`` ou identifiant ``lemme#UPOS[#n]``), éventuellement d'une catégorie.
        Sans ``toutes``, ni analyses masquées ni graphies variantes (enfans)."""
        if not self._analyses:
            return []
        c = self._codes
        champ = "id_lemme" if "#" in lemme else "lemme"
        lignes = self._db.execute(
            f"SELECT f.ortho, l.lemme, a.upos, a.traits, a.phone, a.zipf, l.id_lemme, l.upos, a.masquee, f.drapeaux, "
            f"{self._multext}, {self._marque} FROM lemmes l CROSS JOIN analyses a ON a.lemme = l.id "
            f"JOIN formes f ON f.id = a.forme WHERE l.{champ} = ?", (lemme,))
        msd = c.get("multext", {})
        return [Lecture(o, le, c["upos"][u], c["traits"][t], p, z, il, masquee=bool(m),
                        multext=msd.get(x, "") if x is not None else "", marque=mq or "")
                for o, le, u, t, p, z, il, lu, m, dr, x, mq in lignes
                if (upos is None or lu == upos or c["upos"][u] == upos) and (toutes or not (m or dr & _VARIANTE))]

    def variante(self, forme: str, toutes: bool = False, **traits: str) -> list[tuple[Lecture, Lecture]]:
        """Pour chaque lecture de la forme, les formes du même lemme et de même UPOS où **seuls** les traits donnés
        changent, les autres restant identiques : ``variante("mange", Number="Plur")`` → (mange Ind 3 Sing → mangent),
        (mange Ind 1 Sing → mangeons), (mange Imp 2 Sing → mangez)… Rend des couples (lecture de départ, forme cible) :
        l'appelant choisit la lecture (d'après l'analyseur). Un trait donné vide (``Gender=""``) est retiré. Sans
        ``toutes``, ni lectures masquées ni graphies variantes."""
        res: list[tuple[Lecture, Lecture]] = []
        for l in self.lectures(forme, toutes):
            cible = l.traits()
            for k, v in traits.items():
                if v:
                    cible[k] = v
                else:
                    cible.pop(k, None)
            if cible == l.traits():
                continue
            for x in self.formes_de(l.id_lemme, toutes=toutes):
                if x.upos == l.upos and x.traits() == cible and all(
                        (d, (y.ortho, y.feats)) != (l, (x.ortho, x.feats)) for d, y in res):
                    res.append((l, x))
        return sorted(res, key=lambda c: (-c[0].zipf, -c[1].zipf))

    def autre_genre(self, lemme: str) -> list[str]:
        """Lemmes de l'autre genre (LeXiK, colonnes ``masculin`` / ``feminin``) : acteur → actrice, amie → ami,
        directeur → directrice ; ``lemme`` ou identifiant ``lemme#UPOS``. Taille standard ou complète."""
        if not self._analyses or "masculin" not in self._colonnes_lemmes:
            return []
        champ = "id_lemme" if "#" in lemme else "lemme"
        res: list[str] = []
        lui = lemme.split("#")[0]
        for m, f in self._db.execute(f"SELECT masculin, feminin FROM lemmes WHERE {champ} = ?", (lemme,)):
            for x in (f, m):
                for autre in (x or "").split(","):
                    if autre.strip() and autre.strip() != lui and autre.strip() not in res:
                        res.append(autre.strip())
        return res

    # ── Table des lemmes : propriétés (LeXiK, ``lexik_lemmes``) ──────────────────

    _PROPRIETES = ("masculin", "feminin", "auxiliaire", "auxiliaire_source", "pronominal", "groupe", "ortho_1990")

    def _lignes_lemmes(self, lemme: str) -> list[dict]:
        """Lignes de ``lemmes`` pour ``lemme`` (ou identifiant ``lemme#UPOS[#n]``) ; à défaut, lemmes de la forme."""
        if not self._analyses:
            return []
        props = [c for c in self._PROPRIETES if c in self._colonnes_lemmes]
        colonnes = "id, id_lemme, lemme, upos, zipf" + "".join(f", {c}" for c in props)
        champ = "id_lemme" if "#" in lemme else "lemme"
        lignes = self._db.execute(f"SELECT {colonnes} FROM lemmes WHERE {champ} = ?", (lemme,)).fetchall()
        if not lignes:
            ids = self.lemmes_de(lemme)
            lignes = [r for i in ids for r in self._db.execute(f"SELECT {colonnes} FROM lemmes WHERE id_lemme = ?", (i,))]
        noms = ["id", "id_lemme", "lemme", "upos", "zipf", *props]
        return [dict(zip(noms, r)) for r in lignes]

    def _h_aspire_lemme(self, i: int, lemme: str) -> bool:
        """Le lemme se prononce avec un h aspiré : forme de citation (sinon toute forme) marquée ``*h*``."""
        lignes = self._db.execute(
            "SELECT f.ortho, a.phone_enrichi FROM analyses a JOIN formes f ON f.id = a.forme WHERE a.lemme = ?", (i,))
        marques = [(o == lemme, (pe or "").startswith("*h*")) for o, pe in lignes]
        citation = [m for est, m in marques if est]
        return any(citation) if citation else any(m for _, m in marques)

    def lemme_info(self, lemme: str) -> list[dict]:
        """Propriétés de chaque lemme qui vaut ``lemme`` (ou de l'identifiant ``lemme#UPOS[#n]`` ; à défaut, des
        lemmes de la forme) : ``id_lemme``, ``lemme``, ``upos``, ``zipf`` (fréquence du lemme), ``masculin`` /
        ``feminin`` (autre genre des noms), ``auxiliaire`` et ``auxiliaire_source`` (« lexik » : donné par LeXiK ;
        « regle » : déduit, « être » pour un verbe essentiellement pronominal, « avoir » sinon), ``pronominal``,
        ``groupe``, ``ortho_1990`` (« rectifiee », « traditionnelle »), ``h_aspire``. Une propriété absente de la
        base vaut ``None``."""
        res = []
        for r in self._lignes_lemmes(lemme):
            d = {k: r.get(k) for k in ("id_lemme", "lemme", "upos", "zipf", *self._PROPRIETES)}
            d["h_aspire"] = self._h_aspire_lemme(r["id"], r["lemme"])
            res.append(d)
        return res

    def h_aspire(self, forme: str) -> bool:
        """Vrai si une lecture de la forme commence par un h aspiré (*héros*, *hache* : ni liaison ni élision)."""
        return any(l.phone_enrichi.startswith("*h*") for l in self.lectures(forme))

    def _propriete_verbe(self, verbe: str, cle: str):
        for r in self._lignes_lemmes(verbe):
            if r["upos"] in ("VERB", "AUX") and r.get(cle) not in (None, ""):
                return r[cle]
        return None

    def auxiliaire(self, verbe: str) -> str | None:
        """Auxiliaire du verbe : « avoir », « être » ou « avoir,être ». Donné par LeXiK, sinon déduit par règle
        (« être » pour un verbe essentiellement pronominal, « avoir » sinon ; voir ``lemme_info()["auxiliaire_source"]``).
        Un emploi pronominal se conjugue toujours avec « être ». ``None`` si la base n'a pas cette propriété."""
        return self._propriete_verbe(verbe, "auxiliaire")

    def pronominal(self, verbe: str) -> str | None:
        """Emploi pronominal du verbe : « essentiel » (*s'évanouir*), « possible » (*se laver*), ou ``None``."""
        return self._propriete_verbe(verbe, "pronominal")

    def est_pronominal(self, verbe: str) -> bool:
        """Vrai si le verbe a un emploi pronominal (essentiel ou possible)."""
        return self.pronominal(verbe) is not None

    def groupe(self, verbe: str) -> int | None:
        """Groupe du verbe (1, 2 ou 3) selon LeXiK ; ``None`` sinon."""
        g = self._propriete_verbe(verbe, "groupe")
        return int(g) if g is not None else None

    def _conditions_lemme(self, groupe, auxiliaire, pronominal):
        """Conditions SQL sur ``lemmes lm`` ; ``None`` si la base n'a pas la colonne demandée."""
        res = []
        for nom, val in (("groupe", groupe), ("auxiliaire", auxiliaire), ("pronominal", pronominal)):
            if val is None or val is False:
                continue
            if nom not in self._colonnes_lemmes:
                return None
            if nom == "groupe":
                res.append(("lm.groupe = ?", [int(val)]))
            elif nom == "auxiliaire":
                res.append(("(',' || lm.auxiliaire || ',') LIKE ?", [f"%,{val},%"]))
            elif val is True:
                res.append(("lm.pronominal IS NOT NULL", []))
            else:
                res.append(("lm.pronominal = ?", [val]))
        return res

    def lemmes_de(self, forme: str) -> list[str]:
        vus: list[str] = []
        for l in self.lectures(forme):
            if l.id_lemme and l.id_lemme not in vus:
                vus.append(l.id_lemme)
        return vus

    # ── Sons, syllabes, anagrammes, conjugaison ────────────────────────────────

    def _phone_principal(self, forme: str) -> str:
        """Prononciation de la lecture la plus fréquente de la forme (vide si inconnue)."""
        lectures = sorted(self.lectures(forme), key=lambda l: -l.zipf)
        return lectures[0].phone if lectures else ""

    def _lignes_rime(self, prefixe: str, validite_min: str):
        """Formes dont la clé à l'envers commence par ``prefixe``, de la plus fréquente à la moins fréquente. Les fins
        très répandues (ɔ̃, e, ɑ̃ : plus de 5 000 formes, ≈ 0,4 s) sont gardées en mémoire (quelques-unes)."""
        filtre, params = self._sql_validite(validite_min)
        if (prefixe, validite_min) in self._rimes_larges:
            return self._rimes_larges[(prefixe, validite_min)]
        lignes = self._db.execute(
            "SELECT f.id, f.ortho, f.zipf, f.zipf_lemme, f.drapeaux, c.inverse FROM cles_phone c "
            "JOIN phones p ON p.cle = c.id JOIN formes f ON f.id = p.forme "
            f"WHERE c.inverse >= ? AND c.inverse < ?{filtre}{self._visible('p')} ORDER BY f.zipf DESC",
            (prefixe, prefixe + "\U0010ffff", *params)).fetchall()
        if len(lignes) > 5000:
            if len(self._rimes_larges) >= 6:
                self._rimes_larges.pop(next(iter(self._rimes_larges)))
            self._rimes_larges[(prefixe, validite_min)] = lignes
        return lignes

    def _sql_validite(self, validite_min: str) -> tuple[str, tuple]:
        """Condition SQL nécessaire (sur ``f``) pour atteindre ``validite_min`` : écarte tôt les formes trop rares."""
        s = self.seuils
        if validite_min == INCONNUE:
            return "", ()
        hors = f" AND NOT (f.drapeaux & {NON_VALIDE})"     # jetons « Non classé » : jamais au-dessus d'« inconnue »
        if validite_min == PROPOSABLE:
            return " AND f.zipf >= ?" + hors, (s.proposable,)
        if validite_min in (ACCEPTEE, VARIANTE):
            return " AND (f.zipf >= ? OR (f.drapeaux & ? AND f.zipf_lemme >= ?))" + hors, (
                s.acceptee, ACCEPTEE_NOYAU, s.acceptee_lemme)
        return hors, ()

    def _formes_triees(self, lignes, exclue: str, limite: int, validite_min: str, propres: bool = False,
                       locutions: bool = False) -> list[Forme]:
        """Formes des lignes (id, ortho, zipf, zipf_lemme, drapeaux), déjà triées, une par graphie en minuscules ; sans
        ``propres`` ni ``locutions``, ni formes seulement noms propres (Maier) ni formes à espace (de la façon)."""
        res: list[Forme] = []
        vues = {minuscule(exclue)}
        for ligne in lignes:
            mini = minuscule(ligne[1])
            if mini in vues or _RANG[self._niveau(ligne)] < _RANG[validite_min]:
                continue
            if (not propres and ligne[4] & PROPRE_SEUL) or (not locutions and " " in mini):
                continue
            vues.add(mini)
            res.append(self._forme(ligne))
            if len(res) >= limite:
                break
        return res

    def rimes(self, forme: str = "", phone: str = "", n: int = 2, limite: int = 50,
              validite_min: str = PROPOSABLE, propres: bool = False, locutions: bool = False,
              unite: str = "phonemes", qualite: str = "") -> list[Forme]:
        """Formes qui riment avec ``forme`` (sa lecture la plus fréquente) ou avec la prononciation ``phone``, de la
        plus fréquente à la moins fréquente ; chacune porte la qualité de sa rime (``Forme.rime`` : pauvre,
        suffisante, riche — phonèmes finaux communs depuis la dernière voyelle).

        ``unite`` : ``"phonemes"`` (défaut) — mêmes ``n`` derniers phonèmes (``rimes("chanson")`` → façon, garçon :
        sɔ̃) ; ``"syllabes"`` — mêmes ``n`` dernières syllabes, frontières comprises (« pardon », n = 1 : dɔ̃ →
        abandon, mais pas « ardent ») ; taille standard (la mini n'est pas syllabée : on y compare les phonèmes) ;
        ``"voyelle"`` — même fin depuis la dernière voyelle (rime minimale ; ``n`` ignoré : « chanson » → bon, maison,
        ton…). ``qualite`` : qualité minimale (``"suffisante"``, ``"riche"``). Index : clés à l'envers."""
        if unite not in ("phonemes", "syllabes", "voyelle"):
            raise ValueError(f"unité de rime inconnue : {unite}")
        source = phone or self._phone_principal(forme)
        ph = phonemes(cle_phone(source))
        if unite == "voyelle":
            fin = rime_finale(ph)
        elif unite == "syllabes":
            sy = syllabes_de(source)
            if len(sy) < n:
                return []
            fin = phonemes(cle_phone("".join(sy[-n:])))
            cibles_sy = sy[-n:]
        else:
            if len(ph) < n:
                return []
            fin = ph[-n:]
        if not fin:
            return []
        rang_min = {"": 0, "pauvre": 1, "suffisante": 2, "riche": 3}[qualite]
        syllabes = unite == "syllabes" and self._analyses
        prefixe = "".join(reversed(fin))
        lignes = self._lignes_rime(prefixe, validite_min)
        # comparaison sur les clés à l'envers, en chaînes (« ɔ » est un préfixe de « ɔ̃ » : frontière de phonème)
        moi = "".join(reversed(ph))
        fin_moi, long_fin = fin_inverse(moi), len(fin)
        qualites: dict[str, str] = {}
        rangs = {"aucune": 0, "pauvre": 1, "suffisante": 2, "riche": 3}

        def garder(l) -> bool:
            n_commun = commun_inverse(moi, l[5])
            if n_commun < long_fin:
                return False
            q = qualite_commune(n_commun, fin_moi, fin_inverse(l[5]))
            if rangs[q] < rang_min:
                return False
            if syllabes and not any(syllabes_de(p)[-n:] == cibles_sy for (p,) in self._db.execute(
                    "SELECT phone FROM analyses WHERE forme = ? AND masquee = 0", (l[0],))):
                return False
            qualites.setdefault(minuscule(l[1]), q if q != "aucune" else "")
            return True

        res = self._formes_triees((l[:5] for l in lignes if garder(l)), forme, limite, validite_min, propres,
                                  locutions)
        return [replace(f, rime=qualites.get(minuscule(f.ortho), "")) for f in res]

    # ── Recherche multicritère ─────────────────────────────────────────────────

    def rechercher(self, motif: str = "*", son: str = "", syllabes: int | tuple[int, int] | None = None,
                   upos: str | None = None, zipf_min: float = 0.0, zipf_max: float | None = None,
                   rime: str = "", limite: int = 50, validite_min: str = PROPOSABLE, propres: bool = False,
                   locutions: bool = False, accents: bool = True, groupe: int | None = None,
                   auxiliaire: str | None = None, pronominal: str | bool | None = None,
                   h_aspire: bool | None = None) -> list[Forme]:
        """Formes qui satisfont tous les critères, de la plus fréquente à la moins fréquente.

        ``motif`` : graphie à jokers, casse ignorée — ``*`` (toute suite de lettres), ``?`` (une lettre) : « *tion »,
        « ch?t », « re*er » ; ``accents=False`` ignore aussi les accents (« ecole » trouve école). ``son`` : prononciation
        à jokers, ``?`` valant un phonème — « *ɑ̃ », « ʃ* », « *wa* ». ``syllabes`` : nombre exact ou intervalle
        ``(min, max)`` ; ``upos`` : catégorie (NOUN, VERB…) — ces deux critères demandent la taille standard.
        ``zipf_min`` / ``zipf_max`` : fréquence de la forme. ``rime`` : forme avec laquelle rimer (même fin depuis la
        dernière voyelle). Exemple : ``rechercher("*ette", syllabes=2, upos="NOUN")`` → toilette, assiette…

        Propriétés du lemme (table des lemmes ; bases qui les ont) : ``groupe`` (1, 2, 3), ``auxiliaire``
        (« avoir », « être » : le lemme l'admet), ``pronominal`` (« essentiel », « possible », ou ``True`` pour l'un
        ou l'autre), ``h_aspire`` (prononciation de la forme marquée h aspiré)."""
        return self._chercher(None, motif, son, syllabes, upos, zipf_min, zipf_max, rime, limite, validite_min,
                              propres, locutions, accents, groupe, auxiliaire, pronominal, h_aspire)

    def filtrer(self, formes, motif: str = "*", son: str = "", syllabes: int | tuple[int, int] | None = None,
                upos: str | None = None, zipf_min: float = 0.0, zipf_max: float | None = None, rime: str = "",
                validite_min: str = INCONNUE, accents: bool = True, groupe: int | None = None,
                auxiliaire: str | None = None, pronominal: str | bool | None = None,
                h_aspire: bool | None = None) -> list[Forme]:
        """Garde, parmi ``formes`` (graphies ou ``Forme``), celles qui satisfont les critères de ``rechercher``, dans
        l'ordre donné (une graphie absente de la base n'est gardée que sans critère de son, syllabes, catégorie ni
        fréquence)."""
        graphies = [f.ortho if isinstance(f, Forme) else str(f) for f in formes]
        trouvees = {minuscule(f.ortho): f for f in self._chercher(
            graphies, motif, son, syllabes, upos, zipf_min, zipf_max, rime, len(graphies) or 1, validite_min,
            True, True, accents, groupe, auxiliaire, pronominal, h_aspire)}
        return [trouvees[minuscule(g)] for g in graphies if minuscule(g) in trouvees]

    def _chercher(self, graphies, motif, son, syllabes, upos, zipf_min, zipf_max, rime, limite, validite_min,
                  propres, locutions, accents, groupe=None, auxiliaire=None, pronominal=None,
                  h_aspire=None) -> list[Forme]:
        import re

        conditions, params, jointures = [], [], ""
        motif = minuscule(motif or "*")
        if graphies is not None:
            mins = sorted({minuscule(g) for g in graphies})
            if not mins:
                return []
            conditions.append(f"f.min IN ({','.join('?' * len(mins))})")
            params += mins
        if motif != "*":
            conditions.append("f.min GLOB ?")
            params.append(motif.replace("[", "[[]") if accents else _glob_sans_accents(motif))
        if zipf_min > 0:
            conditions.append("f.zipf >= ?")
            params.append(zipf_min)
        if zipf_max is not None:
            conditions.append("f.zipf <= ?")
            params.append(zipf_max)
        par_lemme = groupe is not None or auxiliaire or pronominal or h_aspire is not None
        if (syllabes is not None or upos or par_lemme) and not self._analyses:
            return []
        if par_lemme:
            conditions_l = self._conditions_lemme(groupe, auxiliaire, pronominal)
            if conditions_l is None:
                return []
        if syllabes is not None or upos or par_lemme:
            jointures = " JOIN analyses a ON a.forme = f.id AND a.masquee = 0"
            if par_lemme:
                for cond, val in conditions_l:
                    conditions.append(cond)
                    params.extend(val)
                if conditions_l:
                    jointures += " JOIN lemmes lm ON lm.id = a.lemme"
                if h_aspire is not None:
                    conditions.append("COALESCE(a.phone_enrichi, '') " + ("" if h_aspire else "NOT ") + "LIKE '*h*%'")
            if syllabes is not None:
                lo, hi = (syllabes, syllabes) if isinstance(syllabes, int) else syllabes
                conditions.append("a.syllabes BETWEEN ? AND ?")
                params += [lo, hi]
            if upos:
                codes = [i for i, v in self._codes["upos"].items() if v == upos]
                if not codes:
                    return []
                conditions.append("a.upos = ?")
                params.append(codes[0])
        test_son = None
        if son:
            jointures += " JOIN phones p ON p.forme = f.id JOIN cles_phone c ON c.id = p.cle" + self._visible("p")
            conditions.append("c.cle GLOB ?")
            params.append(cle_phone(son).replace("?", "*"))
            morceaux = []
            for x in phonemes(cle_phone(son)):
                morceaux.append("(?:/[^/]+)*" if x == "*" else "/[^/]+" if x == "?" else "/" + re.escape(x))
            regex = re.compile("".join(morceaux) + "/")
            test_son = lambda cle: regex.fullmatch("/" + "/".join(phonemes(cle)) + "/") is not None
        fin = None
        if rime:
            # rime : préfixe des clés à l'envers (index), vérifié phonème par phonème (ɔ préfixe de ɔ̃)
            fin = list(reversed(rime_finale(phonemes(cle_phone(self._phone_principal(rime) or rime)))))
            if not fin:
                return []
            jointures += " JOIN phones pr ON pr.forme = f.id JOIN cles_phone cr ON cr.id = pr.cle" + self._visible("pr")
            conditions.append("cr.inverse >= ? AND cr.inverse < ?")
            params += ["".join(fin), "".join(fin) + "\U0010ffff"]
        colonnes = ("f.id, f.ortho, f.zipf, f.zipf_lemme, f.drapeaux" + (", c.cle" if son else ", ''")
                    + (", cr.inverse" if rime else ", ''"))
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        # (0.5, comme lexicon-en) à fréquence égale, la graphie en minuscules d'abord : filtrer(["night"]) rend
        # « night » et non « Night »
        tri = ("a.zipf DESC, f.zipf DESC" if upos else "f.zipf DESC") + ", f.ortho != f.min"
        lignes = self._db.execute(f"SELECT {colonnes} FROM formes f{jointures}{where} ORDER BY {tri}", params)

        def garder(l) -> bool:
            return (test_son is None or test_son(l[5])) and (fin is None or phonemes(l[6])[:len(fin)] == fin)

        return self._formes_triees((l[:5] for l in lignes if garder(l)), rime, limite, validite_min, propres,
                                   locutions)

    def contient_son(self, son: str, limite: int = 50, validite_min: str = PROPOSABLE, propres: bool = False,
                     locutions: bool = False) -> list[Forme]:
        """Formes dont la prononciation contient la suite de phonèmes ``son`` (« ʒ », « wa », « ɑ̃t »), de la plus
        fréquente à la moins fréquente."""
        cible = phonemes(cle_phone(son))
        if not cible:
            return []

        def contient(cle: str) -> bool:
            ph = phonemes(cle)
            return any(ph[i : i + len(cible)] == cible for i in range(len(ph) - len(cible) + 1))

        lignes = self._db.execute(
            "SELECT f.id, f.ortho, f.zipf, f.zipf_lemme, f.drapeaux, c.cle FROM cles_phone c "
            "JOIN phones p ON p.cle = c.id JOIN formes f ON f.id = p.forme "
            f"WHERE instr(c.cle, ?) > 0{self._visible('p')} ORDER BY f.zipf DESC", ("".join(cible),))
        return self._formes_triees((l[:5] for l in lignes if contient(l[5])), "", limite, validite_min, propres,
                                   locutions)

    def syllabes(self, forme: str) -> list[str]:
        """Syllabes phonétiques de la lecture la plus fréquente (« ɛt.se.te.ʁa » → ɛt, se, te, ʁa) ; taille
        standard ou complète (la mini n'a pas la syllabation)."""
        if not self._analyses:
            return []
        return [s for s in self._phone_principal(forme).replace("‿", ".").split(".") if s]

    def mots_par_syllabes(self, n: int, upos: str | None = None, limite: int = 50,
                          validite_min: str = PROPOSABLE) -> list[Forme]:
        """Formes d'exactement ``n`` syllabes (lecture non masquée), éventuellement d'une catégorie, de la plus
        fréquente à la moins fréquente ; taille standard ou complète."""
        if not self._analyses:
            return []
        filtre, params = "", [n]
        if upos:
            codes = [i for i, v in self._codes["upos"].items() if v == upos]
            if not codes:
                return []
            filtre, params = " AND a.upos = ?", [n, codes[0]]
        lignes = self._db.execute(
            "SELECT f.id, f.ortho, f.zipf, f.zipf_lemme, f.drapeaux FROM analyses a JOIN formes f ON f.id = a.forme "
            f"WHERE a.syllabes = ? AND a.masquee = 0{filtre} ORDER BY a.zipf DESC", params)
        return self._formes_triees(lignes, "", limite, validite_min)

    def anagrammes(self, forme: str, limite: int = 50, validite_min: str = PROPOSABLE,
                   propres: bool = False) -> list[Forme]:
        """Formes faites des mêmes lettres (accents et casse ignorés) : « aimer » → Marie, maire, ramie… ; taille
        standard ou complète."""
        if not self._analyses or not anagramme(forme):
            return []
        lignes = self._db.execute(
            "SELECT id, ortho, zipf, zipf_lemme, drapeaux FROM formes WHERE anagramme = ? ORDER BY zipf DESC",
            (anagramme(forme),))
        return self._formes_triees(lignes, forme, limite, validite_min, propres, locutions=True)

    def conjuguer(self, verbe: str) -> dict[str, dict[str, dict[str, str]]]:
        """Conjugaison du verbe (lemme ou identifiant ``lemme#VERB``) : {mode: {temps: {personne: forme}}}, codes du
        cadre (UD) — modes Ind, Sub, Cnd, Imp, Inf, Part ; temps Pres, Imp (imparfait), Past (passé simple, participe
        passé), Fut ; personnes « 1s » … « 3p », participes « ms », « fs », « mp », « fp », infinitif « - ». La forme la
        plus fréquente de chaque case, sans graphies variantes ; taille standard ou complète."""
        if not self._analyses:
            return {}
        formes = self.formes_de(verbe)
        if "#" not in verbe:
            poids: dict[str, float] = {}
            for l in formes:
                if l.upos in ("VERB", "AUX"):
                    poids[l.id_lemme] = poids.get(l.id_lemme, 0.0) + l.zipf
            if not poids:
                return {}
            choisi = max(poids, key=poids.get)
            formes = [l for l in formes if l.id_lemme == choisi]
        cases: dict[tuple[str, str, str], Lecture] = {}
        for l in formes:
            t = l.traits()
            forme_verbale = t.get("VerbForm", "")
            if forme_verbale == "Inf":
                mode, temps, personne = "Inf", "Pres", "-"
            elif forme_verbale == "Part":
                mode, temps = "Part", t.get("Tense", "")
                personne = (t.get("Gender", "Masc")[0] + t.get("Number", "Sing")[0]).lower()
            elif "Mood" in t and "Person" in t:
                mode, temps = t["Mood"], t.get("Tense", "Pres")
                personne = t["Person"] + t.get("Number", "Sing")[0].lower()
            else:
                continue
            cle = (mode, temps, personne)
            # (0.5, comme lexicon-en) forme courante d'abord, puis la plus fréquente : une forme que le Wiktionnaire
            # marque (rare, archaïque…) ne passe jamais devant une forme courante de la même case
            if cle not in cases or (not l.marque, l.zipf) > (not cases[cle].marque, cases[cle].zipf):
                cases[cle] = l
        res: dict[str, dict[str, dict[str, str]]] = {}
        for (mode, temps, personne), l in sorted(cases.items()):
            res.setdefault(mode, {}).setdefault(temps, {})[personne] = l.ortho
        return res

    def fermer(self) -> None:
        self._db.close()
