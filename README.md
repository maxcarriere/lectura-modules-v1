# Lectura v1 : modules de traitement du français (et de l'anglais)

Code des modules v1 de [Lectura](https://www.lectura.world), sous licence **AGPL-3.0-or-later**.

Les modèles et les bases de la v1 ne sont pas dans ce dépôt : les modules les appellent par l'**API publique**
(`https://api.lectura.world/v1`, gratuite, sans clé, avec un usage limité). Une licence commerciale, avec les modèles
et les bases en local, est disponible sur demande : https://lingua.lectura.world/modules/obtenir

| Dossier | Paquet | Rôle |
|---|---|---|
| [`Lexicon/`](Lexicon/) | [`lectura-lexicon`](https://pypi.org/project/lectura-lexicon/) | lexique du français et de l'anglais : validité, fréquence, prononciations, homophones, rimes, conjugaison, voisins, anagrammes ; bases tirées de LeXiK (CC BY-SA 4.0) |

Les autres modules v1 (NLP-FR, NLP-EN, Traducteur, voix) seront publiés ici au fur et à mesure.

- Version v0 (modèles téléchargeables) : https://github.com/maxcarriere/lectura-modules-v0
- Confidentialité de l'API publique : https://www.lectura.world/confidentialite/#api
