# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Mode local, français et anglais, sur les petites bases construites par ``conftest.py``."""

import pytest

from lectura_lexicon import Forme, Lecture, Lexicon, LexiconLocal


def test_mode_local_par_chemin(base_fr, sans_reseau):
    lex = Lexicon(base_fr)
    assert isinstance(lex, LexiconLocal) and isinstance(lex, Lexicon)
    assert lex.mode == "local" and lex.langue == "fr"


def test_mode_local_par_variable(base_fr, sans_reseau, monkeypatch):
    monkeypatch.setenv("LECTURA_LEXICON_DATA", str(base_fr))
    assert isinstance(Lexicon(), LexiconLocal)


def test_validite_frequence(base_fr, sans_reseau):
    lex = Lexicon(base_fr)
    assert lex.existe("chat") and lex.est_valide("maison")
    assert not lex.existe("chta")
    assert lex.validite("chta") == "inconnue"
    assert lex.validite("maison") == "proposable"
    # forme rare d'un lemme courant : acceptée (noyau)
    assert lex.existe("mangeâmes")
    assert lex.frequence("maison") == pytest.approx(5.48, abs=0.01)
    assert lex.frequence("Chat") == lex.frequence("chat")


def test_lectures_et_formes(base_fr, sans_reseau):
    lex = Lexicon(base_fr)
    f = lex.forme("chats")
    assert isinstance(f, Forme) and f.ortho == "chats"
    assert all(isinstance(l, Lecture) for l in f.lectures)
    assert lex.lemmes_de("chats") == ["chat#NOUN"]
    assert lex.phones("verte") == ["vɛʁt"]
    assert {l.ortho for l in lex.formes_de("manger")} >= {"mange", "mangeons", "mangé"}


def test_homophones_rimes_voisins(base_fr, sans_reseau):
    lex = Lexicon(base_fr)
    orthos = [f.ortho for f in lex.homophones("vɛʁ")]
    assert orthos[:3] == ["vers", "verre", "vert"]
    assert "vair" in orthos
    assert [f.ortho for f in lex.homophones("pa.ʁi", propres=False)] == ["pari"]
    rimes = [f.ortho for f in lex.rimes("chanson")]
    assert rimes == ["garçon", "façon"]                      # deux derniers phonèmes : sɔ̃
    assert [f.ortho for f in lex.rimes("chanson", unite="voyelle")] == ["maison", "garçon", "façon", "mangeons"]
    assert "chat" in [f.ortho for f in lex.voisins_orthographiques("chta")]
    assert [f.ortho for f in lex.voisins_phonetiques("vɛʁe", tolerance=1)] == ["vers", "verre", "vert", "verte", "vair"]


def test_conjuguer_variante(base_fr, sans_reseau):
    lex = Lexicon(base_fr)
    c = lex.conjuguer("manger")
    assert c["Ind"]["Pres"]["1p"] == "mangeons"
    assert c["Ind"]["Pres"]["3p"] == "mangent"
    assert c["Inf"]["Pres"]["-"] == "manger"
    assert c["Part"]["Past"]["ms"] == "mangé"
    couples = lex.variante("mangeons", Number="Sing")
    assert ("mangeons", "mange") in [(a.ortho, b.ortho) for a, b in couples]


def test_recherche(base_fr, sans_reseau):
    lex = Lexicon(base_fr)
    assert [f.ortho for f in lex.rechercher("ch*", upos="NOUN", limite=3)] == ["chien", "chat", "chanson"]
    assert [f.ortho for f in lex.rechercher(son="*ɔ̃", syllabes=2, limite=3)] == ["maison", "garçon", "façon"]
    assert [f.ortho for f in lex.filtrer(["chat", "verre", "zzz"], upos="NOUN")] == ["chat", "verre"]
    assert "maire" in [f.ortho for f in lex.anagrammes("aimer")]
    assert lex.syllabes("chanson") == ["ʃɑ̃", "sɔ̃"]


def test_dictionnaire_utilisateur(base_fr, sans_reseau):
    lex = Lexicon(base_fr)
    assert not lex.existe("lecturiel")
    lex.ajouter("lecturiel", "lɛk.ty.ʁjɛl", "NOUN")
    assert lex.existe("lecturiel")
    assert lex.retirer("lecturiel") and not lex.existe("lecturiel")


def test_alias_v0(base_fr, sans_reseau):
    with Lexicon(base_fr) as lex:
        assert lex.phone_de("chat") == "ʃa"
        assert lex.phone_de("zzz") is None
        assert lex.lemme_de("mangeons") == "manger"
        info = lex.info("chats")
        assert info[0]["cgram"] == "NOM" and info[0]["nombre"] == "p" and info[0]["genre"] == "m"
        assert info[0]["freq"] == pytest.approx(12.0, rel=0.03)
        assert "maison" in [f.ortho for f in lex.rimes_par_suffixe("zɔ̃")]
        assert lex.existe_nom_propre("Paris") and not lex.existe_nom_propre("chat")
        assert lex.phone_nom_propre("Paris") == "pa.ʁi"
        assert [f.ortho for f in lex.homophones_nom_propre("paʁi")] == ["Paris"]
        assert lex.decoder_multext("Vmip3s")["mode"] == "indicatif"


def test_fonctions_propres_a_une_langue(base_fr, base_en, sans_reseau):
    fr, en = Lexicon(base_fr), Lexicon(base_en, langue="en")
    assert "rectifiee" in fr.fonctions() and "britannique" not in fr.fonctions()
    with pytest.raises(AttributeError):
        fr.britannique("colour")
    with pytest.raises(AttributeError):
        en.autre_genre("actor")


def test_anglais(base_en, sans_reseau):
    lex = Lexicon(base_en, langue="en")
    assert lex.langue == "en" and lex.existe("cat")
    assert [f.ortho for f in lex.homophones("eɪt")] == ["eight", "ate"]
    assert [f.ortho for f in lex.rimes("nation")][:2] == ["station", "relation"]
    assert lex.rime("nation") == ["eɪ", "ʃ", "ə", "n"]
    assert lex.conjuguer("eat")["Ind"]["Past"]
    assert "silent" in [f.ortho for f in lex.anagrammes("listen")]
    assert not lex.britannique("cat")
    assert lex.phone_de("cat") == "ˈkæt"


def test_sans_base_message_clair(sans_reseau):
    with pytest.raises(FileNotFoundError) as e:
        Lexicon(mode="local")
    message = str(e.value)
    assert "LECTURA_LEXICON_DATA" in message and "convertir" in message and "API" in message
    with pytest.raises(FileNotFoundError) as e:
        Lexicon(mode="local", langue="en")
    assert "LECTURA_LEXICON_EN_DATA" in str(e.value)


def test_langue_inconnue(sans_reseau):
    with pytest.raises(ValueError):
        Lexicon(langue="de")


def test_taille_impose_le_mode_local(sans_reseau):
    with pytest.raises(FileNotFoundError):
        Lexicon(taille="standard")          # jamais de repli silencieux vers l'API quand une taille est demandée


def test_compatibilite_0_5(base_fr, sans_reseau):
    from lectura_lexicon import Dictionnaire, trouver_donnees  # noqa: F401
    from lectura_lexicon.transducer import IndexElargi, brancher  # noqa: F401
    from lectura_lexicon.utilisateur import Dictionnaire as D

    lex = Lexicon(base_fr, dictionnaire=D())
    lex.ajouter("lecturiel", "lɛk.ty.ʁjɛl")
    assert lex.existe("lecturiel") and lex.moteur.chemin == lex.chemin


def test_table_des_lemmes(base_lexik, sans_reseau):
    lex = Lexicon(base_lexik)
    assert lex.groupe("manger") == 1 and lex.groupe("mangeons") == 1          # lemme, ou lemmes de la forme
    assert lex.auxiliaire("manger") == "avoir" and lex.pronominal("manger") == "possible"
    assert lex.est_pronominal("manger") and not lex.est_pronominal("acteur")
    assert lex.groupe("acteur") is None and lex.auxiliaire("zzz") is None
    assert lex.h_aspire("héros") and not lex.h_aspire("acteur")
    info = lex.lemme_info("héros")[0]
    assert info["h_aspire"] and info["upos"] == "NOUN" and info["zipf"] == pytest.approx(4.26, abs=0.01)
    assert lex.lemme_info("acteur")[0]["feminin"] == "actrice"
    assert lex.lemme_info("manger#VERB")[0]["groupe"] == 1
    assert [f.ortho for f in lex.rechercher(groupe=1, limite=5)] == ["manger", "mangé", "mangeons"]
    assert [f.ortho for f in lex.rechercher(auxiliaire="avoir", pronominal=True, limite=5)][:1] == ["manger"]
    assert [f.ortho for f in lex.rechercher(h_aspire=True)] == ["héros"]
    assert [f.ortho for f in lex.filtrer(["héros", "acteur"], h_aspire=False)] == ["acteur"]


def test_table_des_lemmes_base_sans_proprietes(base_fr, base_en, sans_reseau):
    lex = Lexicon(base_fr)
    assert lex.groupe("manger") is None and lex.lemme_info("chat")[0]["zipf"] > 0
    assert lex.rechercher(groupe=1) == []
    assert Lexicon(base_en, langue="en").lemme_info("cat") == [
        {"id_lemme": "cat#NOUN", "lemme": "cat", "upos": "NOUN", "zipf": pytest.approx(4.9, abs=0.1)}]


def test_dir_liste_les_fonctions_deleguees(base_fr, base_en, sans_reseau):
    fr, en = dir(Lexicon(base_fr)), dir(Lexicon(base_en, langue="en"))
    assert {"homophones", "lectures", "conjuguer", "rectifiee", "phone_de", "fermer"} <= set(fr)
    assert "britannique" not in fr and "britannique" in en and "rectifiee" not in en
