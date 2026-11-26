import random

import pytest

from lectura_nlp_fr.analyseur import TypeMot, tokeniser
from lectura_nlp_fr.analyseur.formules import Date, Heure, Nombre, Ordinal, analyser, ecrire, lire, reconnaitre
from lectura_nlp_fr.analyseur.formules.detection import detecter_formules
from lectura_nlp_fr.analyseur.formules.nombres import ecrire_entier, elements, entier_depuis_elements


@pytest.mark.parametrize(
    "n, attendu",
    [
        (0, "zéro"), (17, "dix-sept"), (21, "vingt et un"), (71, "soixante et onze"),
        (80, "quatre-vingts"), (81, "quatre-vingt-un"), (97, "quatre-vingt-dix-sept"),
        (200, "deux cents"), (201, "deux cent un"), (1000, "mille"), (2024, "deux mille vingt-quatre"),
        (80000, "quatre-vingt mille"), (200000, "deux cent mille"), (80000000, "quatre-vingts millions"),
        (1000000, "un million"),
    ],
)
def test_ecriture_des_entiers(n, attendu):
    assert " ".join(ecrire_entier(n)) == attendu


def test_aller_retour_des_entiers():
    alea = random.Random(0)
    for n in list(range(20000)) + [alea.randrange(10**15) for _ in range(20000)]:
        assert entier_depuis_elements(elements(ecrire_entier(n))) == n


@pytest.mark.parametrize("mots", ["vingt mille cent cent", "un deux trois", "mille mille", "deux un", "septante"])
def test_suites_qui_ne_sont_pas_des_entiers(mots):
    assert entier_depuis_elements(elements(mots.split())) is None


@pytest.mark.parametrize(
    "ecrit, lecture",
    [
        ("42", "quarante-deux"),
        ("12 000", "douze mille"),
        ("-3,5", "moins trois virgule cinq"),
        ("3,05", "trois virgule zéro cinq"),
        ("3,14159", "trois virgule un quatre un cinq neuf"),
        ("007", "zéro zéro sept"),
        ("3e", "troisième"),
        ("21e", "vingt et unième"),
        ("80es", "quatre-vingtièmes"),
        ("3,5 %", "trois virgule cinq pour cent"),
        ("14h30", "quatorze heures trente"),
        ("1h", "une heure"),
        ("21h01", "vingt et une heures une"),
        ("25/12/2024", "vingt-cinq décembre deux mille vingt-quatre"),
        ("01/01/2025", "premier janvier deux mille vingt-cinq"),
        ("25,50 €", "vingt-cinq euros cinquante"),
        ("1 €", "un euro"),
        ("0,50 €", "cinquante centimes"),
        ("2 000 000 $", "deux millions de dollars"),
    ],
)
def test_lecture_et_reconnaissance(ecrit, lecture):
    assert " ".join(lire(ecrit)) == lecture
    # Une heure sans minutes n'est reconnue qu'après un mot qui introduit un moment (« une heure de route » : durée).
    mots = (["à"] if lecture == "une heure" else []) + lecture.split()
    (reconnue,) = reconnaitre(mots)
    assert reconnue.ecriture == ecrit
    assert (reconnue.debut, reconnue.fin) == (len(mots) - len(lecture.split()), len(mots))


def test_pas_de_faux_positif():
    for phrase in ("Une heure de route suffit.", "le mil et le sorgho", "un livre neuf", "il était une fois",
                   "en second lieu", "encore moins un reniement"):
        assert reconnaitre(phrase.split()) == [], phrase
    # Durée : le nombre reste un nombre (style usuel à part), mais pas une heure.
    assert [r.type for r in reconnaitre("trois heures de marche".split())] == ["nombre"]
    assert [r.ecriture for r in reconnaitre("rendez-vous à trois heures".split())] == ["3h"]
    assert [r.ecriture for r in reconnaitre("en dix-neuf cent quatre-vingt-dix".split())] == ["1990"]
    assert [r.ecriture for r in reconnaitre("vers dix heures moins le quart".split())] == ["9h45"]
    assert [r.ecriture for r in reconnaitre("il fait moins cinq".split())] == ["-5"]
    assert [r.ecriture for r in reconnaitre("au moins deux fois".split())] == ["2"]


@pytest.mark.parametrize(
    "ecrit, canonique",
    [("14 h 30", "14h30"), ("9:05", "9h05"), ("24h00", "24h"), ("2024-12-25", "25/12/2024"), ("1.5", "1,5"), ("2ème", "2e")],
)
def test_variantes_d_ecriture(ecrit, canonique):
    assert ecrire(analyser(ecrit).valeur) == canonique


def test_formes_longues_et_valeurs():
    assert analyser("1er").valeur == Ordinal(1)
    assert lire("1res") == ["premières"]
    assert lire("2nde") == ["seconde"]
    assert ecrire(Date(1, 1, 2025), longue=True) == "1er janvier 2025"
    assert analyser("14h").valeur == Heure(14)
    assert analyser("1 234,50").valeur == Nombre("1234", "50")


def test_alignement_sur_la_source():
    source = "12 000,5"
    assert [(m.texte, source[m.debut : m.fin]) for m in analyser(source).lecture] == [
        ("douze", "12"), ("mille", " "), ("virgule", ","), ("cinq", "5"),
    ]
    source = "14 h 05"
    assert [(m.texte, source[m.debut : m.fin], m.composant) for m in analyser(source).lecture] == [
        ("quatorze", "14", 0), ("heures", " h ", 0), ("cinq", "05", 1),
    ]


def elements_lus(source):
    return [(e.texte, source[e.debut : e.fin]) for m in analyser(source).lecture for e in m.elements]


@pytest.mark.parametrize(
    "source, attendu",
    [
        # Exemples relevés sur le module Formules d'origine (span_num).
        ("1234", [("mille", "1"), ("deux", "2"), ("cent", "2"), ("trente", "3"), ("quatre", "4")]),
        ("2000", [("deux", "2000"), ("mille", "2000")]),
        ("200", [("deux", "200"), ("cents", "200")]),
        ("12000", [("douze", "12"), ("mille", "12")]),
        ("1025", [("mille", "1"), ("vingt", "2"), ("cinq", "5")]),
        ("21", [("vingt", "2"), ("et", "1"), ("un", "1")]),
        ("97", [("quatre", "9"), ("vingt", "9"), ("dix", "9"), ("sept", "7")]),
        ("80", [("quatre", "80"), ("vingts", "80")]),
        ("71", [("soixante", "7"), ("et", "1"), ("onze", "1")]),
        ("1005", [("mille", "1"), ("cinq", "5")]),
        ("16", [("seize", "16")]),
        ("1001", [("mille", "1"), ("un", "1")]),
        # Séparateur de milliers écrit : il est lu par le mot d'échelle.
        ("12 000", [("douze", "12"), ("mille", " ")]),
        ("2 000 000", [("deux", "2"), ("millions", " ")]),
        ("1 200", [("mille", "1 "), ("deux", "200"), ("cents", "200")]),
    ],
)
def test_alignement_des_elements(source, attendu):
    assert elements_lus(source) == attendu


def test_alignement_ordinal_et_composants():
    from lectura_nlp_fr.analyseur.formules import plages_par_composant, texte_lu

    assert elements_lus("21e") == [("vingt", "2"), ("et", "1"), ("unième", "1e")]
    assert elements_lus("3e") == [("troisième", "3e")]
    source = "25/12/2024"
    lecture = analyser(source).lecture
    assert [source[d:f] for d, f in plages_par_composant(lecture)] == ["25", "12", "2024"]
    assert [m.composant for m in lecture] == [0, 1, 2, 2, 2]
    texte, places = texte_lu(lecture)
    assert texte == "vingt-cinq décembre deux mille vingt-quatre"
    assert [texte[d:f] for d, f in places][:2] == ["vingt-cinq", "décembre"]
    source = "25,50 €"
    assert [source[d:f] for d, f in plages_par_composant(analyser(source).lecture)] == ["25,50 €", "50"]


def test_aller_retour_par_type():
    alea = random.Random(1)
    for _ in range(3000):
        ecrits = [
            f"{alea.randrange(24)}h{alea.randrange(1, 60):02d}",
            f"{alea.randrange(1, 29):02d}/{alea.randrange(1, 13):02d}/{alea.randrange(1000, 2100)}",
            f"{alea.randrange(2, 5000)}e",
            f"{alea.randrange(1000)},{alea.randrange(1, 100):02d} €",
            f"{alea.randrange(1000)},{alea.randrange(1, 10)} %",
        ]
        for ecrit in ecrits:
            (reconnue,) = reconnaitre(lire(ecrit))
            assert reconnue.ecriture == ecrit, ecrit


def test_mots_seuls_ambigus_non_convertis():
    assert reconnaitre("un livre neuf pour la première fois".split()) == []
    assert [r.ecriture for r in reconnaitre("un et un font deux".split())] == ["2"]


def test_reconnaissance_dans_une_phrase():
    mots = "le premier janvier deux mille vingt-cinq à quatorze heures trente pour vingt-cinq euros cinquante".split()
    assert [(r.type, r.ecriture, mots[r.debut : r.fin]) for r in reconnaitre(mots)] == [
        ("date", "01/01/2025", ["premier", "janvier", "deux", "mille", "vingt-cinq"]),
        ("heure", "14h30", ["quatorze", "heures", "trente"]),
        ("monnaie", "25,50 €", ["vingt-cinq", "euros", "cinquante"]),
    ]


def test_detection_dans_un_document():
    texte = "Il a payé 12 000 € le 25/12/2024 à 14 h 30, soit -3,5 % et CO2."
    doc = detecter_formules(tokeniser(texte))
    formules = [m for m in doc.mots if m.type is TypeMot.FORMULE]
    assert [(texte[m.debut : m.fin], m.type_formule) for m in formules] == [
        ("12 000 €", "monnaie"), ("25/12/2024", "date"), ("14 h 30", "heure"), ("-3,5 %", "pourcentage"), ("CO2", "sigle"),
    ]
    monnaie = formules[0]
    assert [(m.forme, texte[m.debut : m.fin]) for m in monnaie.lecture] == [
        ("douze", "12 000"), ("mille", "12 000"), ("euros", "€"),
    ]
    jour = formules[1].lecture[0]
    assert [(s.forme, texte[s.debut : s.fin]) for s in jour.segments] == [("vingt", "25"), ("cinq", "25")]
    assert [m.composant for m in formules[1].lecture] == [0, 1, 2, 2, 2]
    # Les mots hors formule sont inchangés.
    assert [m.forme for m in doc.mots if m.type is TypeMot.MOT] == ["Il", "a", "payé", "le", "à", "soit", "et"]


def test_reconnaissance_phonetique():
    from lectura_nlp_fr.analyseur import tokeniser_phone
    from lectura_nlp_fr.analyseur.formules import reconnaitre_phone

    def f(chaine):
        mots = tokeniser_phone(chaine).mots
        return [(r.type, r.ecriture, r.debut, r.fin) for r in reconnaitre_phone(mots)]

    assert f("il a dø mil vɛ̃t-katʁ ami") == [("nombre", "2024", 2, 5)]
    assert f("a katɔʁz œʁ tʁɑ̃t") == [("heure", "14h30", 1, 4)]
    assert f("vɛ̃t-sɛ̃k øʁo sɛ̃kɑ̃t") == [("monnaie", "25,50 €", 0, 3)]
    assert f("lə pʁəmje ʒɑ̃vje dø mil vɛ̃t-sɛ̃k") == [("date", "01/01/2025", 1, 6)]
    assert f("tʁwa viʁɡyl sɛ̃k puʁ sɑ̃") == [("pourcentage", "3,5 %", 0, 5)]
    assert f("diz ɑ̃") == []  # « dix » seul : homophone de « dise », laissé à l'analyse
    assert f("sɑ̃ twa") == []
    assert f("katʁə-vɛ̃-diz-nœf") == [("nombre", "99", 0, 1)]
    assert f("katʁəvɛ̃diznœf ɑ̃") == [("nombre", "99", 0, 1)]
    assert f("ɔ̃zœʁ") == []


def test_reconnaissance_phonetique_apres_recomposition():
    from pathlib import Path

    from lectura_nlp_fr.analyseur import IndexSqlite, recomposer, tokeniser_phone
    from lectura_nlp_fr.analyseur.formules import reconnaitre_phone

    from lectura_nlp_fr.analyseur.moteur import dossier_modeles, fichier

    if dossier_modeles() is None:
        pytest.skip("modèles absents")
    index = fichier(dossier_modeles(), "index_phone.db")
    mots = recomposer(tokeniser_phone("vɛ̃t.sɛ̃.k‿ø.ʁo e ka.tʁə.vɛ̃.diz.nœf sɑ̃.tim"), IndexSqlite(index)).mots
    assert [r.ecriture for r in reconnaitre_phone(mots)] == ["25 €", "0,99 €"]


@pytest.mark.parametrize(
    "ecrit, lecture, reconnu",
    [
        ("06 12 34 56 78", "zéro six douze trente-quatre cinquante-six soixante-dix-huit", "06 12 34 56 78"),
        ("0612345678", "zéro six douze trente-quatre cinquante-six soixante-dix-huit", "06 12 34 56 78"),
        ("3/4", "trois quarts", "3/4"),
        ("5/100", "cinq centièmes", "5/100"),
        ("7/250", "sept sur deux cent cinquante", "7/250"),
        ("-2/3", "moins deux tiers", "-2/3"),
        ("12 km", "douze kilomètres", "12 km"),
        ("1,5 km", "un virgule cinq kilomètre", "1,5 km"),
        ("25 °C", "vingt-cinq degrés Celsius", "25 °C"),
        ("100 km/h", "cent kilomètres par heure", "100 km/h"),
        ("10 m²", "dix mètres carrés", "10 m²"),
        ("21 s", "vingt et une secondes", None),
        ("1/2", "un demi", None),
        ("XIV", "quatorze", None),
        ("XIXe", "dix-neuvième", None),
        ("Ier", "premier", None),
        ("Ve", "cinquième", None),
        ("Xe", "dixième", None),
        ("MMXXIV", "deux mille vingt-quatre", None),
        ("B2B", "B deux B", None),
    ],
)
def test_autres_types(ecrit, lecture, reconnu):
    assert " ".join(lire(ecrit)) == lecture
    if reconnu:
        (reconnue,) = reconnaitre(lecture.split())
        assert reconnue.ecriture == reconnu


@pytest.mark.parametrize("ecrit", ["DIX", "OTAN", "MIX", "I", "IIII", "Le", "De", "Ce", "Me"])
def test_non_formules(ecrit):
    formule = analyser(ecrit)
    assert formule is None or formule.fin < len(ecrit)


def test_alignement_par_bloc_des_formules_composees():
    # Dans une formule composée, chaque partie est lue d'un bloc (règle du module d'origine).
    assert elements_lus("25/12/2024") == [
        ("vingt", "25"), ("cinq", "25"), ("décembre", "12"),
        ("deux", "2024"), ("mille", "2024"), ("vingt", "2024"), ("quatre", "2024"),
    ]
    source = "06 12 34 56 78"
    lecture = analyser(source).lecture
    assert [(m.texte, source[m.debut : m.fin], m.composant) for m in lecture] == [
        ("zéro", "06", 0), ("six", "06", 0), ("douze", "12", 1), ("trente-quatre", "34", 2),
        ("cinquante-six", "56", 3), ("soixante-dix-huit", "78", 4),
    ]
    source = "100 km/h"
    assert [(m.texte, source[m.debut : m.fin], m.composant) for m in analyser(source).lecture] == [
        ("cent", "100", 0), ("kilomètres", "km", 1), ("par", "/", 2), ("heure", "h", 2),
    ]


def test_romains_et_sigles_dans_un_document():
    texte = "Louis XIV et le XIXe siècle ; la SNCF, le CD, DIX et M6."
    doc = detecter_formules(tokeniser(texte))
    assert [(texte[m.debut : m.fin], m.type_formule) for m in doc.mots if m.type is TypeMot.FORMULE] == [
        ("XIV", "romain"), ("XIXe", "romain"), ("M6", "sigle"),
    ]
    # SNCF : sigle connu du lexique, reconnu par le tokeniseur et prononcé par le lexique (épelé d'un tenant) ;
    # CD, sans chiffre, n'est plus une formule (1.0.3) : la chaîne le lit par le lexique, ou l'épelle d'un tenant.
    assert {m.forme: m.abregement for m in doc.mots if m.abregement} == {"SNCF": "sigle", "M6": "sigle"}
    m6 = doc.mots[-2]
    assert [(m.forme, m.nature) for m in m6.lecture] == [("M", "lettre"), ("six", "")]


@pytest.mark.parametrize(
    "ecrit, lecture, reconnu",
    [
        ("2+3=5", "deux plus trois égale cinq", "2+3=5"),
        ("2 + 3 = 5", "deux plus trois égale cinq", "2+3=5"),
        ("x²+1", "x au carré plus un", "x²+1"),
        ("3*4", "trois fois quatre", "3×4"),
        ("2x+3=5", "deux x plus trois égale cinq", "2x+3=5"),
        ("f(x)=x^2", "f de x égale x puissance deux", "f(x)=x²"),
        ("f(x+1)", "f de parenthèse ouvrante x plus un parenthèse fermante", "f(x+1)"),
        ("x≤3,5", "x inférieur ou égal à trois virgule cinq", "x≤3,5"),
        ("√9", "racine carrée de neuf", "√9"),
        ("x_1", "x indice un", "x_1"),
        ("sin(x)", "sinus de x", "sin(x)"),
        ("n!/k!", "n factorielle sur k factorielle", "n!/k!"),
        ("1/2+1/3", "un sur deux plus un sur trois", "1/2+1/3"),
        ("-3+5", "moins trois plus cinq", "-3+5"),
        ("α+β", "alpha plus bêta", "α+β"),
        ("(a+b)²", "parenthèse ouvrante a plus b parenthèse fermante au carré", None),
    ],
)
def test_maths(ecrit, lecture, reconnu):
    assert " ".join(lire(ecrit)) == lecture
    if reconnu:
        (reconnue,) = reconnaitre(lecture.split())
        assert (reconnue.type, reconnue.ecriture) == ("maths", reconnu)


@pytest.mark.parametrize("ecrit", ["2x", "1990-2000", "10-3", "5!", "M/Mme", "km/h", "x", "+"])
def test_pas_des_expressions(ecrit):
    formule = analyser(ecrit)
    assert formule is None or formule.type != "maths"


def test_arbre_et_alignement_des_maths():
    from lectura_nlp_fr.analyseur.formules.maths import Bin, Num, Puissance, Var

    formule = analyser("2x²+1=9")
    deux, un, neuf = (Num(Nombre(c)) for c in "219")
    assert formule.valeur == Bin("=", Bin("+", Bin("", deux, Puissance(Var("x"), deux)), un), neuf)
    source = "2x²+1=9"
    assert [(m.texte, source[m.debut : m.fin], m.composant, m.nature) for m in formule.lecture] == [
        ("deux", "2", 0, ""), ("x", "x", 1, "lettre"), ("au", "²", 2, ""), ("carré", "²", 2, ""),
        ("plus", "+", 3, ""), ("un", "1", 4, ""), ("égale", "=", 5, ""), ("neuf", "9", 6, ""),
    ]


def test_priorite_au_type_le_plus_long():
    assert analyser("1/2+1/3").type == "maths"
    assert analyser("3/4").type == "fraction"
    assert analyser("25/12/2024").type == "date"
    assert [(r.type, r.ecriture) for r in reconnaitre("un plus un égale deux".split())] == [("maths", "1+1=2")]
    assert [(r.type, r.ecriture) for r in reconnaitre("deux fois par jour moins trois".split())] == [
        ("nombre", "2"), ("nombre", "3"),          # « moins » adverbe : pas de signe sans mot qui annonce une valeur
    ]


def test_maths_dans_un_document():
    texte = "Si x+1=3 alors f(x)=x², et (a+b)² aussi ; voir (p. 3) et km/h."
    doc = detecter_formules(tokeniser(texte))
    assert [(texte[m.debut : m.fin], m.type_formule) for m in doc.mots if m.type is TypeMot.FORMULE] == [
        ("x+1=3", "maths"), ("f(x)=x²", "maths"), ("(a+b)²", "maths"), ("3", "nombre"), ("/", ""),
    ]


@pytest.mark.parametrize(
    "ecrit, lecture, canonique",
    [
        ("$25", "vingt-cinq dollars", "25 $"),
        ("25€50", "vingt-cinq euros cinquante", "25,50 €"),
        ("€ 1 200", "mille deux cents euros", "1200 €"),
        ("1,5e10", "un virgule cinq fois dix puissance dix", "1,5×10^10"),
        ("3E-5", "trois fois dix puissance moins cinq", "3×10^-5"),
        ("6,02×10^23", "six virgule zéro deux fois dix puissance vingt-trois", "6,02×10^23"),
    ],
)
def test_variantes_monnaie_et_notation_scientifique(ecrit, lecture, canonique):
    assert " ".join(lire(ecrit)) == lecture
    assert ecrire(analyser(ecrit).valeur) == canonique
    (reconnue,) = reconnaitre(lecture.split())
    assert reconnue.ecriture == canonique


def test_alignement_notation_scientifique():
    source = "1,5e-10"
    assert [(m.texte, source[m.debut : m.fin]) for m in analyser(source).lecture] == [
        ("un", "1"), ("virgule", ","), ("cinq", "5"), ("fois", "e"), ("dix", "e"), ("puissance", "e"),
        ("moins", "-10"), ("dix", "-10"),
    ]


def test_briques_raccord_avec_les_formules():
    """Tout ce que les formules lisent vient de la table extraite du lexique."""
    from lectura_nlp_fr.analyseur.formules.briques import briques
    from lectura_nlp_fr.analyseur.formules.nombres import ELEMENTS, _BASES
    from lectura_nlp_fr.analyseur.formules.types import MOIS

    lectures = {e for c in ("nombre", "element") for b in briques(c).values() for e in b.lecture.split("-")}
    assert {_BASES.get(e, e) for e in ELEMENTS} <= lectures
    assert MOIS[0] == "janvier" and MOIS[11] == "décembre" and len(MOIS) == 12
    assert briques("devise")["€"].lecture_pluriel == "euros"
    assert (briques("unite")["h"].lecture, briques("unite")["h"].genre) == ("heure", "f")
    assert briques("lettre")["h"].phone == "aʃ"
    # Chaque brique prise au lexique a une prononciation, sauf lacunes connues du lexique.
    sans = [b.signe for c in ("nombre", "mois", "devise", "lettre") for b in briques(c).values() if not b.phone]
    assert sans == []


@pytest.mark.parametrize(
    "ecrit, lecture, reconnu",
    [
        ("12h30min", "douze heures trente minutes", "12 h 30 min"),
        ("2 h 05 min 10 s", "deux heures cinq minutes dix secondes", "2 h 5 min 10 s"),
        ("3'25\"", "trois minutes vingt-cinq secondes", "3 min 25 s"),
        ("1990-2000", "mille neuf cent quatre-vingt-dix à deux mille", None),
        ("12-15", "douze à quinze", None),
        ("3–2", "trois à deux", None),
    ],
)
def test_durees_et_plages(ecrit, lecture, reconnu):
    assert " ".join(lire(ecrit)) == lecture
    if reconnu:
        (reconnue,) = reconnaitre(lecture.split())
        assert reconnue.ecriture == reconnu


def test_intervalles():
    from lectura_nlp_fr.analyseur.formules import TYPES_CROCHET

    def lu(ecrit):
        return " ".join(m.texte for m in analyser(ecrit, 0, TYPES_CROCHET).lecture)

    assert lu("[0;1]") == "de zéro à un"
    assert lu("]0,5]") == "de zéro à cinq"
    assert lu("[-1;+∞[") == "de moins un à plus l' infini"
    assert lu("]-∞;3,5]") == "de moins l' infini à trois virgule cinq"
    assert analyser("[voir note]", 0, TYPES_CROCHET) is None


def test_formules_rares_dans_un_document():
    texte = "Sur [0;1], pages 12-15, en 1990-2000, durée 2 h 05 min ; score 3-2 [voir note] à 12h30."
    doc = detecter_formules(tokeniser(texte))
    assert [(texte[m.debut : m.fin], m.type_formule) for m in doc.mots if m.type is TypeMot.FORMULE] == [
        ("[0;1]", "intervalle"), ("12-15", "plage"), ("1990-2000", "plage"), ("2 h 05 min", "duree"),
        ("3-2", "plage"), ("12h30", "heure"),
    ]


def test_romains_en_contexte():
    """Chiffre romain sans suffixe : après un nom propre ou un mot de numérotation ; « XXX » (anonymisation de l'oral
    transcrit) n'est pas trente."""
    from lectura_nlp_fr.analyseur import decouper

    def romains(texte):
        return [m.forme for p in decouper(texte) for m in p if m.type == "formule"]

    assert romains("Louis XIV régna.") == ["XIV"]
    assert romains("au chapitre XII") == ["XII"]
    assert romains("le XIXe siècle") == ["XIXe"]
    assert romains("mes deux amies, XXX et Paul") == []


@pytest.mark.parametrize(
    "ecrit, lecture, canonique",
    [
        ("3500 FF", "trois mille cinq cents francs", "3500 FF"),
        ("CHF 20", "vingt francs suisses", "20 CHF"),
        ("2,50 EUR", "deux euros cinquante", "2,50 €"),
        ("5 000 FCFA", "cinq mille francs CFA", "5000 FCFA"),
    ],
)
def test_codes_de_devise_en_lettres(ecrit, lecture, canonique):
    """Code de devise à côté d'un nombre : lu en toutes lettres (le lexique ne l'a qu'épelé)."""
    assert " ".join(lire(ecrit)) == lecture
    assert ecrire(analyser(ecrit).valeur) == canonique


def test_code_de_devise_hors_montant_et_sens_inverse():
    texte = "La FF a payé CHF 20 et 3500 FF."
    doc = detecter_formules(tokeniser(texte))
    assert [(texte[m.debut : m.fin], m.type_formule) for m in doc.mots if m.type is TypeMot.FORMULE] == [
        ("CHF 20", "monnaie"), ("3500 FF", "monnaie"),
    ]
    assert [r.type for r in reconnaitre("trois francs".split())] == ["nombre"]
