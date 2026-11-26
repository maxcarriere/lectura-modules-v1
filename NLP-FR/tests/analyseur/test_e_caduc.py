from lectura_nlp_fr.analyseur import IndexMemoire
from lectura_nlp_fr.analyseur.e_caduc import chutes, restaurer, sans_schwas
from lectura_nlp_fr.analyseur.index_phone import ELIDEE, MOT

INDEX = IndexMemoire(
    lectures=[
        ("samədi", MOT, "samədi", 4.5), ("pəti", MOT, "pəti", 5.5), ("pti", MOT, "pti", 3.0),
        ("lə", MOT, "lə", 7.5), ("də", MOT, "də", 7.6), ("d", ELIDEE, "d", 7.0), ("l", ELIDEE, "l", 7.0),
        ("ʒə", MOT, "ʒə", 7.3), ("ʒ", ELIDEE, "ʒ", 6.0), ("sɥi", MOT, "sɥi", 6.0), ("ʃa", MOT, "ʃa", 5.0),
        ("la", MOT, "la", 7.4), ("vwazin", MOT, "vwazin", 4.6), ("wɛst", MOT, "wɛst", 4.5), ("a", MOT, "a", 6.8),
    ],
)


def test_loi_des_trois_consonnes():
    # « samedi, le petit chat de la voisine » : sa.mə.di après pause garde son premier schwa ? non : V C ə C.
    (samedi,), (le, petit, chat, de, la) = chutes([["sa.mə.di"]]), chutes([["lə", " pə.ti", " ʃa", " də", " la"]])
    assert samedi == [0]
    assert (le, petit, de) == ([], [0], [0])            # « lə » en tête de groupe reste ; « lə pti ʃa d la »
    # Trois consonnes : le schwa reste (« vɑ̃.dʁə.di », « pɔm də tɛʁ »).
    assert chutes([["vɑ̃.dʁə.di"]]) == [[]]
    assert chutes([["pɔm", " də", " tɛʁ"]]) == [[], [], []]


def test_resyllabation():
    assert sans_schwas("sa.mə.di", [0]) == "sam.di"
    assert sans_schwas(" pə.ti", [0]) == " pti"
    assert sans_schwas(" də", [0]) == " d"
    assert sans_schwas("pə.ti.z‿", [0]) == "pti.z‿"


def test_schwas_remis_a_l_ecriture():
    assert restaurer("sam.di, lə pti ʃa d la vwa.zin", INDEX) == "samə.di, lə pəti ʃa də la vwa.zin"
    assert restaurer("ʒ sɥi la", INDEX) == "ʒə sɥi la"
    assert restaurer("a l‿wɛst", INDEX) == "a l‿wɛst"        # élision, pas un schwa tombé


def test_schwa_final_et_attaque_maximale():
    from lectura_nlp_fr.analyseur.e_caduc import avec_schwa_final

    assert avec_schwa_final("tabl") == "ta.blə"
    assert avec_schwa_final("paʁl") == "paʁ.lə"
    assert avec_schwa_final(" tɛkst") == " tɛks.tə"
    assert avec_schwa_final("pɔʁt‿") == "pɔʁ.tə‿"
    assert avec_schwa_final("ʃa") == "ʃa"


def test_syllabation_orthographique():
    from lectura_nlp_fr.analyseur.alignement import _syllabation_orthographique

    # « exister » /ɛɡ.zis.te/ : avec x entier, /ɛ.ɡzis.te/.
    exister = [("e", "ɛ", "_"), ("x", "ɡ", "_"), ("_D", "z", "SYL"), ("i", "i", "_"), ("s", "s", "_"), ("t", "t", "SYL")]
    assert _syllabation_orthographique(exister, True, False)[1:3] == [("x", "ɡ", "SYL"), ("_D", "z", "_")]
    # « ballon » /ba.lɔ̃/ : la seconde lettre porte le phonème, la frontière passe entre les deux (« bal|lon »).
    ballon = [("b", "b", "_"), ("a", "a", "_"), ("l", "l", "SYL"), ("l", "_C", "_"), ("o", "ɔ̃", "_"), ("n", "_C", "_")]
    assert _syllabation_orthographique(ballon, False, True)[2:4] == [("l", "_M", "_"), ("l", "l", "SYL")]
    # « accent » : « cc » = /ks/, deux phonèmes, rien ne change.
    accent = [("a", "a", "_"), ("c", "k", "_"), ("c", "s", "SYL"), ("e", "ɑ̃", "_")]
    assert _syllabation_orthographique(accent, False, True) == accent
