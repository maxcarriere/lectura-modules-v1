"""Correctifs manuels (data/correctifs.tsv) et capitales sans accent."""

from lectura_nlp_fr.analyseur import correctifs
from lectura_nlp_fr.analyseur.analyse import Analyse, Couple, Entree
from lectura_nlp_fr.analyseur.chaine import Chaine
from lectura_nlp_fr.analyseur.index_phone import MOT, IndexMemoire

EGLISE = Entree("église", "NOUN", {}, "église", "e.ɡliz", (Couple("e", "é"), Couple(".", "."), Couple("ɡ", "g"),
                                                          Couple("l", "l"), Couple("i", "i"), Couple("z", "se")), 5.0)
ETC = Entree("etc.", "ADV", {}, "etc.", "et.se.te.ʁa", (), 0.0)


class Lexique:
    def __init__(self, entrees):
        self.entrees = entrees

    def lectures(self, forme):
        return [e for e in self.entrees if e.ortho in (forme, forme.lower())]

    def graphies(self, phones):
        return [e for e in self.entrees if e.phone_enrichi in phones]

    def aligner(self, entree):
        return entree


class Analyseur:
    def analyser(self, formes):
        return [Analyse("PUNCT" if f in ".," else "NOUN") for f in formes]


def test_fichier_livre():
    """Le fichier livré se lit (il peut être vide : etc. et Emile, corrigés à la source par LeXiK le 10/10, retirés)."""
    entrees = correctifs.charger()
    assert all(e.phone_enrichi and e.upos for e in entrees)


def test_correctif_prioritaire(tmp_path):
    fichier = tmp_path / "c.tsv"
    fichier.write_text("# commentaire\northo\tupos\ttraits\tlemme\tphone_enrichi\tzipf\tnote\n"
                       "etc.\tADV\t\t\tɛt.se.te.ʁa\t4.5\tessai\n", encoding="utf-8")
    lexique, index = correctifs.appliquer(Lexique([ETC]), IndexMemoire(), fichier)
    assert [e.phone_enrichi for e in lexique.lectures("etc.")] == ["ɛt.se.te.ʁa"]   # remplace l'analyse du lexique
    assert [e.ortho for e in lexique.graphies(["ɛt.se.te.ʁa"])] == ["etc."]
    assert index.prononciations("ɛtseteʁa") == ["ɛt.se.te.ʁa"]
    assert index.lectures("ɛtseteʁa")[MOT].zipf == 4.5


def test_sans_correctif(tmp_path):
    lexique, index = Lexique([ETC]), IndexMemoire()
    assert correctifs.appliquer(lexique, index, tmp_path / "absent.tsv") == (lexique, index)


def test_capitale_sans_accent():
    chaine = Chaine(Analyseur(), Lexique([EGLISE]))
    (phrase,) = chaine.lire("Eglise.")
    mot = phrase.mots[0]
    assert mot.origine == "lexique" and mot.phone_enrichi == "e.ɡliz"
    assert phrase.ortho == "Eglise."                     # le texte garde sa graphie
