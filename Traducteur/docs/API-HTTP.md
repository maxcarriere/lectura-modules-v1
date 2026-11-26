# Routes `/v1/traduire` de l'API publique de Lectura (proposition)

**Statut : proposition du 25/11/2026, non déployée.** Aucune route `/v1/traduire` n'existe encore sur le serveur ;
les anciennes routes `/translator/…` et `/traduction/…` restent celles des démos. Cette page décrit ce qu'attend le
module Traducteur v1 (`lectura-traducteur` 1.0.0) en mode API. Un serveur de test qui suit cette spécification, en
bibliothèque standard, est fourni avec les tests : `tests/serveur_factice.py`.

Même forme que les autres routes texte de l'API v1 (`POST /v1/lire`) et que les routes `/v1/lexique` de Lexicon v1.
Adresse par défaut : `https://api.lectura.world` (sinon `api=`, `LECTURA_TRADUCTEUR_API` ou `LECTURA_API_URL`) ; le
client ajoute le préfixe `/v1/traduire`. Erreurs côté client : mêmes classes que `lectura-lexicon` et
`lectura-nlp-fr` / `lectura-nlp-en`.

## 1. Traduire un texte

```
POST /v1/traduire
Content-Type: application/json
User-Agent: lectura-traducteur/1.0.0
Authorization: Bearer <clé>            (facultatif ; absent pour l'API publique)

{
  "texte": "She left the bank at 5 p.m.",
  "source": "en",                       "en" ou "fr"
  "cible": "fr",                        "fr" ou "en" (l'autre langue)
  "options": {
    "aligner": false,                   mots et liens mot à mot de chaque phrase
    "formules": true,                   formules protégées et converties (heures, dates, monnaies, mesures…)
    "taille": "base"                    "base" seulement sur l'API publique (sinon 422)
  }
}
```

Réponse 200 :

```json
{"resultat": {
  "texte": "Elle a quitté la banque à 17 h.",
  "phrases": [
    {"source": "She left the bank at 5 p.m.", "debut": 0, "fin": 27,
     "traduction": "Elle a quitté la banque à 17 h.",
     "mots_source": ["She", "left", "the", "bank", "at", "5 p.m."],          (si options.aligner)
     "mots_cible": ["Elle", "a", "quitté", "la", "banque", "à", "17 h", "."],  (si options.aligner)
     "liens": [[0, 0], [1, 2], …]}                                          (si options.aligner)
  ]}}
```

- `debut` et `fin` : positions de la phrase dans `texte` (caractères Unicode, `fin` exclue).
- `liens` : couples `[i, j]` (i : rang du mot source, j : rang du mot cible), triés.
- `texte` : les traductions des phrases jointes par une espace.
- C'est exactement le résultat de `Traducteur.traduire()` en mode local, sérialisé en JSON (les couples deviennent
  des listes de deux entiers ; le client les rend en tuples).
- Champs en trop tolérés par le client ; champs d'options inconnus : 422.

## 2. Aligner deux phrases déjà découpées

```
POST /v1/traduire/aligner
{"mots_source": ["She", "left"], "mots_cible": ["Elle", "est", "partie"], "source": "en", "cible": "fr"}
```

Réponse 200 : `{"resultat": {"liens": [[0, 0], [1, 2]]}}`. Au plus 200 mots de chaque côté (sinon 413), chaque mot
de 200 caractères au plus (sinon 422).

## 3. Glossaire en contexte

```
POST /v1/traduire/gloser
{"texte": "He gave up smoking.", "source": "en"}          (la cible est l'autre langue)
```

Réponse 200 : `{"resultat": {"phrases": [{"source", "traduction", "mots": [<entrée>, …]}]}}`, où chaque entrée est
l'objet `Entree` du glossaire : `forme`, `debut`, `fin` (positions dans `texte`), `lemme`, `upos` (`LOC` pour une
locution), `phone`, `ici` (mots de la traduction qui le rendent), `choix` (`accord`, `glose`, `accord_cat`,
`glose_cat`, `defaut`, `outil`, `formule`, `propre`, `nombre`, `aucun`), `sens` (objet `{glose, traductions,
precision, registre, source, langue_glose}` ou `null`), `autres` (liste de sens, 5 au plus).

## 4. Informations (sans quota)

```
GET /v1/traduire?source=en&cible=fr
```

`{"resultat": {"version": "1.0.0", "paires": ["en-fr", "fr-en"], "tailles": {"en-fr": ["base"], "fr-en": ["base"]},
"aligneur": "precis", "glossaire": true, "limites": {"texte_max": 2000, "glose_max": 1000, "mots_max": 200}}}`

## 5. Unités, tailles maximales et quotas (proposés)

Un seul service, `traduction`, compté en **caractères** du texte reçu, avec un poids selon le calcul demandé (comme
`rechercher` compte 10 requêtes dans le lexique) :

| Appel | Unités décomptées | Maximum par requête |
|---|---|---|
| `POST /v1/traduire` | 1 par caractère de `texte` | 2 000 caractères |
| `POST /v1/traduire` avec `options.aligner` | 2 par caractère | 2 000 caractères |
| `POST /v1/traduire/gloser` | 4 par caractère | 1 000 caractères |
| `POST /v1/traduire/aligner` | 1 par caractère des mots reçus (deux listes) | 200 mots de chaque côté |
| `GET /v1/traduire` | 0 | — |

Quotas par adresse IP et par jour, remis à zéro à minuit UTC ; valeurs en vigueur : `GET /v1` (liste des services,
unités, taille maximale par requête, quota). Ordre de grandeur du calcul : environ 1,5 s pour 1 000 caractères
traduits, environ 1,5 fois plus avec l'alignement, 3 à 4 fois plus pour le glossaire (d'où les poids ci-dessus,
arrondis vers le haut).

## 6. Erreurs

Format commun de l'API v1 : `{"error": <code>, "message": <texte>, "service": "traduction"}`.

| Statut | `error` | Cas | Ce qu'en fait le client |
|---|---|---|---|
| 400 | `requete_invalide` | texte vide, paire inconnue (`source` = `cible`, langue hors fr/en) | `ValueError` |
| 413 | `trop_long` | plus de 2 000 car. (1 000 pour gloser, 200 mots pour aligner) | `ValueError` (le client découpe d'abord, voir §7) |
| 422 | `requete_invalide` | option inconnue, `taille` non servie, type faux | `ValueError` |
| 429 | `quota` | quota de l'IP ou plafond global atteint ; en-tête `Retry-After` | `QuotaDepasse` (`attente`) |
| 503 | `service_ferme`, `occupe`, `indisponible` | interrupteur, file pleine, modèles absents | `ErreurAPI` (avec `statut`) |

Succès : en-têtes `X-Quota-Unite: caracteres`, `X-Quota-Limite`, `X-Quota-Restant`, comme les autres routes v1.

## 7. Comportement du client

- Le client découpe un texte plus long que la limite (2 000 car. ; 1 000 pour gloser) en plusieurs requêtes, après
  une fin de phrase si possible, sinon à une espace ; il recale `debut` et `fin` sur le texte d'origine. Un texte
  vide ne part pas (résultat vide).
- Pas de cache côté client (les traductions sont rarement redemandées telles quelles).
- Délai d'attente : 60 s par requête (`delai=`).
- Le serveur ne garde ni le texte reçu ni la traduction (journal : service, taille, motif d'erreur), comme les
  autres routes v1.
