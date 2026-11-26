# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Correcteur du français (module NLP-FR v1 de Lectura) : correcteur orthographique et grammatical pédagogique, sur la
chaîne de l'Analyseur (lecture puis écriture) ; chaque correction est expliquée.

    from lectura_nlp_fr import creer_moteur
    nlp = creer_moteur()
    r = nlp.corriger("Les enfant mange des pomme.", mode="suggestions")      # ou « automatique »
    r.texte                                           # « Les enfants mangent des pommes. »
    for k in r.corrections:                           # debut, fin, original, proposition, type, confiance, explication
        print(k.original, "→", k.proposition, ":", k.explication)

Anciennement ``lectura-corrector`` 0.1.0 (copie figée ; ``import lectura_corrector`` y mène). Dépendances :
``pip install "lectura-nlp-fr[correcteur]"`` (kenlm, onnxruntime, numpy).

Modèles (jamais dans le paquet) : ``langue.bin`` (modèle de langue écrit, livrable en ``langue.bin.xz``, décompressé
une fois dans le cache) et ``analyseur_lot_int8.onnx``, dans l'ordre : ``models_dir``, ``LECTURA_CORRECTEUR_DIR``,
``LECTURA_MODELS_DIR``/corrector, ``~/.lectura/models/corrector``. L'analyseur à porte « correction »
(``analyseur.onnx``, ``analyseur_vocabs.json``) est celui de l'Analyseur, sauf si le dossier du Correcteur en a une copie.

Juge des homophones du Correcteur : **donné explicitement** (``juge_homophones=``, ``LECTURA_JUGE_CORRECTEUR_DIR`` ou
``<dossier du Correcteur>/juge``), jamais emprunté à la chaîne de l'Analyseur : les seuils du Correcteur ont été réglés
avec le juge v2b, l'écriture de l'Analyseur prend le juge v3. Absent, un avertissement le dit.

Lexique : ``lectura-lexicon`` 1.0.0 en mode local (base « standard » de préférence), jamais l'API.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

from ..resultats import Correction, Resultat
from .cache_lexique import LexiqueCache
from .coeur import Correcteur

__all__ = ["Correcteur", "Correction", "Resultat", "charger", "dossier_modeles", "dossier_analyseur",
           "trouver_juge", "EMPREINTE_JUGE_V2B"]

FICHIERS = ("langue.bin",)
ANALYSEUR = ("analyseur.onnx", "analyseur_vocabs.json")
DOSSIER_JUGE = "juge"
# sha256 de ``juge_int8.onnx`` du juge v2b, avec lequel les seuils du Correcteur ont été réglés (18/10/2026).
EMPREINTE_JUGE_V2B = "a6962f1cc4883944681e6d5e65b495707e77ae377cf056fd028cf5cedc88d5c2"


def _present(dossier: Path, nom: str) -> bool:
    return (dossier / nom).exists() or (dossier / f"{nom}.xz").exists()


def dossier_modeles(models_dir: str | Path | None = None) -> Path | None:
    candidats = []
    if models_dir:
        candidats.append(Path(models_dir))
    if os.environ.get("LECTURA_CORRECTEUR_DIR"):
        candidats.append(Path(os.environ["LECTURA_CORRECTEUR_DIR"]))
    if os.environ.get("LECTURA_MODELS_DIR"):
        candidats.append(Path(os.environ["LECTURA_MODELS_DIR"]) / "corrector")
    candidats.append(Path.home() / ".lectura" / "models" / "corrector")
    return next((d for d in candidats if all(_present(d, f) for f in FICHIERS)), None)


def dossier_analyseur(dossier: Path, transducer_dir: str | Path | None = None) -> Path | None:
    """Le graphe à porte du correcteur : copie dans le dossier du correcteur, sinon celui de l'Analyseur."""
    if all((dossier / f).exists() for f in ANALYSEUR):
        return dossier
    from ..analyseur.moteur import dossier_modeles as analyseur

    d = analyseur(transducer_dir)
    return d if d is not None and all((d / f).exists() for f in ANALYSEUR) else None


def trouver_juge(dossier: str | Path | None = None, juge: str | Path | None = None) -> Path | None:
    """Dossier du juge du Correcteur : ``juge``, sinon ``LECTURA_JUGE_CORRECTEUR_DIR``, sinon ``<dossier>/juge``.
    Jamais ``LECTURA_JUGE_DIR`` ni le juge de l'écriture (``~/.lectura/models/juge``)."""
    candidats = [Path(juge)] if juge else []
    if os.environ.get("LECTURA_JUGE_CORRECTEUR_DIR"):
        candidats.append(Path(os.environ["LECTURA_JUGE_CORRECTEUR_DIR"]))
    if dossier is not None:
        candidats.append(Path(dossier) / DOSSIER_JUGE)
    return next((d for d in candidats if (d / "vocab.txt").exists() and (d / "groupes.npz").exists()), None)


def lexique_local(taille: str = "standard"):
    """Lexicon 1.0.0 en mode local (jamais l'API : un appel par mot serait inutilisable) ; base « standard » de
    préférence (celle avec laquelle le Correcteur a été réglé), sinon la plus grande installée, avec un avertissement."""
    from lectura_lexicon import Lexicon

    try:
        return Lexicon(mode="local", taille=taille)
    except FileNotFoundError:
        lexique = Lexicon(mode="local")          # FileNotFoundError si aucune base : message de lectura-lexicon
        from ..erreurs import AvertissementNLP

        warnings.warn(f"Correcteur : base Lexicon « {taille} » absente, base « {lexique.taille} » utilisée à la place "
                      "(réglages faits sur la standard).", AvertissementNLP, stacklevel=3)
        return lexique


def charger(models_dir: str | Path | None = None, transducer_dir: str | Path | None = None,
            lexique=None, fils: int | None = None, chaine=None, **options) -> Correcteur:
    """Assemble le Correcteur : chaîne de l'Analyseur (lecture puis écriture, sans relecture), analyseur à porte de
    correction, lexique ``lectura_lexicon`` (base locale « standard », ou l'objet donné), modèle de langue écrit, juge
    des homophones v2b (``juge_homophones`` : dossier, objet ``JugeHomophones``, ``False`` pour s'en passer ; sinon
    ``trouver_juge``). ``chaine`` : chaîne de l'Analyseur déjà chargée (serveur) : réutilisée telle quelle, et
    l'analyseur partage sa session ONNX si c'est un graphe à porte ; sinon une seconde chaîne est chargée."""
    from ..analyseur.moteur import creer_moteur, fichier

    from .analyseur import AnalyseurCanaux
    from .candidats import Generateur, Juge

    dossier = dossier_modeles(models_dir)
    if dossier is None:
        from ..erreurs import ModelesAbsents

        raise ModelesAbsents("Modèles du Correcteur introuvables (correcteur_dir, LECTURA_CORRECTEUR_DIR, "
                             "$LECTURA_MODELS_DIR/corrector, ~/.lectura/models/corrector). Le paquet ne contient aucun "
                             "modèle : le Correcteur est servi par l'API publique (mode=\"api\") ou livré avec la "
                             "licence commerciale.")
    if fils is None:
        fils = int(os.environ.get("LECTURA_CORRECTEUR_FILS", "1"))
    analyseur_canaux = None
    if chaine is not None and getattr(getattr(chaine, "analyseur", None), "porte", False):
        analyseur_canaux = AnalyseurCanaux.partager(chaine.analyseur, correction=1.0, dossier_lot=dossier, fils=fils)
    if analyseur_canaux is None:
        analyseur = dossier_analyseur(dossier, transducer_dir)
        if analyseur is None:
            from ..erreurs import ModelesAbsents

            raise ModelesAbsents("Analyseur à porte de correction introuvable (dossier du Correcteur ou de l'Analyseur).")
        analyseur_canaux = AnalyseurCanaux(analyseur, correction=1.0, dossier_lot=dossier, fils=fils)
    if chaine is None:
        chaine = creer_moteur("local", models_dir=transducer_dir, relecture=False).chaine
    if lexique is None:
        lexique = lexique_local()
    lexique = LexiqueCache(lexique)
    # Juge des homophones du Correcteur (v2b), donné explicitement : jamais celui de la chaîne (v3 pour l'écriture).
    juge_homophones = options.pop("juge_homophones", None)
    if juge_homophones is None or isinstance(juge_homophones, (str, Path)):
        from .juge_homophones import JugeHomophones

        trouve = trouver_juge(dossier, juge_homophones)
        erreur = None
        try:
            juge_homophones = JugeHomophones.charger(trouve, fils=fils) if trouve is not None else None
        except Exception as e:                # jamais bloquant, mais jamais en silence
            juge_homophones, erreur = None, e
        if juge_homophones is None:
            from ..erreurs import AvertissementNLP

            warnings.warn("Correcteur : juge des homophones introuvable (juge_correcteur=, LECTURA_JUGE_CORRECTEUR_DIR, "
                          f"{dossier / DOSSIER_JUGE}){f' ou illisible ({erreur})' if erreur else ''} : correction des homophones par le seul modèle de langue, "
                          "moins sûre.", AvertissementNLP, stacklevel=3)
        elif juge_homophones.empreinte() != EMPREINTE_JUGE_V2B:
            from ..erreurs import AvertissementNLP

            warnings.warn(f"Correcteur : le juge chargé ({trouve}) n'est pas le juge v2b avec lequel ses seuils ont été "
                          "réglés : résultats non mesurés.", AvertissementNLP, stacklevel=3)
    return Correcteur(chaine, analyseur_canaux, generateur=Generateur(lexique),
                      juge=Juge(fichier(dossier, "langue.bin")), juge_homophones=juge_homophones or None, **options)
