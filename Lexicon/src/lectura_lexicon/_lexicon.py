# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""``Lexicon`` : une seule entrée pour le français et l'anglais, en mode API (par défaut) ou local.

    from lectura_lexicon import Lexicon

    lex = Lexicon()                          # français, API publique de Lectura (les mots partent vers le serveur)
    lex = Lexicon(langue="en")               # anglais, API publique
    lex = Lexicon("ma_base/lexicon.db")      # français, base locale au format rapide (rien ne sort de la machine)
    lex = Lexicon(mode="local")              # base locale trouvée par LECTURA_LEXICON_DATA ou ~/.lectura/models

Choix du mode (``mode=None``) : local si ``chemin`` ou ``taille`` est donné, si la variable de la langue
(``LECTURA_LEXICON_DATA`` en français, ``LECTURA_LEXICON_EN_DATA`` en anglais) est posée, ou si une base est installée
dans ``~/.lectura/models/lexicon[_en]`` (``LECTURA_MODELS_DIR``) ; sinon API. ``LECTURA_LEXICON_MODE`` (``api`` ou
``local``) force le mode.
"""

from __future__ import annotations

import os
from pathlib import Path

from ._types import LANGUES, Forme, Lecture, Seuils

# Fonctions lexicales de chaque langue (mêmes noms en mode local et en mode API)
COMMUNES = (
    "validite", "existe", "est_valide", "non_valide", "usuelle", "frequence", "forme", "lectures", "phones",
    "homophones", "voisins_orthographiques", "voisins_phonetiques", "formes_de", "variante", "lemmes_de", "rimes",
    "rechercher", "filtrer", "contient_son", "syllabes", "mots_par_syllabes", "anagrammes", "conjuguer",
    "lemme_info",
)
PROPRES = {"fr": ("rectifiee", "autre_genre", "h_aspire", "auxiliaire", "pronominal", "est_pronominal", "groupe"),
           "en": ("britannique", "americaine", "britanniques", "rime")}
FONCTIONS = {langue: COMMUNES + PROPRES[langue] for langue in LANGUES}
MODES = ("api", "local")

_VARIABLES = {"fr": "LECTURA_LEXICON_DATA", "en": "LECTURA_LEXICON_EN_DATA"}
_DOSSIERS = {"fr": "lexicon", "en": "lexicon_en"}

# Catégories de la v0 (Lexique 3) pour ``info`` : UPOS → cgram
_CGRAM = {"NOUN": "NOM", "PROPN": "NOM", "VERB": "VER", "AUX": "AUX", "ADJ": "ADJ", "ADV": "ADV", "ADP": "PRE",
          "CCONJ": "CON", "SCONJ": "CON", "DET": "ART", "PRON": "PRO", "INTJ": "ONO", "NUM": "ADJ:num"}


def _langue(langue: str) -> str:
    langue = (langue or "fr").lower()
    if langue not in LANGUES:
        raise ValueError(f"langue « {langue} » : attendu {', '.join(LANGUES)}")
    return langue


def _base_locale_presente(langue: str) -> bool:
    if os.environ.get(_VARIABLES[langue]):
        return True
    dossiers = [Path.home() / ".lectura" / "models" / _DOSSIERS[langue]]
    if os.environ.get("LECTURA_MODELS_DIR"):
        dossiers.insert(0, Path(os.environ["LECTURA_MODELS_DIR"]) / _DOSSIERS[langue])
    return any((d / t / f).exists() for d in dossiers for t in ("complet", "standard", "mini")
               for f in ("lexicon.db", "lexicon.tsv.xz"))


def choisir_mode(langue: str = "fr", chemin=None, mode: str | None = None, taille: str | None = None) -> str:
    """Mode retenu pour ces arguments (voir le module)."""
    mode = mode or os.environ.get("LECTURA_LEXICON_MODE") or None
    if mode is not None:
        if mode not in MODES:
            raise ValueError(f"mode « {mode} » : attendu {', '.join(MODES)}")
        return mode
    if chemin is not None or taille is not None or _base_locale_presente(_langue(langue)):
        return "local"
    return "api"


class Lexicon:
    """Fonctions lexicales du français ou de l'anglais.

    ``Lexicon(chemin=None, langue="fr", taille=None, mode=None, api=None, cle=None, delai=10.0, seuils=None,
    dictionnaire=None)`` rend un ``LexiconLocal`` ou un ``LexiconAPI`` (sous-classes de ``Lexicon``) :

    - ``chemin`` : base au format rapide (``lexicon.db``, dossier qui en contient, ou ``lexicon.tsv.xz``) → mode local ;
    - ``taille`` : en mode local, taille cherchée dans un dossier (``mini``, ``standard``, ``complet``) ;
    - ``api`` / ``cle`` / ``delai`` : en mode API, adresse du serveur (``LECTURA_LEXICON_API``), clé facultative
      (``LECTURA_API_KEY``), délai en secondes ;
    - ``seuils`` / ``dictionnaire`` : en mode local, seuils de validité et mots de l'utilisateur.
    """

    langue: str = "fr"
    mode: str = ""

    def __new__(cls, chemin=None, langue: str = "fr", *args, **kwargs):
        if cls is Lexicon:
            choisi = choisir_mode(langue, chemin, kwargs.get("mode"), kwargs.get("taille"))
            from .local import LexiconLocal
            from .api import LexiconAPI
            cls = LexiconLocal if choisi == "local" else LexiconAPI
        return super().__new__(cls)

    def fonctions(self) -> tuple[str, ...]:
        """Fonctions lexicales disponibles dans cette langue."""
        return FONCTIONS[self.langue]

    # ── Alias de compatibilité avec lectura-lexique (v0) ───────────────────────
    # Mêmes noms que la v0 ; ils s'appuient sur les fonctions de Lexicon et marchent donc dans les deux modes.
    # Les fonctions v0 qui portent déjà un nom de Lexicon (existe, homophones, rimes, conjuguer…) gardent la
    # sémantique de Lexicon : voir le tableau de correspondance de la documentation. Pour retrouver exactement la v0
    # sur un fichier quelconque (SQLite, CSV, TSV), ``lectura_lexicon.Lexique`` est la v0 complète, incluse.

    def phone_de(self, mot: str) -> str | None:
        """(v0) Prononciation la plus fréquente de ``mot``, ou ``None``."""
        lectures = sorted(self.lectures(mot), key=lambda l: -l.zipf)
        return next((l.phone for l in lectures if l.phone), None)

    def lemme_de(self, mot: str) -> str | None:
        """(v0) Lemme le plus fréquent de ``mot`` (sans l'identifiant ``#UPOS``), ou ``None``."""
        poids: dict[str, float] = {}
        for l in self.lectures(mot):
            if l.lemme:
                poids[l.lemme] = poids.get(l.lemme, 0.0) + max(l.zipf, 0.0) + 1e-9
        return max(poids, key=poids.get) if poids else None

    def info(self, mot: str) -> list[dict]:
        """(v0) Entrées de ``mot`` sous forme de dictionnaires : ortho, lemme, cgram (catégorie de la v0), upos, genre,
        nombre, mode, temps, personne, phone, freq (par million), zipf, multext."""
        res = []
        for l in self.lectures(mot):
            t = l.traits()
            res.append({
                "ortho": l.ortho, "lemme": l.lemme, "cgram": _CGRAM.get(l.upos, l.upos), "upos": l.upos,
                "genre": {"Masc": "m", "Fem": "f"}.get(t.get("Gender", ""), ""),
                "nombre": {"Sing": "s", "Plur": "p"}.get(t.get("Number", ""), ""),
                "mode": t.get("Mood", t.get("VerbForm", "") if t.get("VerbForm") in ("Inf", "Part") else ""),
                "temps": t.get("Tense", ""), "personne": t.get("Person", ""), "phone": l.phone,
                "freq": round(10 ** (l.zipf - 3), 4) if l.zipf > 0 else 0.0, "zipf": l.zipf, "multext": l.multext,
                "id_lemme": l.id_lemme, "feats": l.feats,
            })
        return res

    def rimes_par_suffixe(self, suffixe: str, limite: int = 50) -> list[Forme]:
        """(v0) Formes dont la prononciation se termine par ``suffixe`` (phonèmes)."""
        return self.rechercher(son="*" + suffixe, limite=limite)

    def existe_nom_propre(self, mot: str) -> bool:
        """(v0) Vrai si ``mot`` a une lecture de nom propre."""
        return any(l.upos == "PROPN" for l in self.lectures(mot)) or bool(
            (f := self.forme(mot, avec_lectures=False)) and f.propre)

    def phone_nom_propre(self, mot: str) -> str | None:
        """(v0) Prononciation de ``mot`` comme nom propre (sinon sa prononciation la plus fréquente)."""
        propres = [l.phone for l in self.lectures(mot) if l.upos == "PROPN" and l.phone]
        return propres[0] if propres else self.phone_de(mot)

    def homophones_nom_propre(self, phone: str) -> list[Forme]:
        """(v0) Noms propres qui se prononcent ``phone``."""
        return [f for f in self.homophones(phone) if f.propre]

    @staticmethod
    def decoder_multext(tag: str) -> dict[str, str]:
        """(v0) Étiquette MULTEXT (français) → traits lisibles (catégorie, mode, temps, personne…)."""
        from .v0._multext import decoder_multext

        return decoder_multext(tag)

    # ── Fermeture ──────────────────────────────────────────────────────────────

    def fermer(self) -> None:  # redéfinie par les sous-classes
        pass

    def close(self) -> None:
        """(v0) Synonyme de ``fermer``."""
        self.fermer()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.fermer()


__all__ = ["Lexicon", "COMMUNES", "FONCTIONS", "PROPRES", "choisir_mode", "Forme", "Lecture", "Seuils"]
