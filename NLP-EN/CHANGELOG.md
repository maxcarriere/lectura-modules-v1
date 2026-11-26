# Journal des versions — lectura-nlp-en

## 1.0.0 — module NLP-EN v1 (en préparation, non publié)

Première version publique, sous AGPL-3.0-or-later. Remplace `lectura-nlp-en` 0.3.0 (non publié sur PyPI),
`lectura-transducer-en` et `lectura-corrector-en`.

- **Un seul paquet** : Analyseur (`lectura_nlp_en.analyseur`, copie figée de `lectura-transducer-en` 0.1.2) et
  Correcteur (`lectura_nlp_en.correcteur`, copie figée de `lectura-corrector-en` 0.4.0, option `[correcteur]`) ;
  Lexicon par `lectura-lexicon` 1.0.0 (dépendance par défaut, `langue="en"`), à la place de `lectura-lexicon-en`.
- **Entrée unique** `creer_moteur(mode="auto" | "local" | "api" | "degrade")` → `lire`, `ecrire`, `analyser`,
  `decouper`, `corriger`, `lexique`, `etat` ; mêmes noms, mêmes modes, mêmes erreurs que `lectura-nlp-fr` 2.0.0.
- **Mode API** sur les routes `/v1/lire`, `/v1/ecrire`, `/v1/corriger`, `/v1/lexique` de l'API publique ; erreurs
  communes avec `lectura-lexicon` (`ErreurAPI`, `QuotaDepasse`). L'ancien `MoteurAPI` appelait `/nlp/en/…`.
- **Mode local** : aucun appel réseau, jamais ; erreur claire si les modèles manquent. **Mode dégradé** : sans base
  Lexicon. **Mode auto** : le passage à l'API est annoncé par un avertissement (l'ancien `auto` y passait en silence).
- **Code de développement retiré** : adaptateurs PyTorch (`adaptateurs/etalon.py`, `adaptateurs/gpa.py`), lexique TSV
  de développement, mode `dev`, modèle de langue compact inutilisé (`modele_langue.py`) ; plus aucun `sys.path` vers
  l'espace de développement. Les décisions de l'analyseur (candidats, contractions, formules, choix de la tête) passent
  telles quelles dans `adaptateurs/analyseur_onnx.py` (`_Arbitrage`) : sortie identique à la 0.1.2.
- **Aucun modèle dans le paquet** ; tables de règles sous CC BY-SA 4.0 (`NOTICE`, `ATTRIBUTION.md`).
- Vocabulaire de l'analyseur livré avec les modèles : quatre chaînes contenant des adresses électroniques (deux
  classes de lemme, deux motifs) remplacées par le repli (`<RARE>`, motif neutre) ; une classe `<RARE>` vaut repli.
- Le Correcteur lit `lectura-lexicon` 1.0.0 (base locale « standard » de préférence) au lieu de `lectura-lexicon-en`.
- Branchement de Lexicon sur l'écriture repris dans `lectura_nlp_en.lexique` (base locale seulement).
- Alias d'import `lectura_transducer_en` et `lectura_corrector_en` vers les sous-paquets.
- Tests : phrases du Correcteur d'origine incertaine réécrites (phrases inventées, mêmes cas) ; adresse et nom de
  fichier tirés de corpus remplacés dans les tests de l'Analyseur ; tests de modes, d'API et de paquet ajoutés.
