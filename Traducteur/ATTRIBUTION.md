# Attributions — modèles lus par le Traducteur (`lectura-traducteur` 1.0.0)

**Le paquet `lectura-traducteur` ne contient aucun modèle ni aucune donnée.** Son code est sous AGPL-3.0-or-later
(voir `LICENCE.txt`) ou sous licence commerciale de Lectura. En mode local, il lit des modèles installés à part
(remis avec la licence commerciale, ou préparés par l'utilisateur) ; en mode API, ces modèles tournent sur le
serveur de Lectura. Les attributions ci-dessous s'appliquent à ces modèles, pas au code.

## Traduction : OPUS-MT (Helsinki-NLP)

- `opus-mt-en-fr`, `opus-mt-fr-en` (taille `base`) — **Apache License 2.0**.
- `opus-mt-tc-big-en-fr`, `opus-mt-tc-big-fr-en` (taille `big`, facultative) — **CC BY 4.0**
  (https://creativecommons.org/licenses/by/4.0/) : attribution requise pour toute diffusion.
- Jörg Tiedemann et Santhosh Thottingal, « OPUS-MT — Building open translation services for the World »,
  *Proceedings of the 22nd Annual Conference of the European Association for Machine Translation* (EAMT), 2020.
- Lectura les convertit en CTranslate2 (quantification int8), sans autre modification. Les corpus d'entraînement
  sont ceux que décrivent les fiches des modèles publiées par Helsinki-NLP.

## Alignement mot à mot (aligneur « précis »)

- `bert-base-multilingual-cased` (Google) — **Apache License 2.0** ; coupé après la couche 8 et converti en ONNX
  int8 par Lectura.
- Méthode : M. Jalili Sabet, P. Dufter, F. Yvon, H. Schütze, « SimAlign: High Quality Word Alignments without
  Parallel Training Data using Static and Contextualized Embeddings », *Findings of EMNLP* 2020.

## Glossaire en contexte (`glossaire.db`, facultatif)

Base construite par Lectura à partir :

- du **Wiktionnaire** français et du **Wiktionary** anglais (contributeurs des Wiktionnaires ; extraction
  kaikki.org / wiktextract) — CC BY-SA 3.0 / 4.0 ;
- de **WikiLeXiK** (Lectura), lui-même tiré du Wiktionnaire français (traductions anglaises des mots français) —
  CC BY-SA 4.0.

La base est sous **CC BY-SA 4.0** : quiconque la reçoit peut la copier, la modifier et la redistribuer, y compris à des
fins commerciales, en citant ses sources et en gardant la même licence. La licence commerciale du code ne restreint
pas ce droit.

## Analyseurs

Le découpage en phrases, la reconnaissance des formules et l'analyse des mots du glossaire viennent des Analyseurs
de Lectura (`lectura-nlp-fr`, `lectura-nlp-en`), paquets à part, avec leurs propres fichiers de licence.
