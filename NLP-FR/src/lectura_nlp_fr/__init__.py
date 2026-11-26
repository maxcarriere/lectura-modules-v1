# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""lectura-nlp-fr (module NLP-FR v1 de Lectura) : Analyseur, Correcteur et lexique du français.

    from lectura_nlp_fr import creer_moteur

    nlp = creer_moteur()                         # local si les modèles sont installés, sinon API (avertissement)
    nlp.lire("Les petits enfants sont arrivés.")[0]["phone"]
    nlp.ecrire("le pə.ti.z‿ɑ̃.fɑ̃")[0]["ortho"]
    nlp.analyser("Il mange une pomme.")          # catégorie, traits, lemme, tête et relation de chaque mot
    nlp.corriger("Les enfant mange.").texte      # Correcteur (pip install "lectura-nlp-fr[correcteur]")
    nlp.lexique.homophones("vɛʁ")                # Lexicon (lectura-lexicon)

**Modes** (``creer_moteur(mode=…)``) : ``"local"`` (tout sur la machine, aucun appel réseau, jamais),
``"degrade"`` (l'Analyseur sur ses seuls modèles, sans base Lexicon), ``"api"`` (tout par l'API publique de Lectura :
**les textes sont envoyés au serveur**, https://api.lectura.world, adresse réglable par ``api=`` ou
``LECTURA_API_URL``), ``"auto"`` (local si les modèles sont présents, sinon API, avec un avertissement).

Le paquet ne contient aucun modèle : ils sont servis par l'API ou livrés avec la licence commerciale. Interface
complète : ``docs/INTERFACE.md``.

Code : AGPL-3.0-or-later, ou licence commerciale de Lectura. Tables de règles (``analyseur/data``) : CC BY-SA 4.0
(voir NOTICE).
"""

from __future__ import annotations

__version__ = "2.0.0"

from . import _alias  # noqa: E402

_alias.installer()

from .erreurs import AvertissementNLP, ErreurAPI, FonctionIndisponible, ModelesAbsents, QuotaDepasse  # noqa: E402
from .lexique_indisponible import Indisponible, LexiqueIndisponible  # noqa: E402
from .moteur import (  # noqa: E402
    FONCTIONS_LEXIQUE, LANGUE, MODES, BriqueAbsente, MoteurNLP, MoteurNLPAPI, analyser_phrases, creer_moteur,
)
from .resultats import Correction, Resultat  # noqa: E402

BRIQUES = {"analyseur": "lectura_nlp_fr.analyseur", "lexicon": "lectura_lexicon",
           "correcteur": "lectura_nlp_fr.correcteur"}

__all__ = [
    "AvertissementNLP", "BRIQUES", "BriqueAbsente", "Correction", "ErreurAPI", "FONCTIONS_LEXIQUE",
    "FonctionIndisponible", "Indisponible", "LANGUE", "LexiqueIndisponible", "MODES", "ModelesAbsents", "MoteurNLP",
    "MoteurNLPAPI", "QuotaDepasse", "Resultat", "analyser_phrases", "creer_moteur", "__version__",
]
