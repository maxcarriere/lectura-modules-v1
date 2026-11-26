from pathlib import Path

import pytest

from lectura_nlp_fr.analyseur import IndexMemoire, IndexSqlite, recomposer, tokeniser_phone
from lectura_nlp_fr.analyseur.index_phone import ELIDEE, LIEE, MOT, forme_liee

INDEX = IndexMemoire(
    lectures=[
        ("le", MOT, "le", 7.0), ("lez", LIEE, "le", 7.0),
        ("pəti", MOT, "pəti", 5.5), ("pətit", LIEE, "pəti", 5.5), ("pətit", MOT, "pətit", 5.4),
        ("avɛk", MOT, "avɛk", 6.0), ("ɛl", MOT, "ɛl", 6.0), ("il", MOT, "il", 6.5),
        ("a", MOT, "a", 6.8), ("a", ELIDEE, "a", 3.3), ("at", MOT, "at", 4.3), ("va", MOT, "va", 6.0), ("ɑ̃", MOT, "ɑ̃", 7.0),
        ("ɑ̃fɑ̃", MOT, "ɑ̃fɑ̃", 5.0), ("ami", MOT, "ami", 5.0), ("ɛm", MOT, "ɛm", 5.0),
        ("ʒ", ELIDEE, "ʒ", 6.0), ("ʒysk", ELIDEE, "ʒysk", 4.4),
        ("e", MOT, "e", 7.0), ("et", LIEE, "e", 7.0), ("et", MOT, "et", 1.7),
        ("eta", MOT, "eta", 4.4), ("etaz", LIEE, "eta", 4.4), ("yni", MOT, "yni", 4.0),
        ("ale", MOT, "ale", 5.0), ("vu", MOT, "vu", 6.0),
        ("pø", MOT, "pø", 5.9), ("pøt", LIEE, "pø", 5.9), ("ɛtʁ", MOT, "ɛtʁ", 6.2),
        ("i", MOT, "i", 6.3), ("j", ELIDEE, "j", 3.3),
    ],
    composes=[
        ("e.ta.z-y.ni", 4.9), ("o.ʒuʁ.d'ɥi", 5.2), ("ɡʁɑ̃-pɛʁ", 4.5),
        ("tu.t a fɛ", 4.8), ("pø.t-ɛtʁ", 5.4), ("a.le-vu", 0.0),
    ],
)


def lire(chaine):
    return recomposer(tokeniser_phone(chaine), INDEX).mots


def formes(chaine):
    return [m.forme for m in lire(chaine)]


def test_composes_retrouvent_leurs_separateurs():
    assert formes("o.ʒuʁ.d‿ɥi") == ["oʒuʁd'ɥi"]
    assert formes("e.ta.z‿y.ni") == ["etaz-yni"]
    assert formes("ɡʁɑ̃.pɛʁ") == ["ɡʁɑ̃-pɛʁ"]
    assert formes("ɡʁɑ̃pɛʁ") == ["ɡʁɑ̃-pɛʁ"]
    assert formes("pø.t‿ɛtʁ") == ["pøt-ɛtʁ"]


def test_locution_collee_redevient_plusieurs_mots():
    mots = lire("tu.t‿a.fɛ")
    assert [m.forme for m in mots] == ["tut", "a", "fɛ"]
    assert [m.espace_avant for m in mots] == [False, True, True]


def test_decalages_conserves_apres_recomposition():
    chaine = "il ɛm o.ʒuʁ.d‿ɥi"
    doc = recomposer(tokeniser_phone(chaine), INDEX)
    mot = doc.mots[-1]
    assert chaine[mot.debut : mot.fin] == "o.ʒuʁ.d‿ɥi"
    assert [chaine[s.debut : s.fin] for s in mot.segments] == ["o.ʒuʁ.d", "ɥi"]
    assert [(s.sep_avant, s.forme) for s in mot.segments] == [("", "oʒuʁd"), ("'", "ɥi")]


def test_elision():
    j, aime = lire("ʒ‿ɛm")
    assert (j.forme, j.jonction, j.segments[0].sep_apres) == ("ʒ'", "elision", "'")
    assert aime.forme == "ɛm"
    assert formes("ʒ ɛm") == ["ʒ'", "ɛm"]
    assert formes("ʒys.k‿a") == ["ʒysk'", "a"]


def test_t_euphonique():
    mots = lire("a.t‿il")
    assert [m.forme for m in mots] == ["a", "-t-il"]
    assert [(s.sep_avant, s.forme) for s in mots[1].segments] == [("-", "t"), ("-", "il")]
    assert formes("va.t‿ɑ̃") == ["va", "-t'", "ɑ̃"]


def test_inversion_avec_liaison_laissee_a_l_analyse():
    est, il = lire("e.t‿il")
    assert (est.forme, est.jonction, est.forme_isolee) == ("et", "ambigu", "e")
    assert il.forme == "il"


def test_liaison_enchainement_ambigu():
    les = lire("le.z‿ɑ̃.fɑ̃")[0]
    assert (les.jonction, les.forme_isolee, les.segments[0].jonction) == ("liaison", "le", "z")
    avec = lire("a.vɛ.k‿ɛl")[0]
    assert (avec.jonction, avec.segments[0].syllabes, avec.segments[0].jonction) == ("enchainement", ("a", "vɛk"), "")
    petit = lire("pə.ti.t‿a.mi")[0]
    assert (petit.jonction, petit.forme_isolee) == ("ambigu", "pəti")
    assert lire("ba.z‿a.mi")[0].jonction == "inconnue"


def test_niveau_brut_liaison_a_gauche():
    les, enfants = lire("lez ɑ̃fɑ̃")
    assert (les.jonction, les.forme_isolee) == ("liaison", "le")
    assert lire("pətit ami")[0].jonction == ""


def test_compose_non_atteste_ne_prime_pas_sur_deux_mots():
    assert formes("a.le‿vu") == ["ale", "vu"]


def test_verbe_et_clitiques_colles():
    index = IndexMemoire(lectures=[
        ("puve", MOT, "puve", 5.0), ("dɔn", MOT, "dɔn", 5.0), ("vjɛ̃", MOT, "vjɛ̃", 5.0), ("vjɛ̃t", LIEE, "vjɛ̃", 5.0),
        ("a", MOT, "a", 6.8), ("il", MOT, "il", 6.5),
    ])

    def f(chaine):
        return [(m.forme, m.jonction, m.forme_isolee) for m in recomposer(tokeniser_phone(chaine), index).mots]

    assert f("pu.ve.vu") == [("puve", "", ""), ("-vu", "", "")]
    assert f("dɔn.lə.mwa") == [("dɔn", "", ""), ("-lə", "", ""), ("-mwa", "", "")]
    assert f("vjɛ̃.til") == [("vjɛ̃t", "liaison", "vjɛ̃"), ("-il", "", "")]
    assert f("a.til") == [("a", "", ""), ("-t-il", "", "")]
    assert f("zɔʁ.ɡlyb") == [("zɔʁɡlyb", "", "")]
    chaine = "kə pu.ve.vu"
    doc = recomposer(tokeniser_phone(chaine), index)
    assert [chaine[m.debut : m.fin] for m in doc.mots] == ["kə", "pu.ve", "vu"]
    assert [(s.sep_avant, s.forme) for s in doc.mots[2].segments] == [("-", "vu")]


def test_forme_liee():
    assert forme_liee("pəti", "[t]") == "pətit"
    assert forme_liee("dis", "[s>z]") == "diz"
    assert forme_liee("bɔ̃", "[ɔ̃>ɔn]") == "bɔn"
    assert forme_liee("nœf", "") is None


def _index_reel():
    """Index phonétique des modèles de l'Analyseur (décompressé dans le cache), ou None sans modèles."""
    from lectura_nlp_fr.analyseur.moteur import dossier_modeles, fichier

    d = dossier_modeles()
    return fichier(d, "index_phone.db") if d is not None else None


INDEX_REEL = _index_reel()


@pytest.mark.skipif(INDEX_REEL is None, reason="modèles absents")
def test_avec_le_lexique_reel():
    index = IndexSqlite(INDEX_REEL)

    def f(chaine):
        return [(m.forme, m.jonction) for m in recomposer(tokeniser_phone(chaine), index).mots]

    assert f("o.ʒuʁ.d‿ɥi") == [("oʒuʁd'ɥi", "")]
    assert f("le.z‿e.ta.z‿y.ni") == [("lez", "liaison"), ("etaz-yni", "")]
    assert f("ʒ‿ɛm") == [("ʒ'", "elision"), ("ɛm", "")]
    assert f("a.t‿il") == [("a", ""), ("-t-il", "")]
    assert f("va.t‿ɑ̃") == [("va", ""), ("-t'", "elision"), ("ɑ̃", "")]
    assert f("sɔ̃.t‿a.ʁi.ve") == [("sɔ̃t", "liaison"), ("aʁive", "")]
    assert f("a.vɛ.k‿ɛl") == [("avɛk", "enchainement"), ("ɛl", "")]
    assert f("pə.ti.t‿a.mi") == [("pətit", "ambigu"), ("ami", "")]
    assert f("ɡʁɑ̃pɛʁ") == [("ɡʁɑ̃-pɛʁ", "")]


def test_semi_voyelle_devant_voyelle():
    # « il y a » = i.l‿j‿a : le « y » dit /j/, pas l'élidée familière « y' ».
    assert formes("i.l‿j‿a") == ["il", "i", "a"]
    assert formes("j a") == ["i", "a"]
