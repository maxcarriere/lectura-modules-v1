import pytest

from lectura_nlp_fr.analyseur.liaisons import LECTURE, MINIMALE, SOUTENUE, MotAnalyse, jonction


def m(forme, upos, phone, latente="", lemme="", h=False, **feats):
    return MotAnalyse(forme, upos, phone, latente, h, lemme, feats)


LES = m("les", "DET", "le", "[z]")
ENFANTS = m("enfants", "NOUN", "ɑ̃.fɑ̃", "[z]", Number="Plur")
AMI = m("ami", "NOUN", "a.mi", Number="Sing")
ONT = m("ont", "AUX", "ɔ̃", "[t]", lemme="avoir")
EST = m("est", "AUX", "e", "[t]", lemme="être")

# (gauche, droite, règle, statut, forme liée, réalisée en lecture) — exemples de la table.
CAS = [
    (LES, m("héros", "NOUN", "e.ʁo", "[z]", h=True), "L01", "interdite", "", False),
    (LES, m("onze", "NUM", "ɔ̃z"), "L02", "interdite", "", False),
    (m("et", "CCONJ", "e", "[t]"), m("alors", "ADV", "a.lɔʁ"), "L03", "interdite", "", False),
    (m("soldat", "NOUN", "sɔl.da", "[t]", Number="Sing"), m("anglais", "ADJ", "ɑ̃.ɡlɛ"), "L04", "interdite", "", False),
    (m("Jean", "PROPN", "ʒɑ̃", "[n]"), m("arrive", "VERB", "a.ʁiv"), "L05", "interdite", "", False),
    (m("-ils", "PRON", "il", "[z]"), m("eu", "VERB", "y"), "L06", "interdite", "", False),
    (m("quand", "ADV", "kɑ̃", "[t]"), EST, "L07", "interdite", "", False),
    (LES, ENFANTS, "L10", "obligatoire", "lez", True),
    (m("un", "DET", "œ̃", "[n]"), AMI, "L10", "obligatoire", "œ̃n", True),
    (m("deux", "NUM", "dø", "[z]"), m("ans", "NOUN", "ɑ̃", Number="Plur"), "L11", "obligatoire", "døz", True),
    (m("dix", "NUM", "dis", "[s>z;s>]"), m("hommes", "NOUN", "ɔm", Number="Plur"), "L11", "obligatoire", "diz", True),
    (m("petits", "ADJ", "pə.ti", "[z]"), ENFANTS, "L12", "obligatoire", "pətiz", True),
    (m("bon", "ADJ", "bɔ̃", "[ɔ̃>ɔn]"), AMI, "L12", "obligatoire", "bɔn", True),
    (m("ils", "PRON", "il", "[z]"), ONT, "L13", "obligatoire", "ilz", True),
    (m("nous", "PRON", "nu", "[z]"), m("en", "PRON", "ɑ̃", "[n]"), "L13", "obligatoire", "nuz", True),
    (m("vient", "VERB", "vjɛ̃", "[t]"), m("-il", "PRON", "il"), "L14", "obligatoire", "vjɛ̃t", True),
    (m("chez", "ADP", "ʃe", "[z]"), m("elle", "PRON", "ɛl"), "L15", "obligatoire", "ʃez", True),
    (m("très", "ADV", "tʁɛ", "[z]"), m("utile", "ADJ", "y.til"), "L16", "facultative", "tʁɛz", True),
    (m("quand", "SCONJ", "kɑ̃", "[t]"), m("il", "PRON", "il"), "L17", "obligatoire", "kɑ̃t", True),
    (LES, m("États-Unis", "PROPN", "e.ta.z‿y.ni"), "L10", "obligatoire", "lez", True),
    (m("très", "ADV", "tʁɛ", "[z]"), m("envie", "NOUN", "ɑ̃.vi", Number="Sing"), "L29", "facultative", "tʁɛz", True),
    (m("plus", "ADV", "ply", "[z]"), m("envie", "NOUN", "ɑ̃.vi", Number="Sing"), "L99", "interdite", "", False),
    (m("dont", "PRON", "dɔ̃", "[t]"), m("il", "PRON", "il"), "L18", "facultative", "dɔ̃t", True),
    (EST, m("un", "DET", "œ̃", "[n]"), "L19", "facultative", "et", True),
    (ONT, m("eu", "VERB", "y"), "L20", "facultative", "ɔ̃t", False),
    (m("pas", "ADV", "pa", "[z]"), m("encore", "ADV", "ɑ̃.kɔʁ"), "L21", "facultative", "paz", False),
    (ENFANTS, m("adorables", "ADJ", "a.dɔ.ʁabl"), "L22", "facultative", "ɑ̃fɑ̃z", False),
    (m("après", "ADP", "a.pʁɛ", "[z]"), m("avoir", "AUX", "a.vwaʁ"), "L23", "facultative", "apʁɛz", False),
    (m("mais", "CCONJ", "mɛ", "[z]"), m("enfin", "ADV", "ɑ̃.fɛ̃"), "L24", "facultative", "mɛz", False),
    (m("toujours", "ADV", "tu.ʒuʁ", "[z]"), m("utile", "ADJ", "y.til"), "L25", "facultative", "tuʒuʁz", False),
    (m("vais", "VERB", "vɛ", "[z]"), m("essayer", "VERB", "e.se.je"), "L26", "facultative", "vɛz", False),
    (ENFANTS, ONT, "L27", "facultative", "ɑ̃fɑ̃z", False),
    (m("charmants", "ADJ", "ʃaʁ.mɑ̃", "[z]"), m("et", "CCONJ", "e"), "L28", "facultative", "ʃaʁmɑ̃z", False),
]


@pytest.mark.parametrize("gauche, droite, regle, statut, liee, lue", CAS, ids=[f"{c[0].forme} {c[1].forme}" for c in CAS])
def test_regle_appliquee(gauche, droite, regle, statut, liee, lue):
    j = jonction(gauche, droite)
    assert (j.regle, j.statut, j.forme_liee) == (regle, statut, liee)
    assert j.realisee(LECTURE) is lue


def test_pas_de_liaison_possible():
    # Pas de consonne latente à gauche, ou consonne à l'initiale de droite : aucune règle n'est consultée.
    assert jonction(m("la", "DET", "la"), ENFANTS).regle == ""
    assert jonction(LES, m("chats", "NOUN", "ʃa", Number="Plur")).regle == ""


def test_semi_voyelle_initiale():
    assert jonction(LES, m("oiseaux", "NOUN", "wa.zo", Number="Plur")).forme_liee == "lez"
    assert jonction(LES, m("yeux", "NOUN", "jø", Number="Plur")).forme_liee == "lez"
    assert jonction(LES, m("yaourt", "NOUN", "ja.uʁt", Number="Sing")).statut == "interdite"


def test_politiques():
    j = jonction(ONT, m("eu", "VERB", "y"))
    assert (j.realisee(MINIMALE), j.realisee(LECTURE), j.realisee(SOUTENUE)) == (False, False, True)
    j = jonction(m("très", "ADV", "tʁɛ", "[z]"), m("utile", "ADJ", "y.til"))
    assert (j.realisee(MINIMALE), j.realisee(LECTURE)) == (False, True)
