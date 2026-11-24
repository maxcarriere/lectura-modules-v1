# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Format des données embarquées (``lexicon.db``, sqlite) : schéma et drapeaux des formes.

- ``formes``    : une ligne par graphie ; ``min`` = minuscules (recherche sans casse) ; ``zipf`` de la graphie ;
                  ``zipf_lemme`` = plus grand zipf de ses lemmes du noyau ; ``drapeaux`` ci-dessous. Référence
                  complète du format : ``docs/FORMAT.md``.
- ``cles_phone`` : clés phonétiques (``cles.cle_phone``) numérotées ; ``formes.cles`` = numéros des clés de la forme ;
                  ``inverse`` = la clé à l'envers, phonème par phonème (``cles.inverse``) : rimes.
- ``formes.anagramme`` : (standard, complet) lettres de la forme triées, sans accents ni casse (``cles.anagramme``).
- ``phones``    : numéro de clé → forme ; homophones. ``masquee`` (0.4) = clé venue seulement de lectures masquées
                  (lettre épelée « la » → ɛla, abréviation « Bon » → bataillon) : écartée des homophones, rimes et
                  recherches par son.
- ``analyses``  : (standard, complet) lemme, UPOS, traits, prononciation syllabée, zipf de l'analyse ; ``masquee``
                  = zipf 0 alors qu'une autre analyse de la forme a été vue par l'étiquetage (enfant ADJ) ;
                  ``phone_enrichi`` (marques du cadre : latentes, h aspiré, {a|b}) quand il diffère de ``phone`` ;
                  sources et confiance en taille complète ; ``syllabes`` = nombre de syllabes de ``phone``.
                  ``multext`` (0.5) = étiquette MULTEXT de LeXiK (Ncms, Vmip3s-). UPOS, traits, sources et MULTEXT
                  sont codés (table ``codes``). ``marque`` (0.5) = étiquettes du Wiktionnaire quand toutes les
                  entrées de la flexion la marquent (rare, archaic, dated…), NULL pour une forme courante.
- ``lemmes``    : identifiant LeXiK (``lemme#UPOS[#n]``), lemme, UPOS, zipf du lemme ; ``masculin`` / ``feminin`` =
                  lemme de l'autre genre (acteur → feminin actrice ; actrice → masculin acteur).
- ``usuelles``  : graphie usuelle d'une forme variante (enfans → enfants), quand elle est connue.
- ``voisins``   : empreinte (``cles.empreinte``) des suppressions de lettres des formes en minuscules → forme.
- ``voisins_phones`` : empreinte des suppressions de phonèmes des clés phonétiques → numéro de clé.
"""

NOYAU = 1            # au moins une analyse du noyau de LeXiK
PROPRE_SEUL = 2      # toutes les analyses sont des noms propres
SPECIAL = 4          # forme des Spéciaux (abrègement, symbole, élément)
ACCEPTEE_NOYAU = 8   # forme du noyau d'un lemme courant (zipf du lemme ≥ plancher de la construction)
VARIANTE = 16        # graphie ancienne ou concurrente (enfans, loix, sçavoir) : acceptée, jamais proposée
RECTIFIEE = 32       # orthographe rectifiée de 1990 (gout, paraitre ; marque « graphie=1990 » de LeXiK)
UTILISATEUR = 64     # mot du dictionnaire de l'utilisateur (jamais dans les données ; ``utilisateur.py``)
NON_VALIDE = 128     # (0.5) forme vue seulement dans la table « Non classé » de LeXiK : jeton de corpus jamais validé
                     # (another, Takada) ; sa fréquence reste consultable, mais elle n'est jamais un mot sûr :
                     # ``validite`` la dit « inconnue », elle sort des homophones, voisins, rimes et recherches

SCHEMA = """
CREATE TABLE formes (id INTEGER PRIMARY KEY, ortho TEXT, min TEXT, zipf REAL, zipf_lemme REAL, drapeaux INTEGER,
                     cles TEXT, anagramme TEXT);
CREATE TABLE cles_phone (id INTEGER PRIMARY KEY, cle TEXT, inverse TEXT);
CREATE TABLE phones (cle INTEGER, forme INTEGER, masquee INTEGER DEFAULT 0, PRIMARY KEY (cle, forme)) WITHOUT ROWID;
CREATE TABLE analyses (forme INTEGER, lemme INTEGER, upos INTEGER, traits INTEGER, phone TEXT, zipf REAL,
                       masquee INTEGER, phone_enrichi TEXT, sources INTEGER, confiance TEXT, syllabes INTEGER,
                       multext INTEGER, marque TEXT);
CREATE TABLE lemmes (id INTEGER PRIMARY KEY, id_lemme TEXT, lemme TEXT, upos TEXT, zipf REAL, masculin TEXT,
                     feminin TEXT, auxiliaire TEXT, pronominal TEXT, groupe INTEGER,
                     auxiliaire_source TEXT, ortho_1990 TEXT);
CREATE TABLE codes (espace TEXT, id INTEGER, valeur TEXT, PRIMARY KEY (espace, id)) WITHOUT ROWID;
CREATE TABLE usuelles (forme INTEGER PRIMARY KEY, usuelle TEXT);
CREATE TABLE voisins (cle INTEGER, forme INTEGER, PRIMARY KEY (cle, forme)) WITHOUT ROWID;
CREATE TABLE voisins_phones (cle INTEGER, phone INTEGER, PRIMARY KEY (cle, phone)) WITHOUT ROWID;
CREATE TABLE metadonnees (cle TEXT PRIMARY KEY, valeur TEXT);
"""
