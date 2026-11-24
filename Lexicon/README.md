# lectura-lexicon — le module Lexicon (v1)

Génération v1 (2026) de Lectura — https://www.lectura.world/developpement/modules/

French and English lexical functions — word validity, frequency, pronunciations, homophones, spelling and
phonetic neighbours, rhymes, anagrams, inflections and conjugation, multi-criteria search — through the Lectura public API
(default) or a local database. **No database is included in this package.**

*Fonctions lexicales du français et de l'anglais : validité d'un mot, fréquence, prononciations, homophones,
voisins orthographiques et phonétiques, rimes, anagrammes, formes fléchies et conjugaison, recherche multicritère. Par l'API
publique de Lectura (par défaut) ou sur une base locale. Le paquet ne contient aucune base.*

## Installation

```bash
pip install lectura-lexicon
```

Python 3.10 ou plus, aucune dépendance.

## Vos données partent vers l'API de Lectura (mode par défaut)

Sans base locale, **les mots, motifs et prononciations que vous passez aux fonctions sont envoyés au serveur de
Lectura** (`https://api.lectura.world`), qui calcule la réponse. L'API publique est gratuite, sans clé, avec un
usage limité. Politique de confidentialité : https://www.lectura.world/confidentialite/#api

- Changer d'adresse (votre propre serveur) : `Lexicon(api="https://…")` ou la variable `LECTURA_LEXICON_API`.
- Ne rien envoyer : passer en **mode local** (ci-dessous), `Lexicon(mode="local")` ou `LECTURA_LEXICON_MODE=local`.

## Usage

```python
from lectura_lexicon import Lexicon

lex = Lexicon()                          # français, par l'API publique
lex.existe("maison")                     # True
lex.frequence("maison")                  # indice Zipf
[f.ortho for f in lex.homophones("vɛʁ")] # vers, verre, vert… du plus fréquent au moins fréquent
[f.ortho for f in lex.rimes("chanson")]  # mots qui finissent en sɔ̃
lex.conjuguer("aller")["Ind"]["Pres"]    # {'1s': 'vais', '2s': 'vas', '3s': 'va', …}
lex.rechercher("*ette", syllabes=2, upos="NOUN", limite=5)

en = Lexicon(langue="en")                # anglais
en.americaine("colour")                  # 'color'
[f.ortho for f in en.rimes("nation")]    # station, relation…
```

Les résultats sont les mêmes types en mode API et en mode local : `Forme` (graphie, zipf, validité, drapeaux) et
`Lecture` (lemme, UPOS, traits UD, prononciation en alphabet phonétique international (API), MULTEXT en français).

## Mode local : votre base, rien ne sort de la machine

```python
lex = Lexicon("chemin/vers/lexicon.db")             # ou LECTURA_LEXICON_DATA (français), LECTURA_LEXICON_EN_DATA
```

Le mode local est choisi d'office si `chemin=` est donné, si la variable de la langue est posée ou si une base est
installée dans `~/.lectura/models/lexicon` (`lexicon_en` pour l'anglais). Sans base, une erreur claire dit quoi
faire.

### Les bases Lexicon

Une base Lexicon ne contient que ce qui ne se calcule pas : la graphie et sa fréquence, la prononciation (alphabet
phonétique international), le lemme, l'analyse (catégorie et traits grammaticaux) et la fréquence de chaque
analyse ; la table des lemmes (fréquence du lemme, autre genre, auxiliaire, pronominal, groupe, orthographe de
1990) ; les formes spéciales (abréviations, symboles…) ; les variantes avec leur graphie usuelle (variantes :
français, fautes courantes et graphies anciennes, *parmis* → *parmi* ; et anglais, *seperate* → *separate*) ; en
anglais, les graphies britanniques et américaines.
Les index (voisins, rimes, syllabes, anagrammes, paradigmes…) ne sont jamais livrés : ils se construisent sur
votre machine, une fois (commande `indexer`, ou d'office au premier usage d'une base nue). Seules les formes
validées sont reprises.

Trois tailles, définies par la fréquence de la forme (indice Zipf) :

| Base | Contenu | Usage | Formes FR / EN | Livrée (xz) FR / EN | Indexée FR / EN |
|---|---|---|---:|---:|---:|
| complète | toutes les formes validées | serveur, recherche | 2 365 529 / 390 537 | 43,8 / 10,7 Mo | 880 / 185 Mo |
| standard | les formes de fréquence > 0 | correcteurs | 610 415 / 228 835 | 16,6 / 6,3 Mo | 314 / 120 Mo |
| mini | les formes de zipf ≥ 2 | mobile, applis grand public | 121 784 / 104 115 | 3,9 / 3,3 Mo | 73 / 64 Mo |

La mini perd surtout des conjugaisons rares et du vocabulaire technique. L'indexation prend de 30 s (mini) à
5 min (complète française), avec environ 0,5 Go de mémoire au plus.

```bash
python -m lectura_lexicon installer lexicon-fr-standard.db.xz [--sha256 <empreinte>]
# décompresse, construit les index, installe dans ~/.lectura/models/lexicon/standard/ (lexicon_en en anglais)
```

`Lexicon("lexicon-fr-standard.db")` indexe aussi une base nue de lui-même au premier usage (cache
`~/.lectura/cache/lexicon`).

Deux façons d'obtenir une base :

1. **La construire** depuis un lexique que vous possédez :

   ```bash
   python -m lectura_lexicon convertir LeXiK/ lexicon.db [--taille standard|mini]   # LeXiK téléchargée
   python -m lectura_lexicon convertir Lexique383.tsv l3.db                          # Lexique 3
   python -m lectura_lexicon convertir glaff-1.2.2.txt glaff.db                      # GLÀFF
   python -m lectura_lexicon convertir mon_lexique.csv base.db [--langue en]         # CSV/TSV maison
   python -m lectura_lexicon denuder lexicon.db nue.db [--taille standard|mini]      # base nue, à livrer
   # (ajouter --complements variantes pour garder les variantes et leur graphie usuelle)
   ```

   LeXiK se télécharge sur https://lexique.lectura.world et sur ORTOLANG (handle 11403/lexik). La conversion de
   LeXiK complète prend environ 5 minutes et 0,5 Go de mémoire, et demande 2 à 3 Go de disque temporaire.

2. **La recevoir** avec la licence commerciale (bases Lexicon prêtes à l'emploi, français et anglais).

## Compatibilité avec Lexique v0 (`lectura-lexique`)

- `lectura_lexicon.Lexique` est le module Lexique v0 (1.6.1) inclus tel quel : il lit n'importe quel lexique
  SQLite, CSV ou TSV, avec toutes ses fonctions (sens, entités, catégories pour les bases qui les ont, export).
- `Lexicon` porte aussi les noms de la v0 : `phone_de`, `lemme_de`, `info`, `rimes_par_suffixe`,
  `existe_nom_propre`, `phone_nom_propre`, `homophones_nom_propre`, `decoder_multext`, `close`, `with`.
- Différences : `frequence` rend un indice Zipf (la v0 rendait une fréquence par million : `info()["freq"]`) ;
  `homophones`, `rimes`, `rechercher`… rendent des `Forme` (la v0 rendait des dictionnaires) ; `conjuguer` utilise
  les codes UD (`Ind`, `Pres`, `1s`).

Le paquet `lectura-lexique` (v0) reste disponible, inchangé.

## Licence

- **Code** : AGPL-3.0-or-later (`LICENCE.txt`), ou licence commerciale de Lectura pour l'intégrer dans un produit
  fermé. Licence commerciale du module Lexicon v1, avec les bases Lexicon prêtes à l'emploi : 290 € HT (indicatif, sur demande), TVA non applicable, art. 293 B du CGI ; base sur
  mesure (métier, éducative, autre langue) sur devis. Contact : https://www.lectura.world/contact/
- **Bases** : la base Lexicon du français dérive de LeXiK et reste sous **CC BY-SA 4.0** (citer LeXiK, même
  licence) ; quiconque la reçoit peut la redistribuer, y compris à des fins commerciales. La licence commerciale
  couvre l'usage du code hors AGPL, les bases prêtes à l'emploi et le support ; elle ne restreint pas les droits
  que donne la CC BY-SA. La base anglaise dérive du lexique anglais de Lectura (Wiktionnaire, CMUdict,
  wordfreq, UD English-EWT) et reste sous CC BY-SA 4.0. Attributions : `ATTRIBUTION.md`, `NOTICE`.
- Fréquences lexicales calculées par Lectura sur des corpus de textes publiquement accessibles (encyclopédie,
  littérature, dialogues) ; seules des statistiques agrégées sont fournies, aucun texte de ces corpus.
