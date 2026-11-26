# Changelog — lectura-traducteur

## 1.0.0

Première version du Traducteur v1, reprise de `lectura-translator` 0.1.2 (même traduction, mêmes formules, même
alignement, même glossaire).

- Nouveau nom de paquet et d'import : `lectura-traducteur`, `lectura_traducteur`.
- `Traducteur(source, cible, mode=…)` : trois modes. `local` (aucun appel réseau, jamais ; erreur claire si un modèle
  manque), `api` (client des routes `/v1/traduire`, bibliothèque standard seule ; spécification proposée dans
  `docs/API-HTTP.md`), `auto` (local si les modèles sont installés, sinon API avec un avertissement). `creer_moteur`
  garde l'ancien nom.
- Dépend des Analyseurs `lectura-nlp-fr` et `lectura-nlp-en` (découpage, formules, analyse du glossaire) ; les
  dépendances du mode local sont dans les options `[local]` et `[aligneur]`.
- Retiré : tout chargement de code depuis un espace de développement (chemins ajoutés au chemin d'import) ; le
  moteur `hf` (transformers) et l'aligneur `torch`, réservés au développement ; la chaîne parole (`parole.py`), qui
  dépendait des anciennes briques voix (`lectura-tts`, `lectura-stt`) chargées depuis l'espace de développement.
- Option `analyseur=` : un Analyseur déjà chargé sert au glossaire (pas de seconde copie de ses modèles).
- Aucun modèle ni aucune donnée dans le paquet ; en-têtes AGPL dans tous les fichiers ; NOTICE et ATTRIBUTION.
