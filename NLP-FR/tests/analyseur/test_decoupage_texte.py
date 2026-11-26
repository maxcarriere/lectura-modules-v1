from lectura_nlp_fr.analyseur import TYPES_DE_FORMULE, decouper


def test_interface_stable():
    (phrase,) = decouper("Il a payé 25,50 € à 14h30, n'est-ce pas ?")
    assert [(m.forme, m.type) for m in phrase][:4] == [("Il", "mot"), ("a", "mot"), ("payé", "mot"), ("25,50 €", "formule")]
    monnaie = phrase[3]
    assert monnaie.type_formule == "monnaie" and monnaie.lecture == ("vingt-cinq", "euros", "cinquante")
    assert len(monnaie.composants) == len(monnaie.lecture)
    assert phrase[5].type_formule == "heure" and phrase[5].lecture == ("quatorze", "heures", "trente")
    assert [m.forme for m in phrase][-5:] == ["n'", "est", "-ce", "pas", "?"]
    assert phrase[-1].type == "ponctuation" and phrase[6].type == "ponctuation"
    assert {"nombre", "heure", "date", "monnaie", "mesure", "sigle", "romain", "maths"} <= set(TYPES_DE_FORMULE)


def test_phrases_et_positions():
    texte = "J'aime l'école. Il pleut."
    phrases = decouper(texte)
    assert len(phrases) == 2
    assert [texte[m.debut : m.fin] for m in phrases[0]] == ["J'", "aime", "l'", "école", "."]


def test_abregements_et_dates():
    from lectura_nlp_fr.analyseur.decoupage_texte import VERSION

    assert VERSION == "4"
    (phrase,) = decouper("La SNCF, la NASA et M. Roy, en 44 av. J.-C., le 14 juil. 1789.")
    vus = {m.forme: (m.type, m.type_formule, m.lecture) for m in phrase}
    assert vus["SNCF"] == ("abregement", "sigle", ("S", "N", "C", "F"))
    assert vus["NASA"] == ("abregement", "acronyme", ("NASA",))
    assert vus["M."] == ("abregement", "abreviation", ("monsieur",))
    assert vus["av. J.-C."] == ("abregement", "abreviation", ("avant", "Jésus-Christ"))
    assert vus["14 juil. 1789"][:2] == ("formule", "date")


def test_m_point_toujours_monsieur():
    # « M. » se lit toujours « monsieur » (consigne de l'utilisateur), quel que soit le contexte.
    for texte in ("M. Dupont est là.", "M. le maire est arrivé.", "J'ai vu M. et Mme Roy.", "Bonjour M. Il fait beau."):
        lus = [m for p in decouper(texte) for m in p if m.forme == "M."]
        assert lus and all(m.type_formule == "abreviation" and m.lecture == ("monsieur",) for m in lus)
