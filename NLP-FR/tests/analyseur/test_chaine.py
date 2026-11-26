"""Chaîne de lecture avec un analyseur et un lexique de démonstration (sans modèle ni base)."""

import os
from pathlib import Path

import pytest

from lectura_nlp_fr.analyseur.alignement import decomposer, devant_consonne, enchainer, lier
from lectura_nlp_fr.analyseur.analyse import Analyse, Couple, Entree, choisir
from lectura_nlp_fr.analyseur.chaine import Chaine
from lectura_nlp_fr.analyseur.index_phone import ELIDEE, LIEE, MOT, IndexMemoire, cle_de, forme_liee
from lectura_nlp_fr.analyseur.moteur import dossier_modeles


def c(*paires):
    return tuple(Couple(p, g) for p, g in paires)


def e(ortho, upos, phone, couples=(), lemme="", **feats):
    return Entree(ortho, upos, feats, lemme or ortho, phone, couples)


LEXIQUE = {
    "les": [e("les", "DET", "le[z]", c(("l", "l"), ("e[z]", "es")), "le", Number="Plur")],
    "petits": [e("petits", "ADJ", "pə.ti[z]", c(("p", "p"), ("ə", "e"), (".", "."), ("t", "t"), ("i", "i"), ("", "t"), ("[z]", "s")), "petit")],
    "enfants": [e("enfants", "NOUN", "ɑ̃.fɑ̃[z]", c(("ɑ̃", "en"), (".", "."), ("f", "f"), ("ɑ̃", "an"), ("", "t"), ("[z]", "s")), "enfant", Number="Plur")],
    "héros": [e("héros", "NOUN", "*h*e.ʁo[z]", lemme="héros", Number="Plur")],
    "avec": [e("avec", "ADP", "a.vɛk")],
    "elle": [e("elle", "PRON", "ɛl")],
    "j'": [e("j'", "PRON", "ʒ", c(("ʒ", "j"), ("", "'")), "je")],
    "aime": [e("aime", "VERB", "ɛm", lemme="aimer")],
    "est": [e("est", "AUX", "e[t]", lemme="être"), e("est", "NOUN", "ɛst", Number="Sing")],
    "-il": [e("-il", "PRON", "il", lemme="il")],
    "il": [e("il", "PRON", "il")],
    "tout": [e("tout", "ADV", "tu[t]")],
    "à": [e("à", "ADP", "a")],
    "fait": [e("fait", "NOUN", "fɛ", Number="Sing")],
    "tout à fait": [e("tout à fait", "ADV", "tu.t‿a.fɛ")],
    "dix": [e("dix", "NUM", "dis[s>z;s>]")],
    "amis": [e("amis", "NOUN", "a.mi[z]", lemme="ami", Number="Plur")],
    "livres": [e("livres", "NOUN", "livʁ", lemme="livre", Number="Plur")],
    "quatre": [e("quatre", "NUM", "katʁ")],
    "trois": [e("trois", "NUM", "tʁwa[z]")],
    "euros": [e("euros", "NOUN", "ø.ʁo[z]", lemme="euro", Number="Plur")],
    "un": [e("un", "DET", "œ̃[n]")],
    "soldat": [e("soldat", "NOUN", "sɔl.da[t]", Number="Sing")],
    "anglais": [e("anglais", "ADJ", "ɑ̃.ɡlɛ[z]")],
}
UPOS = {"les": "DET", "petits": "ADJ", "enfants": "NOUN", "héros": "NOUN", "avec": "ADP", "elle": "PRON",
        "j'": "PRON", "aime": "VERB", "est": "AUX", "-il": "PRON", "il": "PRON", "tout": "ADV", "à": "ADP", "fait": "NOUN", "dix": "NUM", "amis": "NOUN", "livres": "NOUN",
        "quatre": "NUM", "trois": "NUM", "euros": "NOUN", "un": "DET", "soldat": "NOUN", "anglais": "ADJ"}
LEMME = {"est": "être"}
TRAITS = {"soldat": {"Number": "Sing"}, "enfants": {"Number": "Plur"}}


def cle(phone_enrichi):
    return cle_de(decomposer(phone_enrichi)[1])


class LexiqueDemo:
    def lectures(self, forme):
        return LEXIQUE.get(forme.lower(), [])

    def graphies(self, phones):
        return [x for entrees in LEXIQUE.values() for x in entrees if cle(x.phone_enrichi) in phones]

    def aligner(self, entree):
        return entree


# Catégorie attendue de chaque prononciation, pour l'analyseur de démonstration en canal phonétique.
UPOS_PHONE = {cle(x.phone_enrichi): x.upos for entrees in LEXIQUE.values() for x in reversed(entrees)}


class AnalyseurDemo:
    def analyser(self, formes):
        return [Analyse(UPOS.get(f.lower(), "PUNCT"), TRAITS.get(f.lower(), {}), LEMME.get(f.lower(), "")) for f in formes]

    def analyser_phone(self, phones):
        return [Analyse(UPOS_PHONE.get(p, "PUNCT")) for p in phones]


def index_demo():
    lectures, vus = [], set()
    for entrees in LEXIQUE.values():
        for x in entrees:
            _h, corps, latente = decomposer(x.phone_enrichi)
            base = cle_de(corps)
            nature = ELIDEE if x.ortho.endswith("'") else MOT
            if not x.ortho.startswith("-") and (base, nature) not in vus:
                vus.add((base, nature))
                lectures.append((base, nature, base, 5.0))
            liee = forme_liee(base, latente) if latente else None
            if liee and (liee, LIEE) not in vus:
                vus.add((liee, LIEE))
                lectures.append((liee, LIEE, base, 5.0))
    return IndexMemoire(lectures)


CHAINE = Chaine(AnalyseurDemo(), LexiqueDemo(), index=index_demo())


def phone(texte):
    return " | ".join(p.phone for p in CHAINE.lire(texte))


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("Les petits enfants", "le pə.ti.z‿ɑ̃.fɑ̃"),
        ("les héros", "le e.ʁo"),
        ("avec elle", "a.vɛ.k‿ɛl"),
        ("J'aime", "ʒ‿ɛm"),
        ("Est-il", "e.t‿il"),
        ("dix amis", "di.z‿a.mi"),
        ("dix livres", "di livʁ"),
        ("dix.", "dis."),
        ("quatre amis", "ka.tʁ‿a.mi"),
        ("un soldat anglais", "œ̃ sɔl.da ɑ̃.ɡlɛ"),
        ("3 euros", "tʁwa.z‿ø.ʁo"),
        ("les enfants, les amis", "le.z‿ɑ̃.fɑ̃, le.z‿a.mi"),
    ],
)
def test_phonetique_de_la_phrase(texte, attendu):
    assert phone(texte) == attendu


def test_alignement_lineaire_et_derivations():
    (phrase,) = CHAINE.lire("Les petits enfants")
    assert phrase.ortho == "Les petits enfants"
    assert [m.jonction for m in phrase.mots] == ["espace", "liaison", "espace"]
    assert phrase.mots[1].regle == "L12"
    # Les couples du lexique sont repris tels quels ; l'espace est un couple.
    assert phrase.couples[:4] == [Couple("l", "L"), Couple("e[z]", "es"), Couple("", " "), Couple("p", "p")]
    assert phrase.mots[0].origine == "lexique"


def test_formule_dans_la_phrase():
    (phrase,) = CHAINE.lire("3 euros")
    formule, euros = phrase.mots
    assert (formule.origine, [lu.mot.forme for lu in formule.lecture]) == ("formule", ["trois"])
    assert formule.lecture[0].jonction == "liaison"          # « trois‿euros » : la formule se lie comme un mot
    assert phrase.couples == [Couple("tʁwa.z‿", "3"), Couple("", " "), Couple("ø.ʁo[z]", "euros")]


def test_mot_compose_a_espace_regroupe():
    # « tout à fait » est dans la liste fermée et sa prononciation porte une liaison propre au mot composé.
    (phrase,) = CHAINE.lire("Il est tout à fait")
    assert [m.mot.forme for m in phrase.mots] == ["Il", "est", "tout à fait"]
    assert phrase.phone.endswith("tu.t‿a.fɛ")
    assert phrase.mots[-1].analyse.upos == "ADV"
    assert phrase.ortho == "Il est tout à fait"


def test_mot_inconnu_signale():
    (phrase,) = CHAINE.lire("les zorglubs")
    assert [m.origine for m in phrase.mots] == ["lexique", "inconnu"]
    assert phrase.phone == "le"


def test_choix_de_la_lecture_par_l_analyse():
    assert choisir(LEXIQUE["est"], Analyse("AUX", lemme="être")).phone_enrichi == "e[t]"
    assert choisir(LEXIQUE["est"], Analyse("NOUN")).phone_enrichi == "ɛst"


def test_marques_et_resyllabation():
    assert decomposer("*h*e.ʁo[z]") == (True, "e.ʁo", "[z]")
    assert decomposer("{ɛ|e}ɡ.zɔ̃.de") == (False, "ɛɡ.zɔ̃.de", "")
    assert decomposer("ɑ̃.kɔʁ(ə)") == (False, "ɑ̃.kɔʁə", "")
    assert lier("le", "[z]") == "le.z‿"
    assert lier("bɔ̃", "[ɔ̃>ɔn]") == "bɔ.n‿"
    assert lier("dis", "[s>z;s>]") == "di.z‿"
    assert devant_consonne("dis", "[s>z;s>]") == "di"
    assert enchainer("a.vɛk") == "a.vɛ.k‿"
    assert enchainer("katʁ") == "ka.tʁ‿"
    assert enchainer("il") == "i.l‿"
    assert enchainer("a.mi") is None


# ── Sens phonétique → orthographe ──────────────────────────────────────────────


def ecrit(chaine, **options):
    return " | ".join(p.ortho for p in CHAINE.ecrire(chaine, **options))


@pytest.mark.parametrize(
    "chaine, attendu",
    [
        ("le.z‿ɑ̃.fɑ̃", "Les enfants"),
        ("le pə.ti.z‿ɑ̃.fɑ̃", "Les petits enfants"),
        ("ʒ‿ɛm le.z‿a.mi", "J'aime les amis"),
        ("e.t‿il a.vɛ.k‿ɛl", "Est-il avec elle"),
        ("lez ɑ̃fɑ̃", "Les enfants"),
        ("le e.ʁo", "Les héros"),
        ("œ̃ sɔl.da ɑ̃.ɡlɛ", "Un soldat anglais"),
    ],
)
def test_orthographe_depuis_la_phonetique(chaine, attendu):
    assert ecrit(chaine) == attendu


def test_formule_reconnue_depuis_la_phonetique():
    assert ecrit("di.z‿a.mi") == "10 amis"
    assert ecrit("di.z‿a.mi", formules=False) == "Dix amis"
    (phrase,) = CHAINE.ecrire("tʁwa.z‿ø.ʁo")
    (formule,) = phrase.mots
    assert (formule.mot.forme, formule.mot.type_formule, len(formule.lecture)) == ("3 €", "monnaie", 2)


def test_alignement_du_sens_inverse():
    (phrase,) = CHAINE.ecrire("le pə.ti.z‿ɑ̃.fɑ̃")
    les, petits, enfants = phrase.mots
    assert petits.jonction == "liaison"
    assert [c.graphe for c in petits.couples] == ["p", "e", ".", "t", "i", "t", "s"]
    assert phrase.phone == "le pə.ti.z‿ɑ̃.fɑ̃"          # la prononciation reçue est conservée


def test_mot_inconnu_en_phonetique():
    (phrase,) = CHAINE.ecrire("le zɔʁ.ɡlyb")
    assert [m.origine for m in phrase.mots] == ["lexique", "inconnu"]
    assert phrase.ortho == "Les "


def test_correction_par_la_chaine():
    pytest.importorskip("lectura_nlp_fr.correcteur.nettoyage", reason="Correcteur : dépendances absentes (numpy)")
    """« Il et parti » : l'analyse (ici fournie) voit un auxiliaire là où est écrit « et »."""
    LEXIQUE["et"] = [e("et", "CCONJ", "e")]
    LEXIQUE["parti"] = [e("parti", "VERB", "paʁ.ti", lemme="partir")]
    LEXIQUE["parti"][0].feats.update(VerbForm="Part")

    class AnalyseurImpose(AnalyseurDemo):
        def analyser_dual(self, formes, phones):
            return [Analyse("AUX", lemme="être") if f == "et" else Analyse(UPOS.get(f.lower(), "PUNCT")) for f in formes]

    chaine = Chaine(AnalyseurImpose(), LexiqueDemo(), index=index_demo())
    (phrase,) = chaine.corriger("Il et parti", confiance=0)
    assert [(c.original, c.remplacement, c.motif) for c in phrase.corrections] == [("et", "est", "grammaire")]
    assert phrase.ortho == "Il est parti"
    # Sans désaccord de catégorie, rien n'est touché.
    (phrase,) = Chaine(AnalyseurDemo(), LexiqueDemo(), index=index_demo()).corriger("Il est parti", confiance=0)
    assert phrase.corrections == [] and phrase.ortho == "Il est parti"
    del LEXIQUE["et"], LEXIQUE["parti"]


def test_modele_de_langue_departage_les_homophones():
    """« il e » : l'analyse ne dit rien (X), le modèle de langue choisit entre « et » et « est » selon les voisins."""

    class LexiqueEtEst(LexiqueDemo):
        def graphies(self, phones):
            return super().graphies(phones) + ([e("et", "CCONJ", "e")] if "e" in phones else [])

    class AnalyseurMuet:
        def analyser_phone(self, phones):
            return [Analyse("X") for _ in phones]

    class Langue:
        def __init__(self, prefere):
            self.prefere = prefere

        def score(self, gauche, candidat, droite):
            return 3.0 if (gauche, candidat) == ("il", self.prefere) else 0.0

    for prefere in ("est", "et"):
        chaine = Chaine(AnalyseurMuet(), LexiqueEtEst(), index=index_demo(), langue=Langue(prefere))
        assert chaine.ecrire("il e a.vɛk")[0].ortho == f"Il {prefere} avec"


def test_format_lineaire_a_trois_lignes():
    (phrase,) = CHAINE.lire("Les petits enfants")
    colonnes = phrase.lineaire()
    # Une colonne par lettre ; la liaison se réalise sur le « s » muet de « petits », qui ouvre une syllabe.
    assert "".join(o for o, _p, _c in colonnes) == "Les petits enfants"
    assert colonnes[:4] == [("L", "l", "_"), ("e", "e", "_"), ("s", "_C", "_"), (" ", " ", "ESP")]
    assert ("s", "z", "SYL") in colonnes and (" ", "‿", "LIA") in colonnes
    assert ("t", "_M", "_") in colonnes
    assert phrase.phone_sep == "le pə.ti.z ɑ̃.fɑ̃"
    assert len(phrase.format_lineaire().splitlines()) == 3


def test_format_lineaire_elision_et_clitique():
    (phrase,) = CHAINE.lire("J'aime les amis")
    assert phrase.lineaire()[1] == ("'", "‿", "APO")
    assert phrase.phone_sep == "ʒ'ɛm le.z a.mi"
    (phrase,) = CHAINE.lire("Est-il avec elle")
    assert ("-", "‿", "LIA") in phrase.lineaire()           # tiret et liaison en /t/ : « e.t-il »
    assert phrase.phone_sep.startswith("e.t-i")


@pytest.mark.parametrize(
    "options, attendus",
    [
        ({}, ["le pə.ti.z‿ɑ̃.fɑ̃", "ʒ‿ɛm le.z‿a.mi", "i.l‿a.vɛ.k‿ɛl"]),
        ({"liaisons": False}, ["le pə.ti ɑ̃.fɑ̃", "ʒ‿ɛm le a.mi", "i.l‿a.vɛ.k‿ɛl"]),
        ({"enchainements": False}, ["le pə.ti.z‿ɑ̃.fɑ̃", "ʒ‿ɛm le.z‿a.mi", "il a.vɛk ɛl"]),
        ({"elisions": False}, ["le pə.ti.z‿ɑ̃.fɑ̃", "ʒ.ɛm le.z‿a.mi", "i.l‿a.vɛ.k‿ɛl"]),
    ],
)
def test_jonctions_desactivables(options, attendus):
    chaine = Chaine(AnalyseurDemo(), LexiqueDemo(), index=index_demo(), **options)
    assert [chaine.lire(t)[0].phone for t in ("Les petits enfants", "J'aime les amis", "Il avec elle")] == attendus


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
def test_ecrire_depuis_un_autre_fil():
    """Le moteur sert dans un autre fil que celui où l'index a été ouvert (serveur : correcteur en fil de travail)."""
    import threading

    from lectura_nlp_fr.analyseur import creer_moteur

    moteur = creer_moteur("local", relecture=False)
    resultat = {}
    fil = threading.Thread(target=lambda: resultat.update(a=moteur.ecrire("la ma.zɔ̃")[0]["ortho"]))
    fil.start(); fil.join()
    assert resultat["a"] == moteur.ecrire("la ma.zɔ̃")[0]["ortho"]


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
@pytest.mark.parametrize("phone, incoherents", [
    ("ɛl fi.nis lœʁ tʁa.vaj.", ("Elle finissent", "Elles finisse ")),      # « finisse » : subjonctif homophone
    ("il di k‿ɛl fi.nis lœʁ tʁa.vaj.", ("elle finissent", "elles finisse ")),
    ("le fam sɔ̃ paʁ.ti. ɛl ʁɑ̃tʁ sə swaʁ.", ("Elle rentrent", "Elles rentre ")),
])
def test_sujet_et_verbe_au_meme_nombre(phone, incoherents):
    from lectura_nlp_fr.analyseur import creer_moteur

    ecrit = " ".join(p["ortho"] for p in creer_moteur("local", relecture=False).ecrire(phone))
    assert not any(x in ecrit for x in incoherents), ecrit
