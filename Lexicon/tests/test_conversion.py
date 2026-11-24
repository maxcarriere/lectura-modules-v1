# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Conversion au format rapide : LeXiK publiée, Lexique 3, GLÀFF, CSV maison (entrées écrites à la main)."""

import sqlite3

import pytest

from conftest import MOTS_FR, ecrire_tableau
from lectura_lexicon import Lexicon, convertir
from lectura_lexicon.__main__ import main
from lectura_lexicon.conversion import detecter, lexique3_vers_api, phone_brut, traits_infover, traits_multext


def test_phone_brut_et_multext():
    assert phone_brut("*h*e.ʁo[z]") == "e.ʁo"
    assert phone_brut("{ɛ|e}ɡ.zɔ̃.de") == "ɛɡ.zɔ̃.de"
    assert traits_multext("Ncms") == "Gender=Masc|Number=Sing"
    assert traits_multext("Vmip3s-") == "Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin"
    assert traits_multext("Vmps-sm") == "Gender=Masc|Number=Sing|Tense=Past|VerbForm=Part"
    assert traits_multext("Vmn----") == "VerbForm=Inf"
    assert traits_multext("Afpfp") == "Gender=Fem|Number=Plur"
    assert lexique3_vers_api("S@sO") == "ʃɑ̃sɔ"
    assert traits_infover("ind:pre:3s;sub:pre:3s;") == [
        "Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin", "Mood=Sub|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin"]


def test_lexik(base_lexik, sans_reseau):
    lex = Lexicon(base_lexik)
    assert lex.existe("acteur") and lex.existe("etc.")
    # indice Zipf de LeXiK : moyenne géométrique des corpus (20, 30, 10 par million → 18,2 → 4,26)
    assert lex.frequence("acteur") == pytest.approx(4.26, abs=0.005)
    # analyse : graphie × part, moyenne géométrique (21, 5, 12 → 10,8 → 4,03)
    assert max(l.zipf for l in lex.lectures("héros")) == pytest.approx(4.03, abs=0.005)
    assert lex.forme("etc.").special
    assert lex.autre_genre("acteur") == ["actrice"] and lex.autre_genre("actrice") == ["acteur"]
    assert lex.rectifiee("gout") and not lex.rectifiee("acteur")
    # formes « non classées » : exclues de toutes les bases (décision du 24/11)
    assert lex.forme("Takada") is None and lex.forme("zzzrien") is None
    # auxiliaire : LeXiK, sinon règle (essentiellement pronominal → être, sinon avoir)
    assert lex.auxiliaire("manger") == "avoir" and lex.lemme_info("manger")[0]["auxiliaire_source"] == "lexik"
    assert lex.auxiliaire("évanouir") == "être" and lex.lemme_info("évanouir")[0]["auxiliaire_source"] == "regle"
    assert lex.lemme_info("gout")[0]["ortho_1990"] == "rectifiee"
    # prononciation brute et enrichie
    l = lex.lectures("héros")[0]
    assert l.phone == "e.ʁo" and l.phone_enrichi == "*h*e.ʁo[z]"
    assert {x.feats for x in lex.lectures("héros")} == {"Gender=Masc|Number=Sing", "Gender=Masc|Number=Plur"}
    # deux analyses sur une ligne, fréquence répartie selon les parts
    m = sorted(lex.lectures("mangeons"), key=lambda x: -x.zipf)
    assert [x.multext for x in m] == ["Vmip1p-", "Vmmp1p-"]
    assert lex.conjuguer("manger")["Part"]["Past"]["ms"] == "mangé"
    assert lex.homophones("mɑ̃ʒe")[0].ortho == "manger"
    meta = dict(sqlite3.connect(base_lexik).execute("SELECT cle, valeur FROM metadonnees"))
    assert meta["format_source"] == "lexik" and "CC BY-SA" in meta["licence"]


def test_detecter(tmp_path):
    t = ecrire_tableau(tmp_path / "m.tsv", MOTS_FR[:3])
    assert detecter(t) == "tableau"
    (tmp_path / "l3.tsv").write_text("ortho\tphon\tlemme\tcgram\tgenre\tnombre\tfreqfilms2\tinfover\n", encoding="utf-8")
    assert detecter(tmp_path / "l3.tsv") == "lexique3"
    (tmp_path / "g.txt").write_text("chat|Ncms|chat|ʃa|Sa|1|1|1|1|1|1|1|1|1|1|1|1\n", encoding="utf-8")
    assert detecter(tmp_path / "g.txt") == "glaff"


def test_lexique3(tmp_path, sans_reseau):
    src = tmp_path / "Lexique383.tsv"
    src.write_text(
        "ortho\tphon\tlemme\tcgram\tgenre\tnombre\tfreqlemfilms2\tfreqlemlivres\tfreqfilms2\tfreqlivres\tinfover\n"
        "chat\tSa\tchat\tNOM\tm\ts\t50\t40\t45\t30\t\n"
        "chats\tSa\tchat\tNOM\tm\tp\t50\t40\t5\t10\t\n"
        "mange\tm@Z\tmanger\tVER\t\t\t100\t80\t40\t20\tind:pre:1s;ind:pre:3s;sub:pre:1s;\n"
        "manger\tm@Ze\tmanger\tVER\t\t\t100\t80\t50\t50\tinf;\n"
        "mangé\tm@Ze\tmanger\tVER\tm\ts\t100\t80\t10\t10\tpar:pas;\n", encoding="utf-8")
    lex = Lexicon(convertir(src, tmp_path / "l3.db"))
    assert lex.phones("chat") == ["ʃa"]
    assert [f.ortho for f in lex.homophones("ʃa")] == ["chat", "chats"]
    c = lex.conjuguer("manger")
    assert c["Ind"]["Pres"]["3s"] == "mange" and c["Sub"]["Pres"]["1s"] == "mange"
    assert c["Part"]["Past"]["ms"] == "mangé" and c["Inf"]["Pres"]["-"] == "manger"
    assert lex.info("chats")[0]["cgram"] == "NOM"


def test_glaff(tmp_path, sans_reseau):
    src = tmp_path / "glaff.txt"
    src.write_text("chat|Ncms|chat|ʃa|Sa|10|1.0|12|1.2|10|1.0|12|1.2|300|30.0|360|36.0\n"
                   "chats|Ncmp|chat|ʃa|Sa|2|0.2|12|1.2|2|0.2|12|1.2|60|6.0|360|36.0\n"
                   "mangeait|Vmii3s|manger|mɑ̃ʒɛ;mɑ̃ʒe|m@ZE;m@Ze|5|0.5|9|0.9|5|0.5|9|0.9|90|9.0|300|30.0\n",
                   encoding="utf-8")
    lex = Lexicon(convertir(src, tmp_path / "glaff.db"))
    assert lex.frequence("chat") == pytest.approx(4.48, abs=0.01)
    assert lex.phones("mangeait") == ["mɑ̃ʒɛ"]
    assert lex.conjuguer("manger")["Ind"]["Imp"]["3s"] == "mangeait"


def test_csv_maison_alias_v0(tmp_path, sans_reseau):
    src = tmp_path / "maison.csv"
    src.write_text("Word,IPA,Lemma,POS,Gender,Number,freq_opensubs\n"
                   "chat,ʃa,chat,NOM,m,s,40\nchatte,ʃat,chatte,NOM,f,s,4\n", encoding="utf-8")
    lex = Lexicon(convertir(src, tmp_path / "csv.db"))
    assert lex.existe("chat") and lex.lectures("chatte")[0].feats == "Gender=Fem|Number=Sing"
    assert lex.lectures("chat")[0].upos == "NOUN"


def test_csv_sans_ortho(tmp_path):
    src = tmp_path / "x.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ortho"):
        convertir(src, tmp_path / "x.db")


def test_format_du_francais_refuse_en_anglais(tmp_path):
    (tmp_path / "l3.tsv").write_text("ortho\tphon\tlemme\tcgram\tfreqfilms2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        convertir(tmp_path / "l3.tsv", tmp_path / "x.db", langue="en")


def test_commande(tmp_path, capsys, sans_reseau):
    src = ecrire_tableau(tmp_path / "m.tsv", MOTS_FR)
    assert main(["convertir", str(src), str(tmp_path / "sortie")]) == 0
    assert (tmp_path / "sortie" / "lexicon.db").exists()
    assert Lexicon(tmp_path / "sortie").existe("chat")       # dossier qui contient lexicon.db
    assert main(["mode"]) == 0
    assert capsys.readouterr().out.strip().endswith("api")
    assert main(["convertir", str(tmp_path / "absent.tsv"), str(tmp_path / "y.db")]) == 1


def test_tailles(tmp_path, sans_reseau):
    """Tailles définies par la fréquence, même schéma : complet (tout), standard (zipf > 0), mini (zipf ≥ seuil)."""
    mots = MOTS_FR + [("zinzolin", "zɛ̃.zɔ.lɛ̃", "zinzolin", "NOUN", "Gender=Masc|Number=Sing", 0.002),   # zipf 0,3
                      ("zyzomys", "zi.zɔ.mis", "zyzomys", "NOUN", "Gender=Masc|Number=Sing", 0.0)]      # jamais vue
    src = ecrire_tableau(tmp_path / "m.tsv", mots)
    complet = Lexicon(convertir(src, tmp_path / "c.db"))
    standard = Lexicon(convertir(src, tmp_path / "s.db", taille="standard"))
    mini = Lexicon(convertir(src, tmp_path / "m.db", taille="mini", seuil=5.0))
    assert (complet.taille, standard.taille, mini.taille) == ("complet", "standard", "mini")
    assert complet.forme("zyzomys") and complet.forme("zinzolin")
    assert standard.forme("zyzomys") is None and standard.validite("zinzolin") == "rare"
    assert standard.forme("mangeâmes") is None                       # fréquence nulle
    assert mini.existe("maison") and mini.forme("chat") is None        # zipf 5,48 / 4,78 au seuil 5
    assert mini.lectures("maison")[0].lemme == "maison"                # toutes les tailles gardent les analyses
    with pytest.raises(ValueError):
        convertir(src, tmp_path / "x.db", taille="moyenne")


def test_non_classes_sur_demande(tmp_path, sans_reseau):
    from conftest import ecrire_lexik

    src = ecrire_lexik(tmp_path / "LeXiK")
    assert Lexicon(convertir(src, tmp_path / "s.db")).forme("Takada") is None
    avec = Lexicon(convertir(src, tmp_path / "n.db", non_classes=True))
    assert avec.non_valide("Takada") and not avec.existe("Takada") and avec.frequence("Takada") > 0
