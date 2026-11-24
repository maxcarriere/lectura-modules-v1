# Routes `/v1/lexique` de l'API publique de Lectura

Ce qu'attend le module Lexicon v1 (`lectura-lexicon` 1.0.0) en mode API. Un serveur de test qui suit cette
spécification, en bibliothèque standard, est fourni avec les tests : `tests/serveur_factice.py`.

Adresse par défaut : `https://api.lectura.world` ; le client ajoute le préfixe `/v1/lexique`.

## 1. Appel d'une fonction

```
POST /v1/lexique/{fonction}?langue=fr|en
Content-Type: application/json
User-Agent: lectura-lexicon/1.0.0
Authorization: Bearer <clé>            (facultatif ; absent pour l'API publique)

{ "<argument>": <valeur>, … }           arguments nommés de la fonction (objet vide possible)
```

Réponse 200 : `{"resultat": <valeur>}`.

- `langue` : `fr` (défaut) ou `en`. Une langue absente du serveur → 404.
- Le client n'envoie que les arguments donnés par l'utilisateur (plus quelques défauts explicites : `toutes`,
  `avec_lectures`, `forme`/`phone` vides pour `rimes` et `rime`, `motif` pour `rechercher` et `filtrer`). Le
  serveur applique les défauts de la fonction pour les autres.
- Le client garde les réponses en cache (clé : URL + corps JSON trié) ; le serveur peut répondre avec
  `Cache-Control`.

### Sérialisation

- dataclass → objet JSON de **tous** ses champs ; tuple → liste ; `None` → `null`.
- `Forme` : `ortho`, `zipf`, `validite`, `propre`, `special`, `distance`, `lectures` (liste de `Lecture`), `rime`,
  `non_valide`, `britannique`. Le client reconnaît une `Forme` à la présence de `ortho` **et** `validite`.
- `Lecture` : `ortho`, `lemme`, `upos`, `feats`, `phone`, `zipf`, `id_lemme`, `sources` (liste), `confiance`,
  `masquee`, `phone_enrichi`, `multext`, `marque`. Le client la reconnaît à `ortho` **et** `feats`.
- Champs absents tolérés (le client met la valeur par défaut) et champs en trop ignorés.
- `variante` : liste de couples `[Lecture de départ, Lecture cible]` (listes de deux objets).

### Fonctions et arguments

Les noms et arguments sont ceux des fonctions de `Lexicon`. Un argument inconnu → 422 (sauf `variante`,
qui accepte des traits UD libres : `Number`, `Gender`, `Person`, `Tense`, `Mood`, `VerbForm`…).

| Fonction | Arguments (défaut) | `resultat` |
|---|---|---|
| `validite` | `forme` | `"proposable"`, `"acceptee"`, `"variante"`, `"rare"` ou `"inconnue"` |
| `existe`, `est_valide`, `non_valide` | `forme` | booléen |
| `usuelle` | `forme` | texte ou `null` |
| `frequence` | `forme` | nombre (indice Zipf, 0 si inconnue) |
| `forme` | `forme`, `avec_lectures` (true) | `Forme` ou `null` |
| `lectures` | `forme`, `toutes` (false) | liste de `Lecture` |
| `phones` | `forme` | liste de textes |
| `homophones` | `phone`, `neutre` (false), `avec_lectures` (false), `propres` (true), `casse` (`"toutes"`) | liste de `Forme` |
| `voisins_orthographiques` | `forme`, `distance_max` (2), `limite` (20), `validite_min` (`"proposable"`), `propres` (true), `casse` | liste de `Forme` |
| `voisins_phonetiques` | `phone`, `tolerance` (1), `neutre` (true), `limite` (20), `validite_min`, `propres`, `casse` | liste de `Forme` |
| `formes_de` | `lemme`, `upos` (null), `toutes` (false) | liste de `Lecture` |
| `variante` | `forme`, `toutes` (false), traits UD | liste de couples de `Lecture` |
| `lemmes_de` | `forme` | liste d'identifiants `lemme#UPOS` |
| `rimes` (fr) | `forme` (""), `phone` (""), `n` (2), `limite` (50), `validite_min`, `propres` (false), `locutions` (false), `unite` (`"phonemes"`), `qualite` ("") | liste de `Forme` |
| `rimes` (en) | `forme`, `phone`, `n` (null = rime anglaise), `limite`, `validite_min`, `propres`, `locutions` | liste de `Forme` |
| `rechercher` | `motif` (`"*"`), `son`, `syllabes` (entier ou `[min, max]`), `upos`, `zipf_min`, `zipf_max`, `rime`, `limite` (50), `validite_min`, `propres`, `locutions`, `accents` ; en français aussi `groupe`, `auxiliaire`, `pronominal` (valeur ou `true`), `h_aspire` | liste de `Forme` |
| `filtrer` | `formes` (liste de graphies), mêmes critères que `rechercher` sans `limite` | liste de `Forme` |
| `contient_son` | `son`, `limite`, `validite_min`, `propres`, `locutions` | liste de `Forme` |
| `syllabes` | `forme` | liste de textes |
| `mots_par_syllabes` | `n`, `upos`, `limite`, `validite_min` | liste de `Forme` |
| `anagrammes` | `forme`, `limite`, `validite_min`, `propres` | liste de `Forme` |
| `conjuguer` | `verbe` | `{mode: {temps: {personne: forme}}}` |
| `lemme_info` | `lemme` (ou `lemme#UPOS[#n]`, ou une forme) | liste d'objets : `id_lemme`, `lemme`, `upos`, `zipf` ; en français aussi `masculin`, `feminin`, `auxiliaire`, `auxiliaire_source` (`"lexik"` ou `"regle"`), `pronominal`, `groupe`, `ortho_1990`, `h_aspire` (`null` si la base ne le dit pas) |
| `h_aspire` (fr) | `forme` | booléen |
| `auxiliaire` (fr) | `verbe` | `"avoir"`, `"être"`, `"avoir,être"` ou `null` |
| `pronominal` (fr) | `verbe` | `"essentiel"`, `"possible"` ou `null` |
| `est_pronominal` (fr) | `verbe` | booléen |
| `groupe` (fr) | `verbe` | 1, 2, 3 ou `null` |
| `rectifiee` (fr) | `forme` | booléen |
| `autre_genre` (fr) | `lemme` | liste de textes |
| `britannique` (en) | `forme` | booléen |
| `americaine` (en) | `forme` | texte ou `null` |
| `britanniques` (en) | `forme` | liste de textes |
| `rime` (en) | `forme`, `phone` | liste de phonèmes |

L'API sert les bases Lexicon v1 complètes (français et anglais), avec `lemme_info` et, en français, les fonctions
de la table des lemmes (`h_aspire`, `auxiliaire`, `pronominal`, `est_pronominal`, `groupe`) et leurs filtres de
`rechercher` et `filtrer`. La liste
exacte des fonctions servies est donnée par `GET /v1/lexique?langue=…`. Les alias de la v0 (`phone_de`,
`lemme_de`, `info`…) sont calculés par le client à partir de `lectures`, `forme` et `homophones` : aucune route.

## 2. Informations

```
GET /v1/lexique?langue=fr|en
```

Réponse 200 : `{"resultat": {"langue": "fr", "version": "<version du module servi>", "base": {<métadonnées de la
base : taille, version de LeXiK, date de construction…>}, "fonctions": [...], "limites": {"limite_max": 50,
"texte_max": 200, "liste_max": 1000}}}`. Sert à `LexiconAPI.infos()` ; facultatif pour le reste du client.

## 3. Erreurs

Corps : `{"error": "<code>", "message": "<texte>"}` (le client lit aussi `detail`).

| Statut | Cas | Côté client |
|---|---|---|
| 404 | fonction inconnue dans la langue, langue absente | `ValueError` |
| 422 | argument inconnu, valeur invalide ou trop longue (`ValueError`/`TypeError` du moteur) | `ValueError` |
| 405 | `GET /v1/lexique/{fonction}` : les mots ne passent jamais dans l'adresse, seulement en `POST` | `ErreurAPI` |
| 429 | quota du jour atteint ; en-tête `Retry-After` | `QuotaDepasse` |
| 503 | plafond global du jour atteint, ou serveur occupé ; en-tête `Retry-After` | `ErreurAPI` |
| 5xx, réseau, délai (10 s par défaut) | | `ErreurAPI` |

## 4. Limites

- `limite` est ramenée à 50 au plus.
- Textes de 200 caractères au plus ; `formes` de `filtrer` : 1 000 éléments au plus.
- `rechercher` demande au moins une lettre dans `motif`, sauf si `son`, `rime` ou `upos` est donné (pas
  d'extraction en masse du lexique).
- Quota par adresse IP et par jour pour le service « lexique » (une requête = une unité), et plafond global.

## 5. Données personnelles

Le client envoie des mots, motifs et prononciations, toujours dans le corps de la requête, jamais dans l'adresse.
Politique de confidentialité : https://www.lectura.world/confidentialite/#api
