# Lectura v1 : modules de traitement du français (et de l'anglais)

Code des modules v1 de [Lectura](https://www.lectura.world), sous licence **AGPL-3.0-or-later**.

Les modèles et les bases de la v1 ne sont pas dans ce dépôt : les modules les appellent par l'**API publique**
(`https://api.lectura.world/v1`, gratuite, sans clé, avec un usage limité). Une licence commerciale, avec les modèles
et les bases en local, est disponible sur demande : https://lingua.lectura.world/modules/obtenir

| Dossier | Paquet | Rôle |
|---|---|---|
| [`NLP-FR/`](NLP-FR/) | [`lectura-nlp-fr`](https://pypi.org/project/lectura-nlp-fr/) | traitement du français : Analyseur (lire, écrire, analyser), Correcteur en option, lexique (Lexicon) inclus |
| [`NLP-EN/`](NLP-EN/) | [`lectura-nlp-en`](https://pypi.org/project/lectura-nlp-en/) | le même module pour l'anglais : Analyseur, Correcteur en option, lexique inclus |
| [`Traducteur/`](Traducteur/) | [`lectura-traducteur`](https://pypi.org/project/lectura-traducteur/) | traduction français ⇄ anglais, formules respectées, alignement mot à mot, glossaire en contexte ; demande les Analyseurs des deux langues |
| [`Lexicon/`](Lexicon/) | [`lectura-lexicon`](https://pypi.org/project/lectura-lexicon/) | lexique du français et de l'anglais : validité, fréquence, prononciations, homophones, rimes, conjugaison, voisins, anagrammes ; base française tirée de LeXiK, base anglaise du lexique anglais de Lectura (CC BY-SA 4.0) |

NLP-FR réunit trois fonctions : l'Analyseur, le Correcteur (`pip install "lectura-nlp-fr[correcteur]"`) et le
Traducteur (`pip install "lectura-nlp-fr[traducteur]"`, paquet à part qui installe aussi NLP-EN). C'est symétrique
pour l'anglais. Lexicon est installé d'office avec NLP-FR et NLP-EN.

Les modules de voix v1 seront publiés ici plus tard.

- Version v0 (modèles téléchargeables) : https://github.com/maxcarriere/lectura-modules-v0
- Confidentialité de l'API publique : https://www.lectura.world/confidentialite/#api
