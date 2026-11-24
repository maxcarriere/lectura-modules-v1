# Journal des versions — lectura-lexicon

## 1.0.0 — module Lexicon v1 (en préparation, non publié)

Première version publique, sous AGPL-3.0-or-later.

- **Un seul paquet pour le français et l'anglais** : `Lexicon(langue="fr" | "en")` réunit les moteurs français et
  anglais des versions précédentes du module (non publiées sur PyPI), avec les mêmes noms de fonctions ;
  les fonctions propres à une langue restent propres à elle (`rectifiee`, `autre_genre` ; `britannique`,
  `americaine`, `britanniques`, `rime`).
- **Mode API par défaut** : sans base locale, les fonctions sont calculées par l'API publique de Lectura
  (`https://api.lectura.world/v1/lexique/…`, adresse réglable). Les mots envoyés partent vers le serveur.
- **Mode local** : une base au format rapide (`chemin=`, `LECTURA_LEXICON_DATA`, `LECTURA_LEXICON_EN_DATA`,
  `~/.lectura/models/lexicon[_en]`). Aucune base dans le paquet.
- **Conversion** (`lectura_lexicon.convertir`, `python -m lectura_lexicon convertir`) : base au format rapide
  depuis LeXiK téléchargée, Lexique 3, GLÀFF ou un CSV/TSV maison (alias de colonnes de la v0).
- **Compatibilité v0** : `lectura_lexicon.Lexique` est le module Lexique v0 (`lectura-lexique` 1.6.1) inclus tel
  quel ; `Lexicon` porte aussi les alias `phone_de`, `lemme_de`, `info`, `rimes_par_suffixe`, `existe_nom_propre`,
  `phone_nom_propre`, `homophones_nom_propre`, `decoder_multext`, `close` et le gestionnaire de contexte.
- Types communs `Forme` et `Lecture` (champs des deux langues) ; `Forme.britannique` passe en fin de dataclass.
- Empreintes des archives de bases écrites dans le code (plus de fichier JSON dans le paquet).
- **Table des lemmes** (français) : `lemme_info`, `h_aspire`, `auxiliaire`, `pronominal`, `est_pronominal`,
  `groupe`, et les filtres `groupe`, `auxiliaire`, `pronominal`, `h_aspire` de `rechercher` / `filtrer` ;
  `lemme_info` en anglais (lemme, UPOS, fréquence).
- **Base nue** (`lectura_lexicon.nue`, commandes `denuder`, `indexer` et `installer`) : seulement les données non
  calculables ; index construits chez l'utilisateur, une fois (à l'installation ou au premier usage).
- Convertisseur : mémoire bornée (lecture en flux, base de travail SQLite), profils `--taille`, traits UD de
  l'annexe MULTEXT de LeXiK.
