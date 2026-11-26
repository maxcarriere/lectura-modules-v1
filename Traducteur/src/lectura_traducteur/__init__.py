# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""lectura-traducteur (le Traducteur de Lectura, v1) : traduction français ⇄ anglais.

    from lectura_traducteur import Traducteur

    t = Traducteur("en", "fr")                        # mode auto : local si les modèles sont installés, sinon API
    t.traduire("She left the bank at 5 p.m.")["texte"]   # 'Elle a quitté la banque à 17 h.'
    t.traduire(texte, aligner=True)                   # + mots et liens mot à mot, phrase par phrase
    t.aligner(["She", "left"], ["Elle", "est", "partie"])
    t.gloser("He gave up smoking.")                   # glossaire en contexte
    Traducteur("fr", "en", mode="local")              # rien ne sort de la machine (modèles requis)

**Mode API** : les textes sont envoyés au serveur de Lectura (``https://api.lectura.world``, adresse réglable par
``api=`` ou ``LECTURA_TRADUCTEUR_API``). **Mode local** : modèles installés sur la machine, aucun appel réseau. Le
paquet ne contient aucun modèle.

Code : AGPL-3.0-or-later, ou licence commerciale de Lectura.
"""

__version__ = "1.0.0"

from ._traducteur import MODES, Traducteur, choisir_mode, creer_moteur  # noqa: E402
from .api import ErreurAPI, QuotaDepasse, TraducteurAPI  # noqa: E402
from .modeles import PAIRES, ModelesAbsents  # noqa: E402


def __getattr__(nom: str):
    # TraducteurLocal importe le moteur local à la demande (pas de chargement inutile en mode API)
    if nom == "TraducteurLocal":
        from .local import TraducteurLocal
        return TraducteurLocal
    raise AttributeError(nom)


__all__ = ["Traducteur", "TraducteurAPI", "TraducteurLocal", "creer_moteur", "choisir_mode", "ErreurAPI",
           "QuotaDepasse", "ModelesAbsents", "MODES", "PAIRES", "__version__"]
