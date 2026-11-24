# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""lectura-lexicon (module Lexicon v1) : fonctions lexicales du français et de l'anglais.

    from lectura_lexicon import Lexicon

    lex = Lexicon()                       # français, par l'API publique de Lectura (mode par défaut)
    lex.homophones("vɛʁ")                 # [Forme(ortho='verre', …), Forme(ortho='vers', …), …]
    Lexicon(langue="en").rimes("nation")  # anglais
    Lexicon("ma_base/lexicon.db")         # mode local : une base au format rapide, rien ne sort de la machine

**Mode API (par défaut)** : les mots, motifs et prononciations passés aux fonctions sont envoyés au serveur de
Lectura (``https://api.lectura.world``, adresse réglable par ``api=`` ou ``LECTURA_LEXICON_API``).
**Mode local** : une base au format rapide (``chemin=``, ``LECTURA_LEXICON_DATA``, ``LECTURA_LEXICON_EN_DATA``),
construite par ``lectura_lexicon.convertir`` depuis un lexique que l'on possède. Le paquet ne contient aucune base.

``Lexique`` est le module Lexique v0 (lectura-lexique 1.6.1) inclus tel quel : lecture de n'importe quel lexique
SQLite, CSV ou TSV, et toutes ses fonctions.

Code : AGPL-3.0-or-later, ou licence commerciale de Lectura. Bases dérivées de LeXiK : CC BY-SA 4.0.
"""

__version__ = "1.0.0"

from ._types import ACCEPTEE, INCONNUE, PROPOSABLE, RARE, VARIANTE, Forme, Lecture, Seuils  # noqa: E402
from ._lexicon import COMMUNES, FONCTIONS, Lexicon, choisir_mode  # noqa: E402
from .api import ErreurAPI, LexiconAPI, QuotaDepasse  # noqa: E402
from .local import LexiconLocal  # noqa: E402
from .conversion import convertir  # noqa: E402
from .v0 import Lexique  # noqa: E402
from .fr.lexicon import trouver_donnees  # noqa: E402  (compatibilité 0.5, français)
from .fr.utilisateur import Dictionnaire  # noqa: E402  (compatibilité 0.5, français)

__all__ = [
    "Lexicon", "LexiconAPI", "LexiconLocal", "Lexique", "Forme", "Lecture", "Seuils", "convertir", "choisir_mode",
    "ErreurAPI", "QuotaDepasse", "FONCTIONS", "COMMUNES", "Dictionnaire", "trouver_donnees",
    "ACCEPTEE", "PROPOSABLE", "RARE", "INCONNUE", "VARIANTE", "__version__",
]
