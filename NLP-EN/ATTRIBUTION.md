# Attributions — module `lectura-nlp-en` 1.0.0 (NLP-EN v1)

Le code est sous AGPL-3.0-or-later (`LICENCE.txt`). Ce fichier couvre ce qui n'est pas du code : les tables de règles
livrées dans le paquet (§1), et, par courtoisie, les sources des modèles, qui **ne sont pas dans le paquet** (§2).

## 1. Tables de règles livrées (`lectura_nlp_en/analyseur/data/`) — CC BY-SA 4.0

| Fichier | Contenu | Origine |
|---|---|---|
| `abregements.tsv` | sigles, acronymes, abréviations, unités : développement et prononciation | généré depuis le lexique anglais de Lectura |
| `briques_formules.tsv` | unités, devises, signes des formules et leur lecture | généré depuis LeXiK |
| `formules_phone.tsv` | mots des nombres et des formules, en phonétique | généré depuis LeXiK |
| `correctifs.tsv` | corrections d'analyses et de prononciations (26 lignes) | écrit par Lectura |
| `formes_fortes.tsv` | formes fortes des mots grammaticaux | écrit par Lectura |
| `maths_signes.tsv` | signes mathématiques et leur nature | écrit par Lectura |
| `mots_lexicalises.txt`, `mots_lexicalises_phone.txt` | mots à plusieurs segments à ne pas découper | écrit par Lectura |

Ces tables sont diffusées sous **CC BY-SA 4.0** (https://creativecommons.org/licenses/by-sa/4.0/). Toute
redistribution garde la même licence et les attributions ci-dessous.

### 1.1 Lexique anglais de Lectura (`abregements.tsv`)

Le lexique anglais de Lectura (CC BY-SA 4.0) contient des données des ressources suivantes :

- **English Wiktionary** — Wiktionary contributors, https://en.wiktionary.org — CC BY-SA 4.0 (and GFDL).
  Extracted with **wiktextract** / **kaikki.org** (Tatu Ylonen, *Wiktextract: Wiktionary as Machine-Readable
  Structured Data*, LREC 2022, pp. 1317-1325; https://kaikki.org).
- **CMU Pronouncing Dictionary (CMUdict 0.7b)** — Carnegie Mellon University. Licence notice:
  > Copyright (C) 1993-2015 Carnegie Mellon University. All rights reserved.
  >
  > Redistribution and use in source and binary forms, with or without modification, are permitted provided that
  > the following conditions are met:
  >
  > 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the
  >    following disclaimer. The contents of this file are deemed to be source code.
  >
  > 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the
  >    following disclaimer in the documentation and/or other materials provided with the distribution.
  >
  > This work was supported in part by funding from the Defense Advanced Research Projects Agency, the Office of
  > Naval Research and the National Science Foundation of the United States of America, and by member companies
  > of the Carnegie Mellon Sphinx Speech Consortium. We acknowledge the contributions of many volunteers to the
  > expansion and improvement of this dictionary.
  >
  > THIS SOFTWARE IS PROVIDED BY CARNEGIE MELLON UNIVERSITY ``AS IS'' AND ANY EXPRESSED OR IMPLIED WARRANTIES,
  > INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
  > ARE DISCLAIMED. IN NO EVENT SHALL CARNEGIE MELLON UNIVERSITY NOR ITS EMPLOYEES BE LIABLE FOR ANY DIRECT,
  > INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT
  > OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
  > ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
  > ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
- **wordfreq 3.1.1** — Robyn Speer, *rspeer/wordfreq: v3.0* (v3.0.2), Zenodo, 2022,
  https://doi.org/10.5281/zenodo.7199437 — data CC BY-SA 4.0. wordfreq contains data from Google Books Ngrams
  (http://books.google.com/ngrams), OPUS OpenSubtitles 2018 (attribution to OpenSubtitles,
  http://www.opensubtitles.org/), Wikipedia, NewsCrawl and GlobalVoices, OSCAR, ParaCrawl, Twitter and Reddit word
  counts, and from the **SUBTLEX** word lists created by Marc Brysbaert et al.
  (http://crr.ugent.be/programs-data/subtitle-frequencies) — SUBTLEX is freely available data; credit:
  Brysbaert, M. & New, B. (2009), *Behavior Research Methods* 41(4), 977-990; van Heuven, W. J., Mandera, P.,
  Keuleers, E., & Brysbaert, M. (2014), SUBTLEX-UK, *Quarterly Journal of Experimental Psychology* 67(6),
  1176-1190. Only aggregated frequencies (Zipf values) are used.
- **Universal Dependencies English-EWT** — UD contributors (Silveira et al. 2014) — CC BY-SA 4.0: UD conventions
  for parts of speech, features and lemmas.

### 1.2 LeXiK (`briques_formules.tsv`, `formules_phone.tsv`)

> CARRIERE, Maxime (2026). *LeXiK* — lexique phonétique et grammatical du français. Lectura.
> https://lexique.lectura.world — ORTOLANG, handle 11403/lexik — CC BY-SA 4.0

LeXiK reprend lui-même des données de Lexique 3.83 et 4.10 (B. New, C. Pallier et al., CC BY-SA 4.0), GLAFF 1.2.2
(F. Sajous, N. Hathout, B. Calderone, CLLE-ERSS, CC BY-SA 3.0), du Wiktionnaire (contributeurs du Wiktionnaire,
CC BY-SA 3.0 / 4.0) et d'ipa-dict (dohliam, MIT) : voir la documentation de LeXiK.

## 2. Modèles (non livrés dans ce paquet) — sources d'entraînement, par courtoisie

Les modèles tournent sur le serveur de Lectura ou sont livrés avec la licence commerciale ; ils ne sont pas couverts
par la licence du code et ne figurent pas dans ce paquet.

- **Analyseur** (modèle de phrase et tête de sélection : étiquettes grammaticales, lemmes, dépendances) :
  pré-entraînement sur des phrases de l'encyclopédie Wikipédia en anglais, étiquetées automatiquement, puis affinage
  sur des corpus annotés à la main de Universal Dependencies en anglais (English-EWT, Atis, ESLSpok, CHILDES, CTeTex ;
  CC BY-SA 4.0). Le modèle n'embarque aucune phrase de ces corpus.
- **Modèle de mot et lexique embarqué** : dérivés du lexique anglais de Lectura (§1.1, CC BY-SA 4.0).
- **Tête de graphie du Correcteur** : même modèle de phrase, affiné sur les mêmes sources.
- **Modèle de langue écrit du Correcteur** : entraîné sur des textes publiquement accessibles (encyclopédie,
  dialogues).
- Fréquences lexicales : wordfreq (§1.1) ; seules des statistiques agrégées sont utilisées.

## 3. Lexique

Les fonctions lexicales viennent du paquet `lectura-lexicon` (dépendance), qui a ses propres attributions ; la base
Lexicon de l'anglais dérive du lexique anglais de Lectura et reste sous CC BY-SA 4.0.
