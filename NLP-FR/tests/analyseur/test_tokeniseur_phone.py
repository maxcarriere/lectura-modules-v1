import pytest

from lectura_nlp_fr.analyseur import NiveauPhone, TypeMot, tokeniser_phone


def formes(chaine, niveau=None):
    return [m.forme for m in tokeniser_phone(chaine, niveau).mots]


def test_niveau_brut():
    doc = tokeniser_phone("le ɑ̃fɑ̃ ʒu")
    assert doc.niveau_phone is NiveauPhone.BRUT
    assert [m.forme for m in doc.mots] == ["le", "ɑ̃fɑ̃", "ʒu"]
    assert [len(m.segments) for m in doc.mots] == [1, 1, 1]


def test_niveau_syllabe():
    doc = tokeniser_phone("le.z‿ɑ̃.fɑ̃ ʒu")
    assert doc.niveau_phone is NiveauPhone.SYLLABE
    assert [m.forme for m in doc.mots] == ["lez", "ɑ̃fɑ̃", "ʒu"]
    assert [m.lie_au_suivant for m in doc.mots] == [True, False, False]
    assert [m.espace_avant for m in doc.mots] == [False, False, True]
    assert doc.mots[0].segments[0].syllabes == ("le",)
    assert doc.mots[0].segments[0].jonction == "z"
    assert doc.mots[1].segments[0].syllabes == ("ɑ̃", "fɑ̃")
    assert doc.texte_de(doc.mots[0]) == "le.z"


def test_liaison_interne_d_un_mot_compose():
    # « ‿ » ne dit pas si la frontière est une espace, un tiret ou une apostrophe.
    assert formes("e.ta.z‿y.ni") == ["etaz", "yni"]
    assert formes("ʒ‿ɛm") == ["ʒ", "ɛm"]


@pytest.mark.parametrize(
    "chaine, attendu",
    [
        ("ʒ'ɛm", ["ʒ'", "ɛm"]),
        ("vø-ty", ["vø", "-ty"]),
        ("a-t-il", ["a", "-t-il"]),
        ("e.taz-y.ni", ["etaz-yni"]),
        ("o.ʒuʁd'ɥi", ["oʒuʁd'ɥi"]),
        ("ʁɑ̃.de-vu", ["ʁɑ̃de-vu"]),
        ("k'ɛ-sə kə", ["k'", "ɛ", "-sə", "kə"]),
        ("-ty", ["-ty"]),
    ],
)
def test_niveau_separe(chaine, attendu):
    doc = tokeniser_phone(chaine)
    assert doc.niveau_phone is NiveauPhone.SEPARE
    assert [m.forme for m in doc.mots] == attendu


def test_segments_et_syllabes_au_niveau_separe():
    (mot,) = tokeniser_phone("e.taz-y.ni").mots
    assert [(s.sep_avant, s.forme, s.syllabes) for s in mot.segments] == [
        ("", "etaz", ("e", "taz")),
        ("-", "yni", ("y", "ni")),
    ]


def test_niveau_separe_avec_syllabation_de_phone():
    # Forme retenue le 2026-10-03 : la syllabation de « phone », « ‿ » remplacé par le séparateur.
    for chaine in ("e.ta.z-y.ni", "e.taz-y.ni"):
        (mot,) = tokeniser_phone(chaine).mots
        assert mot.forme == "etaz-yni"
        assert [(s.sep_avant, s.forme) for s in mot.segments] == [("", "etaz"), ("-", "yni")]
    (mot,) = tokeniser_phone("e.ta.z-y.ni").mots
    assert (mot.segments[0].syllabes, mot.segments[0].jonction) == (("e", "ta"), "z")
    assert (mot.segments[1].syllabes, mot.segments[1].jonction) == (("y", "ni"), "")
    (arc,) = tokeniser_phone("aʁ.k-ɑ̃-sjɛl").mots
    assert [(s.forme, s.syllabes, s.jonction) for s in arc.segments] == [
        ("aʁk", ("aʁ",), "k"),
        ("ɑ̃", (), ""),
        ("sjɛl", (), ""),
    ]
    assert [m.forme for m in tokeniser_phone("tu.t a.fɛ").mots] == ["tut", "afɛ"]
    assert [m.forme for m in tokeniser_phone("o.ʒuʁ.d'ɥi").mots] == ["oʒuʁd'ɥi"]


def test_hors_inventaire_signale():
    doc = tokeniser_phone("le gato bɑto")
    assert [(m.forme, m.type) for m in doc.mots] == [
        ("le", TypeMot.MOT),
        ("gato", TypeMot.INCONNU),
        ("bɑto", TypeMot.INCONNU),
    ]


def test_ponctuation_et_phrases():
    doc = tokeniser_phone("il vjɛ̃. ɛl paʁ ?")
    assert [[m.forme for m in p.mots] for p in doc.phrases] == [["il", "vjɛ̃", "."], ["ɛl", "paʁ", "?"]]
