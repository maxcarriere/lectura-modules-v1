# Interface publique de `lectura-nlp-en` 1.0.0 (module NLP-EN v1 de Lingua)

Symétrique de `lectura-nlp-fr` 2.0.0 : mêmes noms, mêmes modes, mêmes erreurs. Version du 25/11/2026.

## 1. Entrée unique

```python
from lectura_nlp_en import creer_moteur

nlp = creer_moteur()                    # mode "auto"
nlp.mode                                # mode effectif : "local", "api" ou "degrade"
nlp.lire("The kids arrived.")           # texte → phrases alignées (orthographe, phonétique, analyse)
nlp.ecrire("ðə ˈkɪdz")                  # phonétique → phrases alignées
nlp.analyser("She left.")               # analyse grammaticale, mot par mot
nlp.decouper("I can't pay $3.50.")      # découpage en phrases et mots (toujours local, sans modèle)
nlp.corriger("He go home.")             # Correcteur : Resultat(texte, corrections) ; explications="fr" | "en"
nlp.lexique.homophones("ðɛɹ")           # Lexicon (lectura-lexicon 1.0.0, langue="en")
nlp.etat()                              # ce qui est chargé : mode, dossiers, base lexicale, Correcteur
```

```python
def creer_moteur(
    mode: str = "auto",                 # "auto" | "local" | "api" | "degrade"
    *,
    models_dir: str | Path | None = None,       # dossier des modèles de l'Analyseur
    api: str | None = None,                     # adresse de l'API (défaut : LECTURA_API_URL, sinon https://api.lectura.world)
    cle: str | None = None,                     # clé facultative (défaut : LECTURA_API_KEY)
    delai: float = 30.0,                        # délai des requêtes, en secondes
    lexique: str | Path | object | bool | None = None,   # base Lexicon (chemin), objet Lexicon, False = sans lexique
    taille_lexique: str | None = None,          # "mini" | "standard" | "complet" (base locale)
    ecriture_lexique: bool | str = "auto",      # élargir l'écriture aux formes de la base Lexicon locale
    correcteur_dir: str | Path | None = None,   # dossier des modèles du Correcteur
    tete_correcteur: str | Path | bool | None = None,    # tête de graphie du Correcteur (False : sans)
    fils: int = 1,                              # fils d'exécution d'onnxruntime (local)
    **options,                                  # options de la chaîne : enchainements, formes_fortes
) -> MoteurNLP
```

Différences avec le français : pas de juge des homophones (l'anglais n'en a pas) ; le Correcteur a une tête de
graphie facultative (`tete_correcteur`) ; options de la chaîne `enchainements` et `formes_fortes` ; un seul objet
`MoteurNLP` pour les quatre modes.

## 2. Les quatre modes

| `mode` | Analyseur (lire, écrire, analyser) | Lexique (`nlp.lexique`) | Correcteur (`nlp.corriger`) | Réseau |
|---|---|---|---|---|
| `"local"` | modèles locaux ; **erreur claire** (`ModelesAbsents`) s'ils manquent | base locale ; sans base : `LexiqueIndisponible` (avertissement) | modèles locaux + base Lexicon locale ; sinon `FonctionIndisponible` | **aucun appel, jamais**, même en repli |
| `"degrade"` | modèles locaux (lexique embarqué compris) **sans base Lexicon** | `LexiqueIndisponible` | `FonctionIndisponible` : il lui faut une base Lexicon | aucun appel |
| `"api"` | `POST /v1/lire`, `/v1/ecrire` | `LexiconAPI` (`POST /v1/lexique/<fonction>?langue=en`) | `POST /v1/corriger` | les textes partent vers l'API |
| `"auto"` | local si les modèles sont présents, **sinon API, avec un avertissement** | base locale si présente, sinon API (avertissement) | local si tout est présent, sinon API (avertissement au premier appel) | seulement en repli annoncé |

## 3. Où sont les modèles (jamais dans le paquet)

| Pièce | Recherche, dans l'ordre |
|---|---|
| Analyseur (`analyseur.onnx`, `selection.onnx`, `modele_mot_*.onnx`, vocabulaires, `lexique.db[.xz]`) | `models_dir`, `LECTURA_NLP_EN_DIR`, `$LECTURA_MODELS_DIR/transducer_en`, `~/.lectura/models/transducer_en` |
| Correcteur (`langue.bin[.xz]`, tête `tete/analyseur.onnx` facultative) | `correcteur_dir`, `LECTURA_CORRECTEUR_EN_DIR`, `$LECTURA_MODELS_DIR/corrector_en`, `~/.lectura/models/corrector_en` |
| Base Lexicon | celle de `lectura-lexicon` : `lexique=`, `LECTURA_LEXICON_EN_DATA`, `$LECTURA_MODELS_DIR/lexicon_en`, `~/.lectura/models/lexicon_en` |

Les fichiers `.xz` sont décompressés une fois dans `~/.lectura/cache` (`LECTURA_CACHE_DIR`).

## 4. Client de l'API, erreurs, lexique indisponible, anciens noms

Comme le français (`lectura-nlp-fr`, `docs/INTERFACE.md` §4 à §6) : `lectura_nlp_en.api.ClientAPI`,
`AnalyseurAPI`, `CorrecteurAPI` ; `QuotaDepasse` (429, attribut `attente`), `ValueError` (400, 404, 413, 422),
`ErreurAPI` (réseau, 5xx) ; `LexiqueIndisponible` rend `Indisponible` (faux, vide) sans exception ; alias d'import
`lectura_transducer_en` → `lectura_nlp_en.analyseur` et `lectura_corrector_en` → `lectura_nlp_en.correcteur`.
