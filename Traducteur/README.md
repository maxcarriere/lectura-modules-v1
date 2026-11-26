# lectura-traducteur — le Traducteur de Lectura (v1)

Génération v1 (2026) de Lectura — https://www.lectura.world/developpement/modules/

French ⇄ English translation that keeps formulas right (times, dates, currencies, measures, percentages), with
word-by-word alignment and an in-context glossary — through the Lectura public API (default when no model is
installed) or local models. **No model is included in this package.**

*Traduction français ⇄ anglais qui respecte les formules (heures, dates, monnaies, mesures, pourcentages), avec
alignement mot à mot et glossaire en contexte. Par l'API publique de Lectura (par défaut quand aucun modèle n'est
installé) ou par des modèles installés sur la machine. Le paquet ne contient aucun modèle.*

## Installation

```bash
pip install lectura-traducteur                 # mode API (et les Analyseurs français et anglais)
pip install "lectura-traducteur[local]"        # + traduction en local (CTranslate2, sentencepiece)
pip install "lectura-traducteur[tout]"         # + aligneur précis et glossaire en local (onnxruntime, tokenizers)
```

Python 3.10 ou plus. Le Traducteur est la troisième fonction des modules NLP-FR et NLP-EN, à côté de l'Analyseur et
du Correcteur ; c'est un paquet à part, qui s'appuie sur les Analyseurs des deux langues (`lectura-nlp-fr`,
`lectura-nlp-en`, installés d'office) pour découper le texte en phrases, repérer les formules et analyser les mots du
glossaire. `pip install "lectura-nlp-fr[traducteur]"` ou `"lectura-nlp-en[traducteur]"` l'installe aussi.

## Vos textes partent vers l'API de Lectura (mode API)

En mode API, **les textes et les mots que vous passez aux fonctions sont envoyés au serveur de Lectura**
(`https://api.lectura.world`), qui calcule la traduction. L'API publique est gratuite, sans clé, avec un usage
limité. Politique de confidentialité : https://www.lectura.world/confidentialite/#api

- Changer d'adresse (votre propre serveur) : `Traducteur(..., api="https://…")`, la variable
  `LECTURA_TRADUCTEUR_API`, ou `LECTURA_API_URL` (commune aux modules v1 de Lectura).
- Ne rien envoyer : **mode local**, `Traducteur(..., mode="local")` ou `LECTURA_TRADUCTEUR_MODE=local`.

## Usage

```python
from lectura_traducteur import Traducteur

t = Traducteur("en", "fr")                           # mode auto
t.mode                                               # "local" ou "api"
t.traduire("She left the bank at 5 p.m. on March 3, 2024.")["texte"]
# 'Elle a quitté la banque à 17 h le 3 mars 2024.'

r = t.traduire(texte, aligner=True)                  # phrase par phrase : source, debut, fin, traduction,
                                                     # + mots_source, mots_cible, liens [(i, j)]
t.aligner(["She", "left"], ["Elle", "est", "partie"])   # {(0, 0), (1, 2)}
t.gloser("He gave up smoking.")                      # pour chaque mot : lemme, catégorie, prononciation,
                                                     # mots qui le traduisent ici, sens retenu

Traducteur("fr", "en").traduire("Le 1er novembre, il a payé 3,50 €.")["texte"]
# 'On November 1, he paid €3.50.'
```

Chaque phrase garde ses positions dans le texte d'origine (`debut`, `fin`). Les formules passent d'une convention à
l'autre : `5 p.m.` → `17 h`, `$3.50` → `3,50 $`, `March 3, 2024` → `3 mars 2024`, `18 %` → `18%`.

## Les trois modes

| Mode | Ce qui se passe | Choisi par |
|---|---|---|
| `local` | tout est calculé sur la machine ; **aucun appel réseau, jamais**, même en cas d'erreur (si un modèle manque : erreur `ModelesAbsents` qui le dit) | `mode="local"`, `models_dir=…`, `LECTURA_TRADUCTEUR_MODE=local` |
| `api` | l'API de Lectura calcule ; un texte trop long est envoyé en plusieurs requêtes, entre deux phrases | `mode="api"`, `api=…`, `LECTURA_TRADUCTEUR_MODE=api` |
| `auto` (défaut) | local si les modèles du sens demandé sont installés, sinon API **avec un avertissement** (`UserWarning`) qui dit que le texte partira vers l'API | rien |

Erreurs du mode API (mêmes classes que `lectura-lexicon`, `lectura-nlp-fr` et `lectura-nlp-en`) :
`QuotaDepasse` (quota du jour atteint ; `attente` en secondes), `ErreurAPI` (serveur injoignable ou indisponible ;
`statut`), `ValueError` (requête refusée : texte trop long, option inconnue…).

## Mode local : les modèles

Le paquet ne contient aucun modèle. Ils sont cherchés dans `models_dir`, `LECTURA_MODELS_DIR/traducteur`,
`~/.lectura/models/traducteur` (et `translator`, nom des versions 0.1) :

```
traducteur/
  opus-mt-en-fr-int8/        OPUS-MT de base, CTranslate2 int8 + source.spm, target.spm   79 Mo   Apache 2.0
  opus-mt-fr-en-int8/                                                                     79 Mo   Apache 2.0
  opus-mt-tc-big-en-fr-int8/ facultatif (taille="big")                                   236 Mo   CC BY 4.0
  opus-mt-tc-big-fr-en-int8/                                                             236 Mo   CC BY 4.0
  mbert8/                    mbert8_int8.onnx + tokenizer.json (aligneur précis)         153 Mo   Apache 2.0
  glossaire.db               facultatif (gloser)                                         144 Mo   CC BY-SA 4.0
```

- Les modèles OPUS-MT sont publics (Helsinki-NLP) : `ct2-transformers-converter --model Helsinki-NLP/opus-mt-en-fr
  --quantization int8 --output_dir opus-mt-en-fr-int8`, puis y copier `source.spm` et `target.spm`.
- Le dossier complet (avec l'aligneur précis et le glossaire) est remis avec la licence commerciale.
- Sans `mbert8/`, prendre `aligneur="leger"` (attention d'OPUS-MT, sans modèle de plus, moins précis).
- Le glossaire demande aussi les modèles de l'Analyseur de la langue source (`lectura-nlp-fr` ou `lectura-nlp-en`),
  en local.

Options du mode local : `taille` (`base`, `big`), `aligneur` (`precis`, `leger`), `fils` (fils de calcul), `gpu`,
`models_dir`, `analyseur` (Analyseur déjà chargé, partagé avec le glossaire).

Mémoire et temps (mesurés sur processeur, 2 fils) : un sens chargé environ 130 à 160 Mo ; tout chargé (deux sens,
aligneur, glossaires, Analyseurs) environ 0,95 Go ; environ 0,3 s par phrase de presse, soit 2 à 3 s de calcul pour
1 000 caractères (modèle « base », banc WMT14 du 25/11/2026).

## Résultats

Banc du 25/11/2026, sur le paquet construit, en local sur processeur, modèle « base » (celui de l'API publique) :
chaque phrase passe par `Traducteur(...).traduire()`, formules comprises. Score BLEU (sacrebleu 2.6.0, réglages par
défaut) contre les traductions humaines :

| Sens | BLEU | chrF |
|---|---|---|
| français → anglais | **37,6** | 63,0 |
| anglais → français | **39,7** | 64,8 |

Corpus : WMT14 newstest2014, 3 003 phrases de presse (Bojar et al., *Findings of the 2014 Workshop on Statistical
Machine Translation*, WMT 2014), jeu de test public de la campagne WMT, utilisé ici seulement pour mesurer.

## Licences

- Code : **AGPL-3.0-or-later** (`LICENCE.txt`), ou licence commerciale de Lectura (usage du code hors des
  obligations de l'AGPL, modèles prêts à l'emploi). Le Traducteur se prend avec le module NLP-FR, Analyseur anglais compris :
  licence NLP-FR avec le Traducteur 1 499 € HT, licence complète (NLP-FR avec le Correcteur et le Traducteur, et
  NLP-EN complet) 1 999 € HT (prix indicatifs, sur demande), TVA non applicable, art. 293 B du CGI. Demande :
  https://lingua.lectura.world/modules/obtenir
- Modèles (non inclus) : OPUS-MT de base et mBERT sous Apache 2.0, OPUS-MT tc-big sous CC BY 4.0, glossaire sous
  CC BY-SA 4.0 (Wiktionnaires). Détail : `ATTRIBUTION.md` et `NOTICE`.

Le paquet `lectura-translator` (0.1) n'est plus mis à jour : `lectura-traducteur` le remplace (`creer_moteur` reste
disponible sous son ancien nom ; la partie voix n'est pas reprise).
