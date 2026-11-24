# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Format des données embarquées (``lexicon.db``, sqlite) : schéma et drapeaux des formes. Même format que
``lectura-lexicon`` (français), plus la table ``americaines`` et le drapeau ``BRITANNIQUE``.

- ``formes``    : une ligne par graphie ; ``min`` = minuscules (recherche sans casse) ; ``zipf`` de la graphie
                  (wordfreq) ; ``zipf_lemme`` = plus grand zipf de ses lemmes du noyau ; ``drapeaux`` ci-dessous.
- ``cles_phone`` : clés phonétiques (``cles.cle_phone``) numérotées ; ``formes.cles`` = numéros des clés de la forme ;
                  ``inverse`` = phonèmes de la clé à l'envers, séparés par des espaces (``cles.inverse``) : rimes.
- ``formes.anagramme`` : (standard, complet) lettres de la forme triées, sans accents ni casse (``cles.anagramme``).
- ``phones``    : numéro de clé → forme ; homophones.
- ``analyses``  : (standard, complet) lemme, UPOS, traits, prononciation syllabée et accentuée, zipf de l'analyse ;
                  ``masquee`` (zipf 0 alors qu'une autre analyse de la forme a été vue) ; ``phone_enrichi`` quand il
                  diffère de ``phone`` ; sources et confiance en taille complète ; ``syllabes`` = nombre de syllabes.
                  Une analyse venue du seul Wiktionnaire n'a pas de prononciation (``phone`` vide).
                  (0.3) ``marque`` : étiquettes du Wiktionnaire (dialectal, archaic, rare…) d'une flexion que toutes
                  ses entrées marquent ainsi (et : passé dialectal de eat) ; NULL pour une forme courante.
- ``lemmes``    : identifiant (``lemme#UPOS``), lemme, UPOS, zipf du lemme ; ``masculin`` / ``feminin`` vides.
- ``usuelles``  : graphie usuelle d'une forme variante (seperate → separate, alot → a lot).
- ``americaines`` : graphie américaine d'une forme britannique (colour → color, realised → realized).
- ``voisins``   : empreinte (``cles.empreinte``) des suppressions de lettres des formes en minuscules → forme.
- ``voisins_phones`` : empreinte des suppressions de phonèmes des clés phonétiques → numéro de clé.

Référence complète du format : ``docs/FORMAT.md``.
"""

NOYAU = 1            # au moins une analyse du noyau du lexique anglais
PROPRE_SEUL = 2      # toutes les analyses sont des noms propres
SPECIAL = 4          # forme des Spéciaux (lettre, sigle, abréviation, symbole)
ACCEPTEE_NOYAU = 8   # forme du noyau d'un lemme courant (zipf du lemme ≥ plancher de la construction)
VARIANTE = 16        # faute connue du Wiktionnaire (misspelling, proscribed : seperate, alot) : acceptée, jamais proposée
RECTIFIEE = 32       # (français seulement : orthographe rectifiée de 1990)
BRITANNIQUE = 64     # graphie britannique (colour, centre, realise, travelled) : juste, équivalent américain connu
UTILISATEUR = 256    # (0.3) mot du dictionnaire de l'utilisateur (jamais dans les données ; ``utilisateur.py``) ;
                     # 64 est déjà BRITANNIQUE en anglais (en français, UTILISATEUR vaut 64)
NON_VALIDE = 128     # (0.3) forme non validée : jeton de wordfreq absent du lexique et du Wiktionnaire (dont, world's),
                     # ou forme du seul Wiktionnaire, sans prononciation, sous les seuils et hors noyau d'un lemme
                     # courant ; sa fréquence reste consultable, mais elle n'est jamais un mot sûr : ``validite`` la
                     # dit « inconnue », elle sort des homophones, voisins, rimes et recherches

SCHEMA = """
CREATE TABLE formes (id INTEGER PRIMARY KEY, ortho TEXT, min TEXT, zipf REAL, zipf_lemme REAL, drapeaux INTEGER,
                     cles TEXT, anagramme TEXT);
CREATE TABLE cles_phone (id INTEGER PRIMARY KEY, cle TEXT, inverse TEXT);
CREATE TABLE phones (cle INTEGER, forme INTEGER, PRIMARY KEY (cle, forme)) WITHOUT ROWID;
CREATE TABLE analyses (forme INTEGER, lemme INTEGER, upos INTEGER, traits INTEGER, phone TEXT, zipf REAL,
                       masquee INTEGER, phone_enrichi TEXT, sources INTEGER, confiance TEXT, syllabes INTEGER,
                       marque TEXT);
CREATE TABLE lemmes (id INTEGER PRIMARY KEY, id_lemme TEXT, lemme TEXT, upos TEXT, zipf REAL, masculin TEXT,
                     feminin TEXT, auxiliaire TEXT, pronominal TEXT, groupe INTEGER,
                     auxiliaire_source TEXT, ortho_1990 TEXT);
CREATE TABLE codes (espace TEXT, id INTEGER, valeur TEXT, PRIMARY KEY (espace, id)) WITHOUT ROWID;
CREATE TABLE usuelles (forme INTEGER PRIMARY KEY, usuelle TEXT);
CREATE TABLE americaines (forme INTEGER PRIMARY KEY, americaine TEXT);
CREATE TABLE voisins (cle INTEGER, forme INTEGER, PRIMARY KEY (cle, forme)) WITHOUT ROWID;
CREATE TABLE voisins_phones (cle INTEGER, phone INTEGER, PRIMARY KEY (cle, phone)) WITHOUT ROWID;
CREATE TABLE metadonnees (cle TEXT PRIMARY KEY, valeur TEXT);
"""
