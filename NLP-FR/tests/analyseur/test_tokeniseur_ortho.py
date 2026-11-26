import pytest

from lectura_nlp_fr.analyseur import TypeMot, tokeniser


def formes(texte):
    return [m.forme for m in tokeniser(texte).mots]


def segments(texte):
    return [[s.forme for s in m.segments] for m in tokeniser(texte).mots if m.type is TypeMot.MOT]


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("j'aime", ["j'", "aime"]),
        ("veux-tu", ["veux", "-tu"]),
        ("l'homme", ["l'", "homme"]),
        ("qu'est-ce que", ["qu'", "est", "-ce", "que"]),
        ("a-t-il", ["a", "-t-il"]),
        ("y a-t-il", ["y", "a", "-t-il"]),
        ("a -t-il", ["a", "-t-il"]),
        ("donne-le-moi", ["donne", "-le", "-moi"]),
        ("allez-vous-en", ["allez", "-vous", "-en"]),
        ("va-t'en", ["va", "-t'", "en"]),
        ("donne-m'en", ["donne", "-m'", "en"]),
        ("cet homme-là", ["cet", "homme", "-là"]),
        ("lorsqu'il", ["lorsqu'", "il"]),
        ("jusqu'à", ["jusqu'", "à"]),
        ("d'aujourd'hui", ["d'", "aujourd'hui"]),
        ("l'arc-en-ciel", ["l'", "arc-en-ciel"]),
        ("s'il", ["s'", "il"]),
        ("L'École", ["L'", "École"]),
        ("N'importe qui", ["N'", "importe", "qui"]),
        ("T'es là", ["T'", "es", "là"]),
    ],
)
def test_suites_de_mots(texte, attendu):
    assert formes(texte) == attendu


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("grand-père", ["grand", "père"]),
        ("aujourd'hui", ["aujourd", "hui"]),
        ("rendez-vous", ["rendez", "vous"]),
        ("Rendez-vous", ["Rendez", "vous"]),
        ("quelqu'un", ["quelqu", "un"]),
        ("c'est-à-dire", ["c", "est", "à", "dire"]),
        ("peut-être", ["peut", "être"]),
        ("celui-ci", ["celui", "ci"]),
        ("États-Unis", ["États", "Unis"]),
        ("prud'homme", ["prud", "homme"]),
        ("porte-bidule", ["porte", "bidule"]),
        ("N'Djamena", ["N", "Djamena"]),
        ("m'sieur", ["m", "sieur"]),
    ],
)
def test_mots_a_plusieurs_segments(texte, attendu):
    assert formes(texte) == [texte]
    assert segments(texte) == [attendu]


def test_separateurs_des_segments():
    (mot,) = tokeniser("c'est-à-dire").mots
    assert [(s.sep_avant, s.forme) for s in mot.segments] == [("", "c"), ("'", "est"), ("-", "à"), ("-", "dire")]
    j, _ = tokeniser("j'aime").mots
    assert (j.segments[0].forme, j.segments[0].sep_apres) == ("j", "'")
    _, tu = tokeniser("veux-tu").mots
    assert (tu.segments[0].sep_avant, tu.segments[0].forme) == ("-", "tu")
    _, til = tokeniser("a-t-il").mots
    assert [(s.sep_avant, s.forme) for s in til.segments] == [("-", "t"), ("-", "il")]


def test_decalages_sur_le_texte_d_origine():
    texte = "Il  dit : « L’homme est‑il là ? »"
    doc = tokeniser(texte)
    for mot in doc.mots:
        assert texte[mot.debut : mot.fin].strip() != ""
        for seg in mot.segments:
            assert doc.texte_de(seg) == seg.forme
    assert [m.forme for m in doc.mots] == ["Il", "dit", ":", "«", "L'", "homme", "est", "-il", "là", "?", "»"]
    l = doc.mots[4]
    assert doc.texte_de(l) == "L’"


def test_forme_normalisee_nfc():
    texte = "été"
    (mot,) = tokeniser(texte).mots
    assert mot.forme == "été"
    assert (mot.debut, mot.fin) == (0, len(texte))


def test_ponctuation_et_guillemets_simples():
    assert formes("'bonjour'") == ["'", "bonjour", "'"]
    assert formes("- Bonjour, dit-il...") == ["-", "Bonjour", ",", "dit", "-il", "..."]
    assert formes("-le chat") == ["-", "le", "chat"]
    types = [m.type for m in tokeniser("Oui !").mots]
    assert types == [TypeMot.MOT, TypeMot.PONCTUATION]


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("3 amis", ["3", "amis"]),
        ("à 14h30.", ["à", "14h30", "."]),
        ("3,5 %", ["3,5", "%"]),
        ("25/12/2024", ["25/12/2024"]),
        ("CO2 et M6", ["CO2", "et", "M6"]),
        ("le 3e, en 2024.", ["le", "3e", ",", "en", "2024", "."]),
    ],
)
def test_formules_brutes(texte, attendu):
    doc = tokeniser(texte)
    assert [m.forme for m in doc.mots] == attendu
    for m in doc.mots:
        assert (m.type is TypeMot.FORMULE) == any(c.isdigit() or c == "%" for c in m.forme)


def test_espace_avant():
    doc = tokeniser("l'ami, lui")
    assert [m.espace_avant for m in doc.mots] == [False, False, False, True]


def test_phrases():
    doc = tokeniser("Il vient. Elle part ?! « Non. » J. Dupont arrive etc. et voilà")
    assert [[m.forme for m in p.mots] for p in doc.phrases] == [
        ["Il", "vient", "."],
        ["Elle", "part", "?", "!"],
        ["«", "Non", ".", "»"],
        ["J.", "Dupont", "arrive", "etc.", "et", "voilà"],
    ]


def _phrases_de(texte):
    return [" ".join(m.forme for m in p.mots) for p in tokeniser(texte).phrases]


def test_abregements():
    assert _phrases_de("César est mort en 44 av. J.-C. à Rome. Auguste lui succède.") == [
        "César est mort en 44 av. J.-C. à Rome .", "Auguste lui succède ."]
    assert _phrases_de("Voir p. 12 et suiv. Le chapitre 3 traite du sujet.") == [
        "Voir p. 12 et suiv .", "Le chapitre 3 traite du sujet ."]     # « suiv » est aussi un mot : point final
    assert _phrases_de("M. Dupont a vu J. R. R. Tolkien à St. Louis.") == ["M. Dupont a vu J. R. R. Tolkien à St. Louis ."]
    assert _phrases_de("La vitamine C. Elle est utile.") == ["La vitamine C .", "Elle est utile ."]
    natures = {m.forme: m.abregement for p in tokeniser("La SNCF, la NASA, Mme Roy, J. Roy, etc. LES DES.").phrases for m in p.mots}
    assert natures["SNCF"] == "sigle" and natures["NASA"] == "acronyme" and natures["Mme"] == "abreviation"
    assert natures["J."] == "initiale" and natures["etc."] == "abreviation" and natures["DES"] == ""


def test_abregements_ambigus():
    # Formes qui sont aussi des mots courants : abrègements seulement dans un contexte sûr (signalé par Modèles).
    natures = {m.forme: m.abregement for p in tokeniser(
        "Son père est venu. Bon, on y va. Il ne viendra pas. Le vol. 3, par ex. la page, le No 5 et St Louis. ET IV."
    ).phrases for m in p.mots}
    assert natures["Son"] == natures["Bon"] == natures["pas"] == natures["ET"] == natures["IV"] == ""
    assert natures["vol."] == natures["ex."] == natures["No"] == natures["St"] == "abreviation"


def test_sigles_a_points():
    natures = {m.forme: m.abregement for p in tokeniser("En tant que R.E.M., la B.C.E. a parlé.").phrases for m in p.mots}
    assert natures["R.E.M."] == natures["B.C.E."] == "sigle"


def test_capitale_seule_en_fin_de_phrase():
    # « S. » de « série S » en fin de phrase : la lettre et le point final, pas « sud » (signalé par Modèles).
    assert [m.forme for m in tokeniser("Je voulais faire S. Puis rien.").mots][:5] == ["Je", "voulais", "faire", "S", "."]
    natures = {m.forme: m.abregement for m in tokeniser("Au S. de la ville, S. Martin.").mots}
    assert natures["S."] in ("abreviation", "initiale")
