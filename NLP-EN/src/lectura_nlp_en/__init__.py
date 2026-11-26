# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""lectura-nlp-en (module NLP-EN v1 de Lingua) : l'anglais, texte ⇄ phonétique, analyse grammaticale, lexique et
correction. Fonctions : **Analyseur** (base), **Correcteur** (extra ``[correcteur]``), Lexicon (``lectura-lexicon``).
Symétrique de ``lectura-nlp-fr``.

    from lectura_nlp_en import creer_moteur

    nlp = creer_moteur()                                 # "auto" : local si les modèles sont là, sinon API
    nlp.lire("I read the book yesterday.")[0]["phone"]   # 'aɪ ˈɹɛd ðə ˈbʊk ˈjɛs.tɚ.di.'
    nlp.ecrire("ðə ˈkɝ.nəl")[0]["ortho"]                 # 'the colonel'
    nlp.analyser("She left.")                            # [[{'forme': 'She', 'upos': 'PRON', …}, …]]
    nlp.lexique.homophones("ðɛɹ")                        # Lexicon anglais
    nlp.corriger("i dont think he go.").texte            # Correcteur : "I don't think he goes."

**Mode API** (``mode="api"``, ou ``auto`` sans modèles locaux) : les textes, prononciations et mots passés aux
fonctions sont envoyés au serveur de Lectura (``https://api.lectura.world``, adresse réglable par ``api=`` ou
``LECTURA_API_URL`` ; politique de confidentialité : https://www.lectura.world/confidentialite/#api).
**Mode local** (``mode="local"``) : modèles et base sur la machine, aucun appel réseau, jamais. **Mode dégradé**
(``mode="degrade"``) : l'Analyseur sur ses seuls modèles, sans base Lexicon. Le paquet ne contient aucun modèle ni
aucune base : ils sont servis par l'API, ou remis avec la licence commerciale.

Code : AGPL-3.0-or-later, ou licence commerciale de Lectura.
"""

__version__ = "1.0.0"

from ._alias import installer as _installer_alias  # noqa: E402
from .erreurs import AvertissementNLP, ErreurAPI, FonctionIndisponible, ModelesAbsents, QuotaDepasse  # noqa: E402
from .lexique_indisponible import Indisponible, LexiqueIndisponible  # noqa: E402
from .moteur import BRIQUES, FONCTIONS_LEXIQUE, LANGUE, MODES, MoteurNLP, creer_moteur  # noqa: E402
from .correcteur.coeur import Correction, Resultat  # noqa: E402

_installer_alias()

__all__ = [
    "AvertissementNLP", "BRIQUES", "Correction", "ErreurAPI", "FONCTIONS_LEXIQUE", "FonctionIndisponible", "Indisponible", "LANGUE",
    "LexiqueIndisponible", "MODES", "ModelesAbsents", "MoteurNLP", "QuotaDepasse", "Resultat", "creer_moteur", "__version__",
]
