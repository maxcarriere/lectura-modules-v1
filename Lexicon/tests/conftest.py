# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Petites bases de test construites par les tests eux-mêmes (aucune donnée livrée), et faux serveur d'API local.

Les mots, prononciations et fréquences ci-dessous sont écrits à la main pour les tests ; ils ne viennent d'aucun
lexique publié.
"""

from __future__ import annotations

import gzip
import threading

import pytest

from lectura_lexicon import convertir

# ortho, phone, lemme, upos, feats, freq (par million)
MOTS_FR = [
    ("chat", "ʃa", "chat", "NOUN", "Gender=Masc|Number=Sing", 60.0),
    ("chats", "ʃa", "chat", "NOUN", "Gender=Masc|Number=Plur", 12.0),
    ("chatte", "ʃat", "chatte", "NOUN", "Gender=Fem|Number=Sing", 5.0),
    ("verre", "vɛʁ", "verre", "NOUN", "Gender=Masc|Number=Sing", 40.0),
    ("vers", "vɛʁ", "vers", "ADP", "", 200.0),
    ("vert", "vɛʁ", "vert", "ADJ", "Gender=Masc|Number=Sing", 30.0),
    ("verte", "vɛʁt", "vert", "ADJ", "Gender=Fem|Number=Sing", 15.0),
    ("vair", "vɛʁ", "vair", "NOUN", "Gender=Masc|Number=Sing", 0.2),
    ("chanson", "ʃɑ̃.sɔ̃", "chanson", "NOUN", "Gender=Fem|Number=Sing", 50.0),
    ("façon", "fa.sɔ̃", "façon", "NOUN", "Gender=Fem|Number=Sing", 80.0),
    ("garçon", "ɡaʁ.sɔ̃", "garçon", "NOUN", "Gender=Masc|Number=Sing", 90.0),
    ("maison", "mɛ.zɔ̃", "maison", "NOUN", "Gender=Fem|Number=Sing", 300.0),
    ("aimer", "e.me", "aimer", "VERB", "VerbForm=Inf", 100.0),
    ("maire", "mɛʁ", "maire", "NOUN", "Gender=Masc|Number=Sing", 20.0),
    ("Marie", "ma.ʁi", "Marie", "PROPN", "", 70.0),
    ("Paris", "pa.ʁi", "Paris", "PROPN", "", 150.0),
    ("pari", "pa.ʁi", "pari", "NOUN", "Gender=Masc|Number=Sing", 8.0),
    ("manger", "mɑ̃.ʒe", "manger", "VERB", "VerbForm=Inf", 120.0),
    ("mange", "mɑ̃ʒ", "manger", "VERB", "Mood=Ind|Number=Sing|Person=1|Tense=Pres|VerbForm=Fin", 30.0),
    ("mange", "mɑ̃ʒ", "manger", "VERB", "Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin", 50.0),
    ("manges", "mɑ̃ʒ", "manger", "VERB", "Mood=Ind|Number=Sing|Person=2|Tense=Pres|VerbForm=Fin", 10.0),
    ("mangeons", "mɑ̃.ʒɔ̃", "manger", "VERB", "Mood=Ind|Number=Plur|Person=1|Tense=Pres|VerbForm=Fin", 5.0),
    ("mangez", "mɑ̃.ʒe", "manger", "VERB", "Mood=Ind|Number=Plur|Person=2|Tense=Pres|VerbForm=Fin", 8.0),
    ("mangent", "mɑ̃ʒ", "manger", "VERB", "Mood=Ind|Number=Plur|Person=3|Tense=Pres|VerbForm=Fin", 20.0),
    ("mangeâmes", "mɑ̃.ʒam", "manger", "VERB", "Mood=Ind|Number=Plur|Person=1|Tense=Past|VerbForm=Fin", 0.0),
    ("mangé", "mɑ̃.ʒe", "manger", "VERB", "Gender=Masc|Number=Sing|Tense=Past|VerbForm=Part", 40.0),
    ("chien", "ʃjɛ̃", "chien", "NOUN", "Gender=Masc|Number=Sing", 70.0),
    ("chient", "ʃi", "chier", "VERB", "Mood=Ind|Number=Plur|Person=3|Tense=Pres|VerbForm=Fin", 0.5),
]

MOTS_EN = [
    ("cat", "ˈkæt", "cat", "NOUN", "Number=Sing", 80.0),
    ("cats", "ˈkæts", "cat", "NOUN", "Number=Plur", 20.0),
    ("hat", "ˈhæt", "hat", "NOUN", "Number=Sing", 40.0),
    ("bat", "ˈbæt", "bat", "NOUN", "Number=Sing", 10.0),
    ("nation", "ˈneɪ.ʃən", "nation", "NOUN", "Number=Sing", 50.0),
    ("station", "ˈsteɪ.ʃən", "station", "NOUN", "Number=Sing", 60.0),
    ("relation", "ɹɪˈleɪ.ʃən", "relation", "NOUN", "Number=Sing", 30.0),
    ("eat", "ˈit", "eat", "VERB", "VerbForm=Inf", 90.0),
    ("ate", "ˈeɪt", "eat", "VERB", "Mood=Ind|Tense=Past|VerbForm=Fin", 30.0),
    ("eight", "ˈeɪt", "eight", "NUM", "", 70.0),
    ("eaten", "ˈi.tən", "eat", "VERB", "Tense=Past|VerbForm=Part", 15.0),
    ("eats", "ˈits", "eat", "VERB", "Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin", 20.0),
    ("listen", "ˈlɪ.sən", "listen", "VERB", "VerbForm=Inf", 60.0),
    ("silent", "ˈsaɪ.lənt", "silent", "ADJ", "Degree=Pos", 25.0),
]


def ecrire_tableau(chemin, mots, separateur="\t"):
    lignes = [separateur.join(("ortho", "phone", "lemme", "upos", "feats", "freq"))]
    lignes += [separateur.join((o, p, l, u, f, str(q))) for o, p, l, u, f, q in mots]
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return chemin


def ecrire_lexik(dossier):
    """Dossier au format des fichiers publiés de LeXiK (mêmes colonnes), avec quelques entrées écrites à la main."""
    dossier.mkdir(parents=True, exist_ok=True)
    entete = ("ortho\tlemme\tid_lemme\tupos\tmultext\tphone\talignement\torthocode\tcomposition\tfreq_opensubtitles\t"
              "freq_wikipedia\tfreq_gutenberg\tparts_opensubtitles\tparts_wikipedia\tparts_gutenberg\tconfiance")
    lignes = [
        "acteur\tacteur\tacteur#NOUN\tNOUN\tNcms\tak.tœʁ\t\t\t\t20.0\t30.0\t10.0\t1.000\t1.000\t1.000\tA",
        "actrice\tactrice\tactrice#NOUN\tNOUN\tNcfs\tak.tʁis\t\t\t\t10.0\t5.0\t2.0\t1.000\t1.000\t1.000\tA",
        "héros\théros\théros#NOUN\tNOUN\tNcms;Ncmp\t*h*e.ʁo[z]\t\t\t\t30.0\t10.0\t20.0\t0.700;0.300\t0.500;0.500\t0.600;0.400\tA",
        "mangeons\tmanger\tmanger#VERB\tVERB\tVmip1p-;Vmmp1p-\tmɑ̃.ʒɔ̃[z]\t\t\t\t4.0\t0.1\t2.0\t0.800;0.200\t1.000;0.000\t0.900;0.100\tA",
        "mangé\tmanger\tmanger#VERB\tVERB\tVmps-sm\tmɑ̃.ʒe\t\t\t\t50.0\t20.0\t30.0\t1.000\t1.000\t1.000\tA",
        "manger\tmanger\tmanger#VERB\tVERB\tVmn----\tmɑ̃.ʒe\t\t\t\t100.0\t50.0\t80.0\t1.000\t1.000\t1.000\tA",
        "gout\tgout\tgout#NOUN\tNOUN\tNcms\tɡu\t\t\t\t1.0\t0.5\t\t1.000\t1.000\t\tB",
        "évanouir\tévanouir\tévanouir#VERB\tVERB\tVmn----\te.va.nwiʁ\t\t\t\t2.0\t1.0\t3.0\t1.000\t1.000\t1.000\tA",
    ]
    with gzip.open(dossier / "lexik_formes_mots.tsv.gz", "wt", encoding="utf-8") as f:
        f.write(entete + "\n" + "\n".join(lignes) + "\n")
    with gzip.open(dossier / "lexik_formes_speciaux.tsv.gz", "wt", encoding="utf-8") as f:
        f.write("ortho\tupos\tmultext\tphone\talignement\torthocode\ttype\tdeveloppement\tdeveloppement_pluriel\t"
                "proprietes\tfreq_opensubtitles\tfreq_wikipedia\tfreq_gutenberg\tconfiance\n"
                "etc.\tADV\tRgp\tɛt.se.te.ʁa\t\t\tabréviation\tet cetera\t\t\t5.0\t9.0\t3.0\tT\n")
    with gzip.open(dossier / "lexik_formes_non_classes.tsv.gz", "wt", encoding="utf-8") as f:
        f.write("ortho\tlemme\tupos\tmultext\tphone\ttype\tproprietes\tfreq_opensubtitles\tfreq_wikipedia\t"
                "freq_gutenberg\tparts_opensubtitles\tparts_wikipedia\tparts_gutenberg\tconfiance\n"
                "Takada\tTakada\tPROPN\tNp\tta.ka.da\t\t\t0.3\t\t\t\t\t\tG\n"
                "zzzrien\tzzzrien\tNOUN\tNcms\tzʁjɛ̃\t\t\t\t\t\t\t\t\tG\n")
    with gzip.open(dossier / "lexik_lemmes.tsv.gz", "wt", encoding="utf-8") as f:
        f.write("id_lemme\tlemme\tupos\tproprietes\tfreq_opensubtitles\tfreq_wikipedia\tfreq_gutenberg\n"
                "acteur#NOUN\tacteur\tNOUN\tgenre:m;feminin:actrice\t30.0\t40.0\t12.0\n"
                "actrice#NOUN\tactrice\tNOUN\tgenre:f;masculin:acteur\t12.0\t6.0\t3.0\n"
                "manger#VERB\tmanger\tVERB\tgroupe:1;auxiliaire:avoir;pronominal:possible;transitivite:td,i\t300.0\t100.0\t200.0\n"
                "héros#NOUN\théros\tNOUN\tgenre:m;invariable:oui\t30.0\t10.0\t20.0\n"
                "gout#NOUN\tgout\tNOUN\tgenre:m;ortho_1990:rectifiee\t1.0\t0.5\t\n"
                "évanouir#VERB\tévanouir\tVERB\tgroupe:2;pronominal:essentiel\t\t\t\n")
    (dossier / "provenance").mkdir(exist_ok=True)
    with gzip.open(dossier / "provenance" / "lexik_provenance.tsv.gz", "wt", encoding="utf-8") as f:
        f.write("ortho\tlemme\tupos\tphone\tconfiance\tsources\tcandidates\tregles\tcorrections\tmarques\n"
                "gout\tgout\tNOUN\tɡu\tB\tcadre\t\t\t\tgraphie=1990\n")
    return dossier


@pytest.fixture(scope="session")
def base_fr(tmp_path_factory):
    d = tmp_path_factory.mktemp("fr")
    return convertir(ecrire_tableau(d / "mots.tsv", MOTS_FR), d / "base" / "lexicon.db", langue="fr")


@pytest.fixture(scope="session")
def base_en(tmp_path_factory):
    d = tmp_path_factory.mktemp("en")
    return convertir(ecrire_tableau(d / "words.tsv", MOTS_EN), d / "base" / "lexicon.db", langue="en")


@pytest.fixture(scope="session")
def base_lexik(tmp_path_factory):
    d = tmp_path_factory.mktemp("lexik")
    return convertir(ecrire_lexik(d / "LeXiK"), d / "base" / "lexicon.db")


@pytest.fixture()
def sans_reseau(monkeypatch, tmp_path):
    """Environnement propre : aucune variable Lectura, HOME vide (aucune base installée)."""
    for v in ("LECTURA_LEXICON_DATA", "LECTURA_LEXICON_EN_DATA", "LECTURA_MODELS_DIR", "LECTURA_LEXICON_MODE",
              "LECTURA_LEXICON_API", "LECTURA_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture(scope="session")
def serveur(base_fr, base_en):
    """Faux serveur d'API sur 127.0.0.1 (port libre), qui suit la spécification des routes ``/v1/lexique``."""
    from serveur_factice import demarrer

    srv, url = demarrer({"fr": base_fr, "en": base_en})
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield url
    srv.shutdown()
