# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Chaîne anglaise : jonctions (spec 09), alignement et syllabation, canal phonétique, chaîne de bout en bout sur un
petit lexique et un analyseur factices (sans modèle) ; tests avec les vrais modèles dans ``tests/test_modeles.py``."""

from __future__ import annotations

import pytest

from lectura_nlp_en.analyseur.alignement import MotAligne, PhraseAlignee, colonnes_du_mot
from lectura_nlp_en.analyseur.analyse import Analyse, Couple, Entree
from lectura_nlp_en.analyseur.chaine import Chaine, a_la_casse, partager
from lectura_nlp_en.analyseur.jonctions import clitique, forme_forte, recoupler
from lectura_nlp_en.analyseur.phonetique import assimiler_s, phonemes, sans_marques
from lectura_nlp_en.analyseur.recomposition import recomposer
from lectura_nlp_en.analyseur.structures import NiveauPhone
from lectura_nlp_en.analyseur.tokeniseur import tokeniser_phone


def cs(texte: str) -> tuple[Couple, ...]:
    """« ˈ=. ð=th ə=e » → couples."""
    return tuple(Couple(*x.split("=", 1)) for x in texte.split())


def montre(couples) -> str:
    return " ".join(f"{c.phone}={c.graphe}" for c in couples)


# ── Inventaire ────────────────────────────────────────────────────────────────


def test_phonemes_diphtongues_affriquees():
    assert phonemes("tʃeɪndʒ") == ["tʃ", "eɪ", "n", "dʒ"]
    assert phonemes("ʁ") is None
    assert sans_marques("ˈhæp.i ‿ˌoʊ") == "hæpioʊ"


@pytest.mark.parametrize("hote, attendu", [("ˈbʊʃ", "ɪz"), ("ˈkæt", "s"), ("ˈdʒɑn", "z"), ("ˈdɔɡ", "z"), ("ˈtʃɝtʃ", "ɪz")])
def test_assimilation_s(hote, attendu):
    assert assimiler_s(hote) == attendu


# ── Jonctions ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("couples, nouveau, attendu", [
    ("ð=th ə=e", "ði", "ð=th i=e"),
    ("t=t ə=o", "tu", "t=t u=o"),
    ("f=f ɚ=or", "ˈfɔɹ", "ˈ=. f=f ɔɹ=or"),
    ("k=c ə=a n=n", "ˈkæn", "ˈ=. k=c æ=a n=n"),
    ("=h ɪ=i m=m", "ˈhɪm", "ˈ=. h=h ɪ=i m=m"),
    ("ˌ=. ɪ=i n=n .=. t=t ə=o", "ˈɪn.tu", "ˈ=. ɪ=i n=n .=. t=t u=o"),
])
def test_recoupler(couples, nouveau, attendu):
    assert montre(recoupler(cs(couples), nouveau)) == attendu


def test_formes_fortes():
    assert forme_forte("from", "ADP", "fɹəm") == "ˈfɹʌm"
    assert forme_forte("can", "AUX", "kən") == "ˈkæn"
    assert forme_forte("was", "AUX", "wəz") == "ˈwʌz"
    assert forme_forte("look", "VERB", "ˈlʊk") is None            # déjà accentué


@pytest.mark.parametrize("forme, hote, attendu", [
    ("'s", "ˈbʊʃ", ".=' ɪz=s"), ("'s", "ˈkæt", "‿=' s=s"), ("'s", "ˈdʒɑn", "‿=' z=s"),
    ("'d", "ˈɪt", ".=' əd=d"), ("'d", "aɪ", "‿=' d=d"), ("'ll", "ju", "‿=' l=ll"), ("'ll", "ˈɪt", ".=' əl=ll"),
    ("'re", "ju", "‿=' ɚ=re"), ("n't", "ˈmaɪt", ".=. ən=n ‿=' t=t"), ("'", "ˈwɝ.kɚz", "='"),
])
def test_clitiques(forme, hote, attendu):
    assert montre(clitique(forme, hote)) == attendu


def test_partager_contraction():
    dont = cs("ˈ=. d=d oʊ=o n=n ‿=' t=t")
    do, nt = partager(dont, [2, 3])
    assert montre(do) == "ˈ=. d=d oʊ=o" and montre(nt) == "n=n ‿=' t=t"
    gon, na = partager(cs("ˈ=. ɡ=g ɑ=o .=. n=nn ə=a"), [3, 2])
    assert montre(gon) == "ˈ=. ɡ=g ɑ=o .=. n=n" and montre(na) == "=n ə=a"


def test_a_la_casse():
    assert montre(a_la_casse(cs("ð=th ə=e"), "The")) == "ð=Th ə=e"
    assert a_la_casse(cs("ð=th ə=e"), "Thy") == ()


# ── Alignement et syllabation ─────────────────────────────────────────────────


def test_colonnes_accent_et_doubles():
    happy = cs("ˈ=. h=h æ=a p=pp .=. i=y")
    assert [c[2] for c in colonnes_du_mot(happy)] == ["SYL1", "_", "_", "_", "SYL"]
    from lectura_nlp_en.analyseur.alignement import _doubles

    col = _doubles(colonnes_du_mot(happy))
    assert col[2] == ("p", "p", "_") and col[3] == ("p", "_M", "SYL") and col[4][2] == "_"     # hap.p°y


def test_colonnes_marque_interne():
    exist = cs("ɪ=e ɡˈz=x ɪ=i s=s t=t")
    col = colonnes_du_mot(exist)
    assert col[1] == ("x", "ɡ", "_") and col[2] == ("_D", "z", "SYL1")


# ── Canal phonétique ──────────────────────────────────────────────────────────


def test_tokeniser_phone():
    d = tokeniser_phone("aɪ ˈdoʊn‿t ˈnoʊ, ən‿ˈæp.əl.")
    formes = [m.forme for p in d.phrases for m in p.mots]
    assert formes == ["aɪ", "ˈdoʊn", "t", "ˈnoʊ", ",", "ən", "ˈæp.əl", "."]
    assert d.niveau_phone is NiveauPhone.SYLLABE
    assert tokeniser_phone("aɪ doʊnt noʊ").niveau_phone is NiveauPhone.BRUT


# ── Petit lexique et analyseur factices ───────────────────────────────────────

_LIGNES = [
    # ortho, upos, lemme, phone, couples, zipf
    ("the", "DET", "the", "ðə", "ð=th ə=e", 7.7),
    ("apple", "NOUN", "apple", "ˈæp.əl", "ˈ=. æ=a p=pp .=. əl=le", 4.7),
    ("is", "AUX", "be", "ɪz", "ɪ=i z=s", 7.2),
    ("red", "ADJ", "red", "ˈɹɛd", "ˈ=. ɹ=r ɛ=e d=d", 5.3),
    ("I", "PRON", "I", "aɪ", "aɪ=I", 7.1),
    ("can", "AUX", "can", "kən", "k=c ə=a n=n", 6.5),
    ("can", "NOUN", "can", "ˈkæn", "ˈ=. k=c æ=a n=n", 6.5),
    ("do", "AUX", "do", "du", "d=d u=o", 6.8),
    ("don't", "VERB", "don't", "ˈdoʊn‿t", "ˈ=. d=d oʊ=o n=n ‿=' t=t", 6.1),
    ("n't", "PART", "not", "n‿t", "n=n ‿=' t=t", 6.0),
    ("know", "VERB", "know", "ˈnoʊ", "ˈ=. =k n=n oʊ=ow", 6.3),
    ("Bob", "PROPN", "Bob", "ˈbɑb", "ˈ=. b=B ɑ=o b=b", 4.5),
    ("'s", "PART", "'s", "z", "=' z=s", 6.0),
    ("dog", "NOUN", "dog", "ˈdɔɡ", "ˈ=. d=d ɔ=o ɡ=g", 5.1),
    ("to", "PART", "to", "tə", "t=t ə=o", 7.4),
    ("eat", "VERB", "eat", "ˈit", "ˈ=. i=ea t=t", 5.3),
    ("an", "DET", "a", "ən", "ə=a n=n", 6.3),
    ("hour", "NOUN", "hour", "ˈaʊ.ɚ", "ˈ=. =h aʊ=ou .=. ɚ=r", 5.2),
    ("want", "VERB", "want", "ˈwɔnt", "ˈ=. w=w ɔ=a n=n t=t", 6.0),
]


class Lex:
    def __init__(self):
        self.par_forme, self.par_cle = {}, {}
        for ortho, upos, lemme, phone, couples, zipf in _LIGNES:
            e = Entree(ortho, upos, {}, lemme, phone, cs(couples), zipf)
            self.par_forme.setdefault(ortho.lower(), []).append(e)
            self.par_cle.setdefault(sans_marques(phone), []).append(e)

    def lectures(self, forme):
        return list(self.par_forme.get(forme.lower().replace("’", "'"), []))

    def speciales(self, forme):
        return []

    def homophones(self, phone):
        return list(self.par_cle.get(sans_marques(phone), []))


class Analyseur:
    """UPOS de la première lecture du lexique (AUX pour can) ; en phonétique, pas d'avis."""

    def __init__(self, lex):
        self.lex = lex

    def analyser(self, jetons):
        res = []
        for j in jetons:
            mots = j.mots or (j.forme,)
            res.append([Analyse((self.lex.lectures(m) or [Entree(m, "X", {}, m, "", ())])[0].upos, {}, "") if j.type != "p"
                        else Analyse("PUNCT") for m in mots])
        return res

    def analyser_phone(self, jetons):
        return [[Analyse("X")] for _ in jetons]


@pytest.fixture(scope="module")
def chaine():
    lex = Lex()
    return Chaine(Analyseur(lex), lex, None)


def test_lire_the_devant_voyelle_et_enchainement(chaine):
    (p,) = chaine.lire("The apple is red.")
    assert p.phone == "ði ˈæp.ə.l‿ɪz ˈɹɛd."            # enchaînement resyllabé comme le français
    assert [m.regle for m in p.mots][:1] == ["the_V"]
    assert p.ortho == "The apple is red."
    assert p.separee() == "ði ˈæp.ə.l ɪz ˈɹɛd."            # comme le français « le.z a.mi »


def test_lire_sans_enchainement():
    lex = Lex()
    (p,) = Chaine(Analyseur(lex), lex, None, enchainements=False).lire("The apple is red.")
    assert p.phone == "ði ˈæp.əl ɪz ˈɹɛd."


def test_lire_forme_forte_et_contraction(chaine):
    (p,) = chaine.lire("I don't know. I can.")[:1]
    assert p.phone == "aɪ ˈdoʊn‿t ˈnoʊ."
    (q,) = chaine.lire("I can.")
    assert q.phone == "aɪ ˈkæn."
    assert q.mots[1].regle == "forte" and q.mots[1].phone_enrichi == "kən"


def test_lire_to_devant_voyelle_et_h_muet(chaine):
    (p,) = chaine.lire("I want to eat an hour.")
    assert "tu ˈi.t‿ə.n‿ˈaʊ.ɚ" in p.phone


def test_lire_clitique_compose(chaine):
    (p,) = chaine.lire("Bob's dog.")
    assert p.phone.startswith("ˈbɑb‿z ˈdɔɡ")
    assert p.mots[1].clitique and p.mots[0].jonction == "clitique"


def test_lineaire_trois_lignes(chaine):
    (p,) = chaine.lire("The apple.")
    lignes = p.format_lineaire().splitlines()
    assert len(lignes) == 3 and "SYL1" in lignes[2] and "ENC" not in lignes[2]


def test_ecrire_recomposition_et_formes(chaine):
    (p,) = chaine.ecrire("aɪ ˈdoʊn‿t ˈnoʊ.")
    assert p.ortho == "I don't know."
    (q,) = chaine.ecrire("ði ˈæp.əl‿ɪz ˈɹɛd")
    assert q.ortho == "The apple is red"
    (r,) = chaine.ecrire("ˈbɑb‿z ˈdɔɡ")
    assert r.ortho == "Bob's dog"


def test_ecrire_tolere_l_accent(chaine):
    (p,) = chaine.ecrire("ði æpəl ɪz ɹɛd")
    assert p.ortho == "The apple is red"


def test_recomposition_contraction_et_enchainement():
    lex = Lex()
    d = recomposer(tokeniser_phone("aɪ ˈdoʊn‿t ən‿ˈaʊ.ɚ ˈbɑb‿z"), lex)
    mots = d.phrases[0].mots
    assert [m.forme for m in mots] == ["aɪ", "ˈdoʊn‿t", "ən", "ˈaʊ.ɚ", "ˈbɑb", "z"]
    assert mots[2].jonction == "enchainement" and mots[4].jonction == "clitique" and mots[5].nature == "clitique"


def test_vers_dict(chaine):
    (p,) = chaine.lire("I can.")
    d = p.vers_dict()
    assert d["phone"] == "aɪ ˈkæn." and d["mots"][1]["regle"] == "forte" and d["lineaire"]


def test_phone_sep_doubles(chaine):
    lex = Lex()
    lex.par_forme["happy"] = [Entree("happy", "ADJ", {}, "happy", "ˈhæp.i", cs("ˈ=. h=h æ=a p=pp .=. i=y"), 5.0)]
    (p,) = Chaine(Analyseur(lex), lex, None).lire("happy")
    assert p.separee() == "ˈhæp.i"
    assert p.separee(doubles=True) == "ˈhæp.i"
    assert [c[1:] for c in p.lineaire(doubles=True)][2:4] == [("p", "_"), ("_M", "SYL")]


def test_ecrire_forme_forte_finale():
    lex = Lex()
    lex.par_cle.setdefault("tu", []).append(Entree("two", "NUM", {}, "two", "ˈtu", cs("ˈ=. t=t u=wo"), 6.0))
    (p,) = Chaine(Analyseur(lex), lex, None).ecrire("aɪ ˈwɔnt ˈtu.")
    assert p.ortho == "I want to."


def test_recomposition_enchainement_pas_contraction():
    lex = Lex()
    e = Entree("which's", "PRON", {}, "which's", "ˈwɪtʃ.ɪz", cs("ˈ=. w=w ɪ=i tʃ=ch .=' ɪz=s"), 3.0)
    lex.par_cle["wɪtʃɪz"] = [e]
    d = recomposer(tokeniser_phone("ˈwɪtʃ‿ɪz"), lex)
    assert [m.forme for m in d.phrases[0].mots] == ["ˈwɪtʃ", "ɪz"]


def test_ecrire_enchainement_resyllabe(chaine):
    (q,) = chaine.ecrire("ði ˈæp.ə.l‿ɪz ˈɹɛd")
    assert q.ortho == "The apple is red"
    (r,) = chaine.ecrire("aɪ ˈwɔnt tu ˈi.t‿ə.n‿ˈaʊ.ɚ")
    assert r.ortho == "I want to eat an hour"


def test_forme_forte_devant_not(chaine):
    lex = Lex()
    lex.par_forme["not"] = [Entree("not", "PART", {}, "not", "nɑt", cs("n=n ɑ=o t=t"), 6.5)]
    (p,) = Chaine(Analyseur(lex), lex, None).lire("I can not.")
    assert p.phone == "aɪ ˈkæn nɑt."


def test_formes_fortes_coherentes_avec_le_lexique():
    """La table du Module garde les formes faibles et catégories de NLP_EN/Lexique/tables/formes_faibles.tsv."""
    from pathlib import Path

    from lectura_nlp_en.analyseur.jonctions import FICHIER_FORMES_FORTES

    ref_chemin = Path(__file__).resolve().parents[2] / "Lexique" / "tables" / "formes_faibles.tsv"
    if not ref_chemin.exists():
        pytest.skip("table des formes faibles du lexique absente")
    ref: dict[str, tuple[set, set]] = {}
    for l in ref_chemin.read_text(encoding="utf-8").splitlines():
        if l.startswith("#") or l.startswith("forme\t") or not l.strip():
            continue
        c = l.split("\t")
        cats, faibles = ref.setdefault(c[0], (set(), set()))
        cats.update(c[1].split(","))
        faibles.add(c[4])
    for l in FICHIER_FORMES_FORTES.read_text(encoding="utf-8").splitlines():
        if l.startswith("#") or not l.strip():
            continue
        forme, cats, faible, _forte = l.split("\t")
        assert forme in ref, forme
        assert faible in ref[forme][1] and set(cats.split(",")) == ref[forme][0], forme


def test_sans_etendus():
    from lectura_nlp_en.analyseur.analyse import sans_etendus

    frum = Entree("frum", "ADJ", {}, "frum", "ˈfɹʌm", (), 1.5, niveau="etendu")
    frm = Entree("from", "ADP", {}, "from", "fɹəm", (), 7.0, niveau="noyau")
    assert sans_etendus([frum, frm]) == [frm] and sans_etendus([frum]) == [frum]
