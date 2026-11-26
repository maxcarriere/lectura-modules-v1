# Journal des versions — lectura-nlp-fr

## 2.0.0 — module NLP-FR v1 (en préparation, non publié)

Première version publique, sous AGPL-3.0-or-later. Remplace `lectura-nlp-fr` 1.2.0 (non publié sur PyPI),
`lectura-transducer` et `lectura-corrector`.

- **Un seul paquet** : Analyseur (`lectura_nlp_fr.analyseur`, copie figée de `lectura-transducer` 1.1.0 : lecture
  1.0.5, écriture 1.1.0) et Correcteur (`lectura_nlp_fr.correcteur`, copie figée de `lectura-corrector` 0.1.0, option
  `[correcteur]`) ; Lexicon par `lectura-lexicon` 1.0.0 (dépendance par défaut).
- **Entrée unique** `creer_moteur(mode="auto" | "local" | "api" | "degrade")` → `lire`, `ecrire`, `analyser`,
  `decouper`, `corriger`, `lexique`, `etat`.
- **Mode API** sur les routes `/v1/lire`, `/v1/ecrire`, `/v1/corriger`, `/v1/lexique` de l'API publique ; erreurs
  communes avec `lectura-lexicon` (`ErreurAPI`, `QuotaDepasse`).
- **Mode local** : aucun appel réseau, jamais ; erreur claire si les modèles manquent. **Mode dégradé** : sans base
  Lexicon. **Mode auto** : le passage à l'API est annoncé par un avertissement.
- **Juges explicites** : l'écriture prend le juge des homophones trouvé (v3 livré) et avertit s'il manque ; le
  Correcteur reçoit son propre juge (v2b, avec lequel ses seuils ont été réglés), jamais celui de l'écriture.
- **Aucun modèle dans le paquet** ; tables de règles sous CC BY-SA 4.0 (`NOTICE`).
- Le Correcteur lit `lectura-lexicon` 1.0.0 (base locale « standard » de préférence) au lieu de l'ancien Lexicon 0.x.
- `creer_moteur(ecriture_lexique=False)` par défaut : l'écriture n'est plus élargie aux formes de la base Lexicon
  (aucun gain mesuré sur CSF18 : 17,07 % sans, 17,12 % avec la base standard) ; `True` ou `"auto"` la rétablissent.
  La classe `MoteurNLP` garde `"auto"` par défaut, par compatibilité avec la 1.2.0.
- `etat()` reste sérialisable en JSON en mode dégradé.
- Alias d'import `lectura_transducer` et `lectura_corrector` vers les sous-paquets.
