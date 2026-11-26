# lectura-nlp-fr — le module NLP-FR (v1)

Génération v1 (2026) de Lectura — https://www.lectura.world/developpement/modules/

French NLP in one package: text to phonetics (liaisons, numbers, acronyms, formulas) and back, grammatical analysis
(Universal Dependencies), pedagogical spelling and grammar corrector, lexicon — through the Lectura public API (default
when no model is installed) or local models. **No model is included in this package.**

*Traitement automatique du français en un seul paquet : lecture (texte → phonétique) et écriture (phonétique → texte),
analyse grammaticale, correcteur pédagogique, lexique. Par l'API publique de Lectura (par défaut quand aucun modèle
n'est installé) ou par des modèles installés sur la machine. Le paquet ne contient aucun modèle.*

## Trois fonctions

- **Analyseur** (le module de base) : lire (texte → phonétique, avec liaisons, e caduc, nombres, sigles et
  formules), écrire (phonétique → texte), analyser (catégorie, traits, lemme et dépendance de chaque mot), découper.
- **Correcteur** (option `[correcteur]`) : correcteur orthographique et grammatical pédagogique ; chaque correction
  est expliquée en français.
- **Traducteur** (option `[traducteur]`) : traduction français ⇄ anglais. C'est un paquet à part,
  [`lectura-traducteur`](https://pypi.org/project/lectura-traducteur/), qui demande les Analyseurs des deux langues ;
  l'option l'installe avec `lectura-nlp-en`.

Le **lexique** est inclus : `nlp.lexique` donne les fonctions de Lexicon
([`lectura-lexicon`](https://pypi.org/project/lectura-lexicon/), installé d'office) : validité, fréquence,
homophones, rimes, conjugaison…

C'est symétrique pour l'anglais : [`lectura-nlp-en`](https://pypi.org/project/lectura-nlp-en/) a les mêmes
fonctions, les mêmes noms et les mêmes modes.

## Installation

```bash
pip install lectura-nlp-fr                  # mode API (aucune dépendance lourde)
pip install "lectura-nlp-fr[onnx]"          # Analyseur en local (onnxruntime, numpy)
pip install "lectura-nlp-fr[correcteur]"    # Analyseur et Correcteur en local (+ kenlm, compilateur C++ requis)
pip install "lectura-nlp-fr[traducteur]"    # + le Traducteur (lectura-traducteur, lectura-nlp-en)
```

Python 3.10 ou plus récent.

## Vos données partent vers l'API de Lectura (mode API)

En mode API (`mode="api"`, ou `mode="auto"` quand les modèles ne sont pas installés), **les textes, les
prononciations et les mots passés aux fonctions sont envoyés au serveur de Lectura** (`https://api.lectura.world`).
L'API publique est gratuite, sans clé, avec un usage limité (quota journalier ; au-delà, l'erreur `QuotaDepasse` est
levée). Politique de confidentialité : https://www.lectura.world/confidentialite/#api

- Changer d'adresse (votre propre serveur) : `creer_moteur(api="https://…")` ou la variable `LECTURA_API_URL`.
- Ne rien envoyer : `mode="local"` ou `mode="degrade"` (modèles installés).

## Usage

```python
from lectura_nlp_fr import creer_moteur

nlp = creer_moteur()                                   # mode "auto"
print(nlp.mode)                                        # "local" ou "api"
nlp.lire("Les petits enfants sont arrivés.")[0]["phone"]
# 'le pə.ti.z‿ɑ̃.fɑ̃ sɔ̃.t‿a.ʁi.ve.'
nlp.ecrire("le pə.ti.z‿ɑ̃.fɑ̃")[0]["ortho"]             # 'Les petits enfants'
for mot in nlp.analyser("Il mange une pomme.")[0]:
    print(mot["forme"], mot["upos"], mot["lemme"], mot["traits"])   # mange VERB manger {'Mood': 'Ind', …}
r = nlp.corriger("Les enfant mange des pomme.")        # mode "suggestions" ; ou mode="automatique"
print(r.texte)                                         # 'Les enfants mangent des pommes.'
for c in r.corrections:
    print(c.original, "→", c.proposition, ":", c.explication)
# enfant → enfants : Après « Les », le nom « enfant » est au pluriel : « enfants ».
[f.ortho for f in nlp.lexique.homophones("vɛʁ")]       # ['vers', 'verre', 'vert', 'verts', 'verres', 'ver', …]
```

## Les modes

| `mode` | Ce qui se passe | Réseau |
|---|---|---|
| `"local"` | tout sur la machine, avec une base Lexicon locale ; erreur claire si les modèles manquent ; sans base, les fonctions lexicales répondent « lexique indisponible » | **aucun appel, jamais** |
| `"api"` | tout par l'API publique de Lectura | les textes partent vers le serveur |
| `"degrade"` | l'Analyseur sur ses seuls modèles, sans base Lexicon ; les fonctions lexicales répondent « lexique indisponible : installer une base ou autoriser l'API », sans erreur ; pas de Correcteur | aucun appel |
| `"auto"` (défaut) | local si les modèles sont installés, sinon l'API ; sans base Lexicon locale, le lexique et le Correcteur passent par l'API ; **un avertissement le dit** | seulement en repli annoncé |

Le mode dégradé lit et écrit aussi bien que le mode local : mêmes scores sur CSF18 en lecture (PER 5,8 %) et en
écriture (WER 17,1 %). Par défaut, la base Lexicon sert aux fonctions lexicales et au Correcteur, pas à la lecture
ni à l'écriture (`ecriture_lexique=False` : élargir l'écriture à la base n'a rien apporté au banc). `nlp.etat()` dit
ce qui est chargé.

## Résultats

Bancs du 25/11/2026, sur le paquet construit, en local sur processeur. Références humaines seulement ; le même banc sert
pour la v0 et pour espeak-ng (point de comparaison extérieur).

| Fonction | Mesure | Corpus | **v1** | v0 | espeak-ng |
|---|---|---|---|---|---|
| Lecture de phrases | erreurs de phonèmes (PER), strict | CSF18, 238 phrases | **5,8 %** | 6,7 % | 12,9 % |
| Lecture d'un mot seul (modèle de mot, sans lexique) | mots exacts | WikiPron, 971 mots absents de l'entraînement | **77 %** | 58 % | 64 % |
| Écriture de phrases | mots faux (WER) | CSF18, 238 phrases | **17,1 %** | 25,3 % | — |
| Analyse grammaticale | catégorie (UPOS) / six traits justes ensemble | UD French-PUD, 1 000 phrases jamais vues | **97,5 % / 95,0 %** | 94,2 % / 80,5 % | — |
| Correcteur | F0,5 (précision 62 %, rappel 56 %) | WiCoPaCo, 2 000 phrases du test gelé | **60** | — | — |

Corpus : CSF18 (Zenodo, DOI 10.5281/zenodo.5554849, CC BY 4.0) ; WikiPron (Lee et al., LREC 2020 ; données du
Wiktionnaire, CC BY-SA) ; UD French-PUD (Universal Dependencies, CC BY-SA 4.0) ; WiCoPaCo (Max et Wisniewski, LREC
2010 ; révisions de la Wikipédia française, texte sous licences de Wikipédia : GFDL et CC BY-SA 3.0). Détail et méthode : documentation du module.

## Note technique : modèles du mode local

Les modèles ne sont pas publiés ; ils sont livrés avec la licence commerciale. Ils se placent ainsi :

| Pièce | Dossier (dans l'ordre de recherche) |
|---|---|
| Analyseur | `models_dir=`, `LECTURA_NLP_FR_DIR`, `$LECTURA_MODELS_DIR/transducer`, `~/.lectura/models/transducer` |
| Juge des homophones de l'écriture | `LECTURA_JUGE_DIR`, `<dossier de l'Analyseur>/juge`, `$LECTURA_MODELS_DIR/juge`, `~/.lectura/models/juge` |
| Correcteur | `correcteur_dir=`, `LECTURA_CORRECTEUR_DIR`, `$LECTURA_MODELS_DIR/corrector`, `~/.lectura/models/corrector` |
| Juge du Correcteur | `juge_correcteur=`, `LECTURA_JUGE_CORRECTEUR_DIR`, `<dossier du Correcteur>/juge` |
| Base Lexicon | celle de `lectura-lexicon` : `lexique=`, `LECTURA_LEXICON_DATA`, `$LECTURA_MODELS_DIR/lexicon`, `~/.lectura/models/lexicon` |

Le Correcteur en local demande une base Lexicon locale (la « standard » de préférence). Un juge des homophones ou un
supplément d'écriture absent n'est jamais ignoré en silence : un avertissement (`AvertissementNLP`) le signale.

Anciens noms : `lectura_nlp_fr.analyseur` reprend `lectura-transducer` 1.1.0 et `lectura_nlp_fr.correcteur` reprend
`lectura-corrector` 0.1.0. Après `import lectura_nlp_fr`, `import lectura_transducer` et `import lectura_corrector`
mènent à ces sous-paquets.

## Licence

- **Code** : AGPL-3.0-or-later (`LICENCE.txt`), ou licence commerciale de Lectura pour l'intégrer dans un produit
  fermé. Licence commerciale du module NLP-FR v1, avec les modèles pour le mode local et les bases Lexicon prêtes à
  l'emploi : Analyseur 999 € HT ; avec le Correcteur 1 499 € HT ; avec le Traducteur (Analyseur anglais compris) 1 499 € HT ;
  avec les deux options et NLP-EN complet 1 999 € HT (prix indicatifs, sur demande), TVA non applicable, art. 293 B du CGI. Demande :
  https://lingua.lectura.world/modules/obtenir
- **Tables de règles** (`lectura_nlp_fr/analyseur/data/`) : CC BY-SA 4.0, dérivées de LeXiK ou écrites par Lectura
  (`NOTICE`, `ATTRIBUTION.md`).
- **Modèles** : non inclus ; servis par l'API publique ou livrés avec la licence commerciale. Sources d'entraînement
  dans `ATTRIBUTION.md`.
