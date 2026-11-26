# Interface publique de `lectura-nlp-fr` 2.0.0 (module NLP-FR v1 de Lingua)

Document de référence pour les modules v1 voisins (`lectura-nlp-en`, `lectura-traducteur`) : mêmes noms, mêmes modes,
mêmes erreurs. Version du 25/11/2026.

## 1. Entrée unique

```python
from lectura_nlp_fr import creer_moteur

nlp = creer_moteur()                    # mode "auto"
nlp.mode                                # mode effectif : "local", "api" ou "degrade"
nlp.lire("Les enfants sont arrivés.")   # texte → phrases alignées (orthographe, phonétique, analyse)
nlp.ecrire("le.z‿ɑ̃.fɑ̃")                  # phonétique → phrases alignées
nlp.analyser("Il mange.")               # analyse grammaticale, mot par mot
nlp.decouper("Il est 8 h.")             # découpage en phrases et mots (toujours local, sans modèle)
nlp.corriger("Les enfant mange.")       # Correcteur : Resultat(texte, corrections)
nlp.lexique.homophones("vɛʁ")           # Lexicon (lectura-lexicon 1.0.0)
nlp.etat()                              # ce qui est chargé : mode, dossiers, empreintes des juges, base lexicale
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
    ecriture_lexique: bool | str = False,       # élargir l'écriture aux formes de la base Lexicon locale
    correcteur_dir: str | Path | None = None,   # dossier des modèles du Correcteur
    juge_correcteur: str | Path | bool | None = None,    # dossier du juge du Correcteur (False : sans juge)
    **options,                                  # options de la chaîne : e_caduc, schwas_finaux, liaisons,
                                                # enchainements, elisions, juge, poids_juge ;
                                                # ecriture=False : lecture seule (voir §2)
) -> MoteurNLP | MoteurNLPAPI
```

## 2. Les quatre modes

| `mode` | Analyseur (lire, écrire, analyser) | Lexique (`nlp.lexique`) | Correcteur (`nlp.corriger`) | Réseau |
|---|---|---|---|---|
| `"local"` | modèles locaux ; **erreur claire** (`ModelesAbsents`) s'ils manquent | base locale ; sans base : `LexiqueIndisponible` (avertissement) | modèles locaux + base Lexicon locale ; sinon erreur claire | **aucun appel, jamais**, même en repli |
| `"degrade"` | modèles locaux (lexique embarqué compris) **sans base Lexicon** | `LexiqueIndisponible` | indisponible (`FonctionIndisponible`) : il lui faut une base Lexicon | aucun appel |
| `"api"` | `POST /v1/lire`, `/v1/ecrire` | `LexiconAPI` (`POST /v1/lexique/<fonction>`) | `POST /v1/corriger` | les textes partent vers l'API |
| `"auto"` | local si les modèles sont présents, **sinon API, avec un avertissement** | base locale si présente, sinon API (avertissement) | local si tout est présent, sinon API (avertissement) | seulement en repli annoncé |

- Le mode effectif est dans `nlp.mode` ; `nlp.etat()` dit d'où vient chaque pièce.
- **Jamais de juge absent en silence** : si le juge des homophones de l'écriture n'est pas trouvé, un
  `AvertissementNLP` (sous-classe de `UserWarning`) le dit. Même chose pour le juge du Correcteur et pour le
  supplément d'écriture.
- **Lecture seule** : `creer_moteur(..., ecriture=False)` (ou `lectura_nlp_fr.analyseur.creer_moteur(..., ecriture=False)`)
  charge l'Analyseur pour `lire`, `analyser` et `corriger` seulement : ni le juge de l'écriture ni le supplément
  d'écriture ne sont cherchés, donc aucun avertissement à leur sujet ; `ecrire` lève alors `FonctionIndisponible`.
  Sans effet en mode API. Utile à un module qui ne fait que lire (glossaire du Traducteur, par exemple).
- `"decouper"` ne demande aucun modèle : il marche dans tous les modes, sans réseau.

## 3. Où sont les modèles (jamais dans le paquet)

| Pièce | Recherche, dans l'ordre |
|---|---|
| Analyseur (analyseur, modèle de mot, lexique embarqué, index, supplément d'écriture) | `models_dir`, `LECTURA_NLP_FR_DIR`, `$LECTURA_MODELS_DIR/transducer`, `~/.lectura/models/transducer` |
| Juge des homophones de l'écriture (v3) | `LECTURA_JUGE_DIR`, `<dossier de l'Analyseur>/juge`, `$LECTURA_MODELS_DIR/juge`, `~/.lectura/models/juge` |
| Correcteur (`langue.bin[.xz]`, `analyseur_lot_int8.onnx`) | `correcteur_dir`, `LECTURA_CORRECTEUR_DIR`, `$LECTURA_MODELS_DIR/corrector`, `~/.lectura/models/corrector` |
| Juge du Correcteur (v2b, donné explicitement) | `juge_correcteur`, `LECTURA_JUGE_CORRECTEUR_DIR`, `<dossier du Correcteur>/juge` — **jamais** le juge de l'écriture |
| Base Lexicon | celle de `lectura-lexicon` : `lexique=`, `LECTURA_LEXICON_DATA`, `$LECTURA_MODELS_DIR/lexicon`, `~/.lectura/models/lexicon` |

Les fichiers `.xz` sont décompressés une fois dans `~/.lectura/cache` (`LECTURA_CACHE_DIR`).

## 4. Client de l'API

```python
from lectura_nlp_fr.api import ClientAPI, MoteurNLPAPI, ErreurAPI, QuotaDepasse

client = ClientAPI(api=None, cle=None, delai=30.0)
client.appeler("lire", {"texte": "…", "langue": "fr", "options": {}})   # → valeur de "resultat"
```

- Routes : `POST /v1/lire` `{"texte", "langue", "options"}` ; `POST /v1/ecrire` `{"phone", "langue", "options"}` ;
  `POST /v1/corriger` `{"texte", "langue", "mode", "explications"}` ; lexique : `LexiconAPI` de `lectura-lexicon`
  (`POST /v1/lexique/<fonction>?langue=fr`). Réponse : `{"resultat": …}` ; erreur : `{"error", "message"}` (ou
  `{"detail"}`).
- Erreurs, communes avec `lectura-lexicon` (mêmes classes) :
  - `QuotaDepasse` (HTTP 429 ; attribut `attente`, en secondes, depuis `Retry-After`) ;
  - `ValueError` (HTTP 400, 404, 413, 422 : requête refusée, texte trop long…) ;
  - `ErreurAPI` (réseau, délai, HTTP 5xx, réponse illisible ; attribut `statut`).
- En-tête `User-Agent: lectura-nlp-fr/<version>` ; `Authorization: Bearer <clé>` seulement si une clé est donnée.

## 5. Mode dégradé du lexique

`LexiqueIndisponible` répond à toutes les fonctions lexicales par une valeur `Indisponible` : fausse (`bool` faux),
vide (`len` 0, itération vide), dont le texte est « lexique indisponible : installer une base ou autoriser l'API ».
Aucune exception : le code appelant continue. `nlp.lexique.disponible` vaut `False`.

## 6. Compatibilité avec les anciens noms

`import lectura_nlp_fr` installe deux alias d'import : `lectura_transducer` → `lectura_nlp_fr.analyseur` et
`lectura_corrector` → `lectura_nlp_fr.correcteur` (mêmes objets de module, pas de copie). Pour le serveur et les voix,
qui importent `lectura_transducer` sans passer par `lectura_nlp_fr`, deux petits paquets locaux (jamais publiés),
`compat/lectura-transducer` 2.0.0 et `compat/lectura-corrector` 2.0.0, remplacent les anciens et redirigent vers
`lectura-nlp-fr`.
