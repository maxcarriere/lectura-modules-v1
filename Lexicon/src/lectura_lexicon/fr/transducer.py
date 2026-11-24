# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Branchement optionnel de Lexicon sur le Transducer (``lectura_transducer``), sans changer son code.

Le Transducer écrit (phonétique → orthographe) avec son lexique embarqué : mots fréquents et corrections de ses
propres erreurs. Branché, Lexicon élargit l'écriture aux mots rares et aux noms propres :

- ``IndexElargi`` (interface ``IndexPhone``) : l'index embarqué, complété par l'index complet de LeXiK
  (``index_phone.db[.xz]`` à côté de la standard, construit par ``Module/outils/construire_index_phone.py``) pour les clés qu'il ne connaît pas ; seules
  les unités de zipf ≥ ``zipf_min`` sont ajoutées ;
- ``LexiqueElargi`` (interface ``Lexique``) : les graphies du lexique embarqué, complétées par celles de Lexicon
  pour les mêmes prononciations (formes acceptées, ni variantes ni lectures masquées). La lecture
  (orthographe → phonétique) est inchangée.

L'embarqué fait foi pour ce qu'il couvre (décision du 14/10 : les mots fréquents restent au Transducer) : une clé
qu'il connaît n'est pas complétée (« etc » resterait sinon découpé en « êtes cetera »), et Lexicon n'ajoute que
des formes de zipf inférieur au seuil de l'embarqué (``zipf_min`` de ses métadonnées, 2 par défaut) — sans quoi
des analyses de mots fréquents s'ajoutent aux siennes et changent le nombre au hasard (plaques → plaque).

Réglage par défaut, jugé le 15/10 (réglé sur FLEURS dev, jugé une fois sur FLEURS test et dev2) : formes rares
des lemmes fréquents comprises (``lemmes_frequents``) et index complet branché s'il est présent, sans formes
seulement noms propres (``propres`` : Comores → Komor, FIC → Fick, sans gain). WER en phonétique parfaite /
depuis le décodeur : FLEURS test −0,18 / −0,09 pt (59 phrases meilleures, 30 pires), dev2 −0,27 / −0,22 pt
(132 / 36) ; sans lemmes fréquents ni index : −0,03 / 0,00 et 0,00 / +0,01.

    from lectura_lexicon.fr.transducer import brancher
    brancher(moteur.chaine, Lexicon(mode="local", taille="standard").moteur)   # mode local seulement
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .lexicon import _RANG, ACCEPTEE, Lexicon
from .donnees import PROPRE_SEUL, VARIANTE

INDEX = "index_phone.db"   # index complet de LeXiK, livré avec la standard (même version), souvent en .xz


def trouver_index(lexicon: Lexicon) -> Path | None:
    """Index complet : ``LECTURA_LEXICON_INDEX``, sinon à côté de la base de ``lexicon`` (``index_phone.db`` ou
    ``index_phone.db.xz``, décompressé une fois dans le cache par ``lectura_transducer.moteur.fichier``)."""
    import os

    from lectura_transducer.moteur import fichier

    env = os.environ.get("LECTURA_LEXICON_INDEX")
    if env:
        return Path(env)
    dossier = Path(lexicon.chemin).parent
    if (dossier / INDEX).exists() or (dossier / f"{INDEX}.xz").exists():
        return fichier(dossier, INDEX)
    return None


class IndexElargi:
    """``complet`` : index complet de LeXiK (ou ``None``) ; ``dictionnaire`` : mots de l'utilisateur, ajoutés comme
    unités « mot » à leur clé (les caches suivent sa ``version``)."""

    def __init__(self, embarque, complet, zipf_min: float = 0.0, dictionnaire=None):
        self.embarque, self.complet, self.zipf_min, self.dictionnaire = embarque, complet, zipf_min, dictionnaire

    def _version(self) -> int:
        return self.dictionnaire.version if self.dictionnaire is not None else 0

    @lru_cache(maxsize=100_000)
    def _lectures(self, cle: str, version: int = 0) -> dict:
        res = dict(self.embarque.lectures(cle))
        if not res and self.complet is not None:
            for nature, lecture in self.complet.lectures(cle).items():
                if nature not in res and lecture.zipf >= self.zipf_min:
                    res[nature] = lecture
        if "mot" not in res and self.dictionnaire is not None:
            from lectura_transducer.index_phone import Lecture as Unite

            mots = self.dictionnaire.par_cle(cle)
            if mots:
                res["mot"] = Unite("mot", cle, max(m.zipf for m in mots))
        return res

    def lectures(self, cle: str) -> dict:
        return dict(self._lectures(cle, self._version()))

    def composes(self, cle: str) -> list:
        if self.embarque.lectures(cle) or self.complet is None:
            return list(self.embarque.composes(cle))
        return [c for c in self.complet.composes(cle) if c.zipf >= self.zipf_min]

    def prononciations(self, cle: str, neutre: bool = False) -> list[str]:
        res = list(self.embarque.prononciations(cle, neutre))
        if not res and self.complet is not None:
            res = list(self.complet.prononciations(cle, neutre))
        if not res and self.dictionnaire is not None:
            from .cles import syllabes_de

            res = list(dict.fromkeys(".".join(syllabes_de(m.phone)) for m in self.dictionnaire.par_cle(cle)))
        return res


class LexiqueElargi:
    def __init__(self, embarque, lexicon: Lexicon, zipf_min: float = 0.0, propres: bool = False,
                 lemmes_frequents: bool = True):
        from lectura_transducer.analyse import Entree

        self._Entree = Entree
        self.embarque, self.lexicon, self.zipf_min, self.propres = embarque, lexicon, zipf_min, propres
        self.zipf_embarque = _seuil_embarque(embarque)
        # sans lemmes fréquents : seulement les formes dont le lemme est lui aussi sous le seuil de l'embarqué
        self.zipf_lemme_max = float("inf") if lemmes_frequents else self.zipf_embarque

    def lectures(self, forme: str) -> list:
        """Lectures de l'embarqué ; pour une forme qu'il ne connaît pas, celles du dictionnaire de l'utilisateur
        (prononciation donnée, alignée sur la graphie par l'embarqué)."""
        res = self.embarque.lectures(forme)
        d = self.lexicon.dictionnaire
        if res or d is None or not len(d):
            return res
        from .cles import minuscule

        # casse comme ``Lexicon.validite`` : graphie exacte, minuscules en début de phrase, toutes en capitales
        mots = [m for m in d.lectures_min(minuscule(forme)) if m.phone and (
            m.ortho in (forme, minuscule(forme)) or (forme.isupper() and len(forme) > 1))]
        entrees = [self._Entree(m.ortho, m.categorie(), {}, m.lemme or m.ortho, m.phone, (), m.zipf,
                                origine="utilisateur") for m in mots]
        return [self.aligner(e) or e for e in entrees]

    def graphies(self, phones: list[str]) -> list:
        res = list(self.embarque.graphies(phones))
        vues = {(e.ortho, e.upos, e.lemme, tuple(sorted(e.feats.items()))) for e in res}
        for phone in phones:
            for e in self._graphies(phone) + self._graphies_utilisateur(phone):
                cle = (e.ortho, e.upos, e.lemme, tuple(sorted(e.feats.items())))
                if cle not in vues:
                    vues.add(cle)
                    res.append(e)
        return res

    @lru_cache(maxsize=100_000)
    def _graphies(self, phone: str) -> tuple:
        lex, res = self.lexicon, []
        c = lex._codes
        lignes = lex._db.execute(
            "SELECT f.ortho, f.zipf, f.zipf_lemme, f.drapeaux, l.lemme, a.upos, a.traits, a.zipf, a.phone_enrichi "
            "FROM analyses a JOIN formes f ON f.id = a.forme JOIN lemmes l ON l.id = a.lemme "
            "WHERE a.phone = ? AND a.masquee = 0", (phone,))
        for ortho, zipf, zl, dr, lemme, u, t, za, pe in lignes:
            if dr & VARIANTE or (dr & PROPRE_SEUL and not self.propres) or not self.zipf_min <= zipf < self.zipf_embarque \
                    or (zl or 0) >= self.zipf_lemme_max:
                continue
            if _RANG[lex._niveau((0, ortho, zipf, zl, dr))] < _RANG[ACCEPTEE]:
                continue
            feats = dict(x.split("=", 1) for x in c["traits"][t].split("|") if "=" in x)
            # Même fréquence que le lexique embarqué : zipf de l'analyse, sinon dixième du zipf de la forme.
            res.append(self._Entree(ortho, c["upos"][u], feats, lemme or ortho, pe or phone, (), za or zipf / 10,
                                    origine="lexicon"))
        return tuple(res)

    def _graphies_utilisateur(self, phone: str) -> tuple:
        """Mots du dictionnaire de l'utilisateur de cette prononciation (zipf du mot, à l'égal de l'embarqué)."""
        d = self.lexicon.dictionnaire
        if d is None or not len(d):
            return ()
        from .cles import cle_phone

        return tuple(self._Entree(m.ortho, m.categorie(), {}, m.lemme or m.ortho, phone, (), m.zipf,
                                  origine="utilisateur") for m in d.par_cle(cle_phone(phone)))

    def aligner(self, entree):
        return self.embarque.aligner(entree)


def _seuil_embarque(embarque, defaut: float = 2.0) -> float:
    """Zipf minimal des mots du lexique embarqué (métadonnée ``zipf_min`` de ``lexique.db``)."""
    try:
        return float(dict(embarque._base.execute("SELECT cle, valeur FROM metadonnees")).get("zipf_min", defaut))
    except Exception:
        return defaut


def brancher(chaine, lexicon: Lexicon, index_complet: str | Path | None = "auto", zipf_min: float = 0.0,
             propres: bool = False, lemmes_frequents: bool = True) -> None:
    """Remplace le lexique de la chaîne par sa version élargie (l'embarqué reste prioritaire). ``index_complet`` :
    chemin de l'index complet, ``"auto"`` (défaut : ``trouver_index``, branché s'il est trouvé) ou ``None``."""
    from lectura_transducer.index_phone import IndexSqlite

    if index_complet == "auto":
        index_complet = trouver_index(lexicon)

    chaine.lexique = LexiqueElargi(chaine.lexique, lexicon, zipf_min, propres, lemmes_frequents)
    # l'index suit le dictionnaire de ``lexicon`` (créé vide s'il manque, pour que ``lexicon.ajouter`` y écrive)
    if lexicon.dictionnaire is None:
        from .utilisateur import Dictionnaire

        lexicon.dictionnaire = Dictionnaire()
    chaine.index = IndexElargi(chaine.index, IndexSqlite(index_complet) if index_complet is not None else None,
                               zipf_min, lexicon.dictionnaire)
