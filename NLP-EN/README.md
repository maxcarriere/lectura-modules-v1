# lectura-nlp-en — le module NLP-EN (v1)

Génération v1 (2026) de Lectura — https://www.lectura.world/developpement/modules/

English NLP (General American) in one package, symmetric to `lectura-nlp-fr`: text to phonetics (connected speech,
weak and strong forms, numbers, dates, acronyms, formulas) and back, grammatical analysis (Universal Dependencies),
pedagogical spelling and grammar corrector with explanations in French or English, lexicon — through the Lectura
public API (default when no model is installed) or local models. **No model is included in this package.**

*Traitement automatique de l'anglais (américain) en un seul paquet, symétrique de `lectura-nlp-fr` : lecture et
écriture, analyse grammaticale, correcteur pédagogique, lexique. Par l'API publique de Lectura (par défaut quand aucun
modèle n'est installé) ou par des modèles installés sur la machine. Le paquet ne contient aucun modèle.*

## Trois fonctions, comme en français

- **Analyseur** (le module de base) : lire (texte → phonétique, avec jonctions de phrase, formes faibles et fortes,
  nombres, dates, sigles et formules), écrire (phonétique → texte), analyser (catégorie, traits, lemme et dépendance
  de chaque mot, conventions Universal Dependencies), découper (contractions *ca + n't*, *I + 'm*…).
- **Correcteur** (option `[correcteur]`) : correcteur orthographique et grammatical pédagogique de l'anglais ;
  chaque correction est expliquée en français ou en anglais.
- **Traducteur** (option `[traducteur]`) : traduction anglais ⇄ français. C'est un paquet à part,
  [`lectura-traducteur`](https://pypi.org/project/lectura-traducteur/), qui demande les Analyseurs des deux langues ;
  l'option l'installe avec `lectura-nlp-fr`.

Le **lexique** est inclus : `nlp.lexique` donne les fonctions de Lexicon pour l'anglais
([`lectura-lexicon`](https://pypi.org/project/lectura-lexicon/), installé d'office) : validité, fréquence,
homophones, rimes, graphies britanniques et américaines…

## Installation

```bash
pip install lectura-nlp-en                  # mode API (aucune dépendance lourde)
pip install "lectura-nlp-en[onnx]"          # Analyseur en local (onnxruntime, numpy)
pip install "lectura-nlp-en[correcteur]"    # Analyseur et Correcteur en local (+ kenlm, compilateur C++ requis)
pip install "lectura-nlp-en[traducteur]"    # + le Traducteur (lectura-traducteur, lectura-nlp-fr)
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
from lectura_nlp_en import creer_moteur

nlp = creer_moteur()                                   # mode "auto"
print(nlp.mode)                                        # "local" ou "api"
nlp.lire("The children arrived at school on March 5, 2020.")[0]["phone"]
# 'ðə ˈtʃɪl.dɹə.n‿əˈɹaɪv.d‿ət ˈsku.l‿ɑn ˈmɑɹtʃ ˈfɪfθ ˈtwɛn.ti ˈtwɛn.ti.'
nlp.ecrire("ðə ˈkɝ.nəl")[0]["ortho"]                   # 'The colonel'
for mot in nlp.analyser("She left the bank at 5 p.m.")[0]:
    print(mot["forme"], mot["upos"], mot["lemme"], mot["traits"])   # left VERB leave {'Mood': 'Ind', …}
r = nlp.corriger("i dont think he go to school.")      # mode "suggestions" ; ou mode="automatique"
print(r.texte)                                         # "I don't think he goes to school."
for c in r.corrections:
    print(c.original, "→", c.proposition, ":", c.explication)   # explications="en" : en anglais
# go → goes : Avec le sujet « he » (3e personne du singulier), le verbe s'écrit « goes » : …
[f.ortho for f in nlp.lexique.homophones("ðɛɹ")]       # ['their', 'there', "they're"]
```

## Les modes

| `mode` | Ce qui se passe | Réseau |
|---|---|---|
| `"local"` | tout sur la machine, avec une base Lexicon locale ; erreur claire si les modèles manquent ; sans base, les fonctions lexicales répondent « lexique indisponible » | **aucun appel, jamais** |
| `"api"` | tout par l'API publique de Lectura | les textes partent vers le serveur |
| `"degrade"` | l'Analyseur sur ses seuls modèles, sans base Lexicon ; les fonctions lexicales répondent « lexique indisponible : installer une base ou autoriser l'API », sans erreur ; pas de Correcteur | aucun appel |
| `"auto"` (défaut) | local si les modèles sont installés, sinon l'API ; sans base Lexicon locale, le lexique et le Correcteur passent par l'API ; **un avertissement le dit** | seulement en repli annoncé |

`nlp.etat()` dit ce qui est chargé (dossiers, base lexicale, Correcteur). En anglais, quand une base Lexicon locale
est ouverte, l'écriture (phonétique → texte) accepte aussi les mots de la base que le lexique embarqué de l'Analyseur
ne connaît pas (`ecriture_lexique="auto"`, défaut ; `False` pour l'éviter). L'effet de ce réglage, comme l'écart entre
le mode local et le mode dégradé, n'a pas été mesuré au banc v1.

## Résultats

Banc du 25/11/2026, sur le paquet construit, en local sur processeur, référence humaine.

| Fonction | Mesure | Corpus | **v1** |
|---|---|---|---|
| Correcteur | F0,5, mode suggestions / mode automatique | WikEd Error Corpus, 3 200 phrases du test gelé | **71 / 69** |

WikEd Error Corpus : Grundkiewicz et Junczys-Dowmunt, PolTAL 2014 ; révisions de la Wikipédia anglaise (texte sous licences de Wikipédia : CC BY-SA 3.0 et GFDL).
Il n'existe pas encore de banc de phrases anglaises à phonétique vérifiée à la main (pendant de CSF18) : la lecture et
l'écriture anglaises ne sont pas chiffrées ici.

## Note technique : modèles du mode local

Les modèles ne sont pas publiés ; ils sont livrés avec la licence commerciale. Ils se placent ainsi :

| Pièce | Dossier (dans l'ordre de recherche) |
|---|---|
| Analyseur | `models_dir=`, `LECTURA_NLP_EN_DIR`, `$LECTURA_MODELS_DIR/transducer_en`, `~/.lectura/models/transducer_en` |
| Correcteur (et sa tête de graphie, `tete/`) | `correcteur_dir=`, `LECTURA_CORRECTEUR_EN_DIR`, `$LECTURA_MODELS_DIR/corrector_en`, `~/.lectura/models/corrector_en` |
| Base Lexicon | celle de `lectura-lexicon` : `lexique=`, `LECTURA_LEXICON_EN_DATA`, `~/.lectura/models/lexicon_en` |

Le Correcteur en local demande une base Lexicon anglaise locale (la « standard » de préférence).

Anciens noms : `lectura_nlp_en.analyseur` reprend `lectura-transducer-en` 0.1.2 et `lectura_nlp_en.correcteur`
reprend `lectura-corrector-en` 0.4.0. Après `import lectura_nlp_en`, `import lectura_transducer_en` et
`import lectura_corrector_en` mènent à ces sous-paquets.

## Licence

- **Code** : AGPL-3.0-or-later (`LICENCE.txt`), ou licence commerciale de Lectura pour l'intégrer dans un produit
  fermé. Licence commerciale du module NLP-EN v1 (Analyseur et Correcteur), avec les modèles pour le mode local et les
  bases Lexicon prêtes à l'emploi : 999 € HT (indicatif, sur demande), TVA non applicable, art. 293 B du CGI.
  L'Analyseur anglais et le Traducteur sont compris dans la licence NLP-FR avec le Traducteur (1 499 € HT, indicatif),
  sans le Correcteur anglais ; NLP-EN complet est compris dans la licence complète (1 999 € HT, indicatif). Demande : https://lingua.lectura.world/modules/obtenir
- **Tables de règles** (`lectura_nlp_en/analyseur/data/`) : CC BY-SA 4.0, dérivées du lexique anglais de Lectura
  (Wiktionnaire via kaikki.org, CMUdict, wordfreq, UD English-EWT) ou de LeXiK, ou écrites par Lectura (`NOTICE`,
  `ATTRIBUTION.md`).
- **Modèles** : non inclus ; servis par l'API publique ou livrés avec la licence commerciale. Sources d'entraînement
  dans `ATTRIBUTION.md`.
