# Attributions — bases Lexicon (module `lectura-lexicon` 1.0.0)

**Le paquet `lectura-lexicon` ne contient aucune base ni aucune donnée lexicale.** Ce fichier accompagne le code
parce que le module lit des bases au format rapide : celles que sert l'API publique de Lectura, celles remises avec
la licence commerciale, et celles que l'utilisateur construit lui-même (`python -m lectura_lexicon convertir`).
Les attributions ci-dessous s'appliquent à ces bases, pas au code (AGPL-3.0-or-later, voir `LICENCE.txt`).

Fréquences lexicales calculées par Lectura sur des corpus de textes publiquement accessibles (encyclopédie,
littérature, dialogues) ; seules des statistiques agrégées sont fournies, aucun texte de ces corpus.

## 1. Base Lexicon du français

La base Lexicon du français (toutes tailles) est dérivée de **LeXiK**, lexique phonétique et grammatical du
français :

> CARRIERE, Maxime (2026). *LeXiK* — lexique phonétique et grammatical du français. Lectura.
> https://lexique.lectura.world — ORTOLANG, handle 11403/lexik — CC BY-SA 4.0
> (https://creativecommons.org/licenses/by-sa/4.0/)

Elle est sous la même licence, **CC BY-SA 4.0** : quiconque la reçoit peut la copier, la modifier et la
redistribuer, y compris à des fins commerciales, en citant LeXiK et en gardant la même licence. La licence
commerciale du module ne restreint pas ce droit.

Les graphies variantes du français (fautes courantes et graphies anciennes, avec leur graphie usuelle) viennent de
la base Lexicon 0.5 de Lectura : graphies marquées anciennes ou variantes par le Wiktionnaire (contributeurs du
Wiktionnaire, CC BY-SA, via kaikki.org), graphies concurrentes relevées dans LeXiK et confirmées par Grammalecte,
Lexique 3.83 et Lexique 4, et listes écrites par Lectura. Elles sont diffusées sous CC BY-SA 4.0 avec le reste de la base.

Une base que l'utilisateur construit lui-même avec `convertir` suit la licence de sa source : depuis LeXiK,
CC BY-SA 4.0 avec la citation ci-dessus ; depuis Lexique 3, CC BY-SA 4.0 (B. New, C. Pallier et al.,
http://www.lexique.org) ; depuis GLÀFF, CC BY-SA 3.0 (F. Sajous, N. Hathout, B. Calderone, CLLE-ERSS).

LeXiK est lui-même construit à partir des ressources suivantes, dont il reprend des données :

- **Lexique 3.83 et 4.10** — B. New, C. Pallier et al., http://www.lexique.org — CC BY-SA 4.0.
- **GLAFF 1.2.2** — F. Sajous, N. Hathout, B. Calderone (CLLE-ERSS) — CC BY-SA 3.0.
- **Wiktionnaire** (extraction Kaikki / wiktextract) — contributeurs du Wiktionnaire — CC BY-SA 3.0 / 4.0.
- **ipa-dict** (fr_FR) — Copyright (c) 2016 dohliam — licence MIT :
  > Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
  > documentation files (the "Software"), to deal in the Software without restriction, including without
  > limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the
  > Software, and to permit persons to whom the Software is furnished to do so, subject to the following
  > conditions:
  >
  > The above copyright notice and this permission notice shall be included in all copies or substantial portions
  > of the Software.
  >
  > THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED
  > TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
  > THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
  > CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
  > DEALINGS IN THE SOFTWARE.
- **Lexique français de Grammalecte (liste des formes fléchies), version 7.7** — Olivier R.
  (olivier@grammalecte.net) et contributeurs de Dicollecte, https://grammalecte.net/ — **Mozilla Public License
  2.0**. Notice de la MPL 2.0 (pièce A) :
  > This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0. If a copy of the MPL was not
  > distributed with this file, You can obtain one at https://mozilla.org/MPL/2.0/.

  Forme source de la ressource couverte : `lexique-grammalecte-fr-v7.7.txt`, disponible sur
  https://grammalecte.net/. LeXiK en reprend des données (formes, étiquettes, marques de
  l'orthographe de 1990), mêlées aux autres sources ; aucun fichier de Grammalecte n'est livré tel quel.
- **Wikidata** (lexèmes) — CC0.
- **INSEE**, fichiers des prénoms et des noms — Licence Ouverte 2.0 — « Source : Insee ».
- **GeoNames** — https://www.geonames.org — CC BY 4.0.
- **Google Books Ngram Viewer** (français, v3) — CC BY 3.0.

## 2. Base Lexicon de l'anglais

The English Lexicon database is derived from the **Lectura English lexicon** and is distributed under the
**Creative Commons Attribution-ShareAlike 4.0 International** licence
(https://creativecommons.org/licenses/by-sa/4.0/). Any application that redistributes it must keep this notice
and the attributions below, and keep the data under CC BY-SA 4.0.

It contains data from the following resources:

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
- **English Wikipedia** — Wikipedia contributors — CC BY-SA 4.0: capitalisation counts only.

*Résumé.* La base anglaise est sous CC BY-SA 4.0 ; toute redistribution reprend ces attributions (Wiktionnaire /
kaikki, CMUdict avec sa notice complète, wordfreq et SUBTLEX, UD English-EWT, Wikipédia) et garde la même licence.
