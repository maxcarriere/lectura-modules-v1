# Attributions — module `lectura-nlp-fr` 2.0.0 (NLP-FR v1)

Le code est sous AGPL-3.0-or-later (`LICENCE.txt`). Ce fichier couvre ce qui n'est pas du code : les tables de règles
livrées dans le paquet (§1), et, par courtoisie, les sources des modèles, qui **ne sont pas dans le paquet** (§2).

## 1. Tables de règles livrées (`lectura_nlp_fr/analyseur/data/`) — CC BY-SA 4.0

| Fichier | Contenu | Origine |
|---|---|---|
| `abregements.tsv` | abréviations, sigles, symboles et leur développement | généré depuis LeXiK |
| `briques_formules.tsv` | unités, devises, signes des formules et leur lecture | généré depuis LeXiK |
| `formules_phone.tsv` | mots des nombres et des formules, en phonétique | généré depuis LeXiK |
| `mots_composes_espace.txt` | mots composés à espace (liste fermée) | généré depuis LeXiK |
| `correctifs.tsv` | corrections d'analyses et de prononciations | Lectura, au format de LeXiK, signalées à LeXiK |
| `liaisons_contextes.tsv` | règles de liaison (contextes interdits, obligatoires, facultatifs) | écrit par Lectura |
| `maths_signes.tsv` | signes mathématiques et leur nature | écrit par Lectura |
| `mots_lexicalises.txt`, `mots_lexicalises_phone.txt` | mots à plusieurs segments à ne pas découper | écrit par Lectura |
| `sms.tsv` | abréviations du langage SMS | écrit par Lectura |

Ces tables sont diffusées sous **CC BY-SA 4.0** (https://creativecommons.org/licenses/by-sa/4.0/), avec la mention
de LeXiK :

> CARRIERE, Maxime (2026). *LeXiK* — lexique phonétique et grammatical du français. Lectura.
> https://lexique.lectura.world — ORTOLANG, handle 11403/lexik — CC BY-SA 4.0

LeXiK reprend lui-même des données de Lexique 3.83 et 4.10 (B. New, C. Pallier et al., CC BY-SA 4.0), GLAFF 1.2.2
(F. Sajous, N. Hathout, B. Calderone, CLLE-ERSS, CC BY-SA 3.0), du Wiktionnaire (contributeurs du Wiktionnaire,
CC BY-SA 3.0 / 4.0) et d'ipa-dict (dohliam, MIT) : voir la documentation de LeXiK.

## 2. Modèles (non livrés dans ce paquet) — sources d'entraînement, par courtoisie

Les modèles tournent sur le serveur de Lectura ou sont livrés avec la licence commerciale ; ils ne sont pas couverts
par la licence du code et ne figurent pas dans ce paquet.

- **Analyseur** (étiquettes grammaticales, lemmes, dépendances) : pré-entraînement sur des phrases publiquement
  accessibles (encyclopédie, littérature du domaine public, dialogues), étiquetées automatiquement, puis affinage
  sur des corpus annotés à la main de Universal Dependencies, dont **UD French-Sequoia** (licence LGPL-LR,
  https://github.com/UniversalDependencies/UD_French-Sequoia). Le modèle n'embarque aucune phrase de ces corpus.
- **Modèle de mot, lexique embarqué, index phonétique, supplément d'écriture** : dérivés de LeXiK (CC BY-SA 4.0) ;
  le supplément d'écriture comprend aussi des noms propres de Wikidata (CC0).
- **Juges des homophones** (écriture : v3 ; Correcteur : v2b) et **modèle de langue écrit du Correcteur** :
  entraînés sur des textes publiquement accessibles (encyclopédie, littérature du domaine public, dialogues).
- Fréquences lexicales calculées par Lectura sur des corpus de textes publiquement accessibles ; seules des
  statistiques agrégées sont utilisées.

## 3. Lexique

Les fonctions lexicales viennent du paquet `lectura-lexicon` (dépendance), qui a ses propres attributions ; la base
Lexicon du français dérive de LeXiK et reste sous CC BY-SA 4.0.
