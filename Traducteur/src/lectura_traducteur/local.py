# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Mode local : tout est calculé sur la machine, avec les modèles installés. **Aucun appel réseau, jamais** : si un
modèle manque, une erreur ``ModelesAbsents`` le dit, sans repli sur l'API."""
from __future__ import annotations

from dataclasses import asdict

from ._traducteur import Traducteur, verifier_paire
from .opus import MoteurOpus, decouper_phrases
from . import analyseurs


class TraducteurLocal(Traducteur):
    """Traduction par OPUS-MT (CTranslate2 int8), formules protégées, alignement mot à mot et glossaire en contexte,
    en local. ``taille`` : ``base`` ou ``big`` (si installée) ; ``aligneur`` : ``precis`` (mBERT ONNX int8) ou
    ``leger`` (attention d'OPUS-MT, sans modèle de plus) ; ``fils`` : fils de calcul ; ``gpu`` ; ``models_dir`` ;
    ``analyseur`` : Analyseur de la langue source déjà chargé (mode local), pour que le glossaire ne charge pas une
    seconde copie de ses modèles (serveur)."""

    mode = "local"

    def __init__(self, source: str = "en", cible: str = "fr", mode: str | None = None, taille: str = "base",
                 aligneur: str = "precis", fils: int = 4, gpu: bool = False, models_dir=None, api: str | None = None,
                 cle: str | None = None, delai: float | None = None, analyseur=None):
        if api is not None or cle is not None:
            raise ValueError("mode local : pas d'adresse ni de clé d'API (api=, cle= choisissent le mode API)")
        if aligneur not in ("precis", "leger"):
            raise ValueError(f"aligneur « {aligneur} » : precis ou leger")
        self.source, self.cible = verifier_paire(source, cible)
        self.taille = taille
        self.options = dict(fils=fils, gpu=gpu, models_dir=models_dir)
        self.nom_aligneur = aligneur
        self.moteur = MoteurOpus(self.source, self.cible, taille, gpu=gpu, fils=fils, models_dir=models_dir)
        self._aligneur = None
        self._glossaire = None
        self._analyseur_source = analyseur

    @property
    def aligneur(self):
        """Chargé à la demande : ``precis`` (mBERT ONNX int8) ou ``leger`` (attention d'OPUS-MT)."""
        if self._aligneur is None:
            from .aligneur import Aligneur, AligneurMbert
            o = self.options
            self._aligneur = (AligneurMbert(gpu=o["gpu"], fils=o["fils"], models_dir=o["models_dir"])
                              if self.nom_aligneur == "precis"
                              else Aligneur(self.source, self.cible, fils=o["fils"], models_dir=o["models_dir"]))
        return self._aligneur

    def traduire(self, texte: str, aligner: bool = False, formules: bool = True) -> dict:
        phrases = decouper_phrases(texte, self.source)
        for p, t in zip(phrases, self.moteur.traduire_phrases([p.source for p in phrases], formules=formules)):
            p.traduction = t
        sortie = {"texte": " ".join(p.traduction for p in phrases), "phrases": [asdict(p) for p in phrases]}
        if aligner:
            dec_s, dec_c = analyseurs.decouper(self.source), analyseurs.decouper(self.cible)
            for p in sortie["phrases"]:
                ms = [m.forme for ph in dec_s(p["source"]) for m in ph]
                mc = [m.forme for ph in dec_c(p["traduction"]) for m in ph]
                p["mots_source"], p["mots_cible"] = ms, mc
                p["liens"] = sorted(self.aligner(ms, mc))
        return sortie

    def aligner(self, mots_source: list[str], mots_cible: list[str]) -> set[tuple[int, int]]:
        if not mots_source or not mots_cible:
            return set()
        return self.aligneur.aligner([(list(mots_source), list(mots_cible))],
                                     **({"mode": "inter"} if self.nom_aligneur == "precis" else {}))[0]

    def gloser(self, texte: str) -> list[dict]:
        if self._glossaire is None:
            from .glossaire import Glossaire
            self._glossaire = Glossaire(self.source, taille=self.taille, models_dir=self.options["models_dir"],
                                        traducteur=self.moteur, aligneur_obj=self.aligneur,
                                        analyseur=self._analyseur_source)
        sorties = self._glossaire.gloser(texte)
        for ph in sorties:
            ph["mots"] = [asdict(e) for e in ph["mots"]]
        return sorties

    def infos(self) -> dict:
        from . import __version__
        from .modeles import NOMS, dossier_modeles
        d = dossier_modeles(self.options["models_dir"])
        return {"mode": "local", "version": __version__, "source": self.source, "cible": self.cible,
                "taille": self.taille, "aligneur": self.nom_aligneur,
                "tailles": {f"{s}-{c}": [t for t, nom in NOMS[(s, c)].items() if (d / f"{nom}-int8").is_dir()]
                            for (s, c) in NOMS},
                "aligneur_precis": (d / "mbert8" / "mbert8_int8.onnx").is_file(),
                "glossaire": (d / "glossaire.db").is_file()}
