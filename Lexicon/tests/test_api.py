# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Mode API contre un faux serveur local (127.0.0.1) : aucun appel au réseau réel."""

import urllib.request

import pytest

import serveur_factice
from lectura_lexicon import ErreurAPI, Lexicon, LexiconAPI, QuotaDepasse
from lectura_lexicon.api import API_PAR_DEFAUT


@pytest.fixture(autouse=True)
def interdire_reseau_reel(monkeypatch):
    """Toute requête hors de 127.0.0.1 fait échouer le test."""
    origine = urllib.request.urlopen

    def garde(requete, *args, **kwargs):
        url = requete.full_url if hasattr(requete, "full_url") else str(requete)
        assert url.startswith("http://127.0.0.1:"), f"appel réseau réel interdit dans les tests : {url}"
        return origine(requete, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", garde)


def test_mode_api_par_defaut(sans_reseau):
    lex = Lexicon()
    assert isinstance(lex, LexiconAPI) and lex.mode == "api"
    assert lex.api == API_PAR_DEFAUT + "/v1/lexique"


def test_adresse_par_variable(sans_reseau, monkeypatch, serveur):
    monkeypatch.setenv("LECTURA_LEXICON_API", serveur)
    assert Lexicon().api == serveur + "/v1/lexique"


def test_mode_force(sans_reseau, monkeypatch, base_fr):
    monkeypatch.setenv("LECTURA_LEXICON_DATA", str(base_fr))
    assert isinstance(Lexicon(mode="api"), LexiconAPI)
    monkeypatch.setenv("LECTURA_LEXICON_MODE", "api")
    assert isinstance(Lexicon(), LexiconAPI)


NOMS = ["chat", "chats", "Chat", "maison", "mangeons", "vair", "zzz", "mangeâmes", "Paris", "verte"]


@pytest.mark.parametrize("fonction", ["validite", "existe", "est_valide", "non_valide", "usuelle", "frequence",
                                      "forme", "lectures", "phones", "lemmes_de", "syllabes", "rectifiee",
                                      "phone_de", "lemme_de", "info", "existe_nom_propre"])
def test_api_egale_local_par_forme(fonction, base_fr, serveur, sans_reseau):
    local, distant = Lexicon(base_fr), Lexicon(api=serveur)
    for mot in NOMS:
        assert getattr(distant, fonction)(mot) == getattr(local, fonction)(mot), (fonction, mot)


def test_api_egale_local_listes(base_fr, serveur, sans_reseau):
    local, distant = Lexicon(base_fr), Lexicon(api=serveur)
    appels = [
        ("homophones", ("vɛʁ",), {}), ("homophones", ("vɛʁ",), {"propres": False, "casse": "regrouper"}),
        ("voisins_orthographiques", ("chta",), {}), ("voisins_phonetiques", ("vɛʁ",), {"limite": 5}),
        ("formes_de", ("manger",), {}), ("formes_de", ("manger",), {"upos": "VERB"}),
        ("rimes", ("chanson",), {}), ("rimes", (), {"phone": "sɔ̃", "unite": "voyelle"}),
        ("rechercher", ("ch*",), {"upos": "NOUN"}), ("rechercher", (), {"son": "*ɔ̃", "limite": 3}),
        ("filtrer", (["chat", "verre", "zzz"],), {"upos": "NOUN"}), ("contient_son", ("ʒ",), {}),
        ("mots_par_syllabes", (2,), {}), ("anagrammes", ("aimer",), {}), ("conjuguer", ("manger",), {}),
        ("autre_genre", ("chat",), {}), ("rimes_par_suffixe", ("zɔ̃",), {}), ("homophones_nom_propre", ("paʁi",), {}),
        ("lemme_info", ("manger",), {}), ("groupe", ("manger",), {}), ("auxiliaire", ("manger",), {}),
        ("pronominal", ("manger",), {}), ("est_pronominal", ("manger",), {}), ("h_aspire", ("chat",), {}),
        ("rechercher", ("m*",), {"h_aspire": False, "limite": 5}),
    ]
    for nom, args, kwargs in appels:
        assert getattr(distant, nom)(*args, **kwargs) == getattr(local, nom)(*args, **kwargs), nom
    v_local, v_api = local.variante("mangeons", Number="Sing"), distant.variante("mangeons", Number="Sing")
    assert v_api == v_local and all(isinstance(c, tuple) for c in v_api)
    # les Forme reçues portent leurs lectures
    f = distant.forme("chats")
    assert f.lectures and f.lectures[0].sources == () and f == local.forme("chats")


def test_filtrer_accepte_des_formes(base_fr, serveur, sans_reseau):
    distant = Lexicon(api=serveur)
    formes = distant.rechercher("ch*", limite=5)
    assert [f.ortho for f in distant.filtrer(formes, upos="NOUN")] == [f.ortho for f in formes if f.ortho != "chient"]


def test_anglais_api(base_en, serveur, sans_reseau):
    local, distant = Lexicon(base_en, langue="en"), Lexicon(langue="en", api=serveur)
    for nom, args in [("homophones", ("eɪt",)), ("rimes", ("nation",)), ("rime", ("nation",)),
                      ("britannique", ("cat",)), ("americaine", ("cat",)), ("britanniques", ("color",)),
                      ("conjuguer", ("eat",)), ("anagrammes", ("listen",)), ("phone_de", ("cat",)),
                      ("lemme_info", ("eat",))]:
        assert getattr(distant, nom)(*args) == getattr(local, nom)(*args), nom
    with pytest.raises(AttributeError):
        distant.rectifiee("gout")


def test_requete_envoyee(serveur, sans_reseau):
    serveur_factice.APPELS.clear()
    lex = Lexicon(api=serveur)
    lex.homophones("ʃa", propres=False)
    lex.homophones("ʃa", propres=False)           # réponse gardée en cache : un seul appel
    assert serveur_factice.APPELS == [("fr", "homophones", {"phone": "ʃa", "propres": False})]


def test_infos(serveur, sans_reseau):
    infos = Lexicon(api=serveur).infos()
    assert infos["langue"] == "fr" and "homophones" in infos["fonctions"]


def test_erreurs(serveur, sans_reseau, monkeypatch):
    lex = Lexicon(api=serveur)
    with pytest.raises(ValueError):
        lex.homophones("ʃa", inconnu=1)              # 422 → ValueError
    with pytest.raises(ValueError):
        lex.rimes("chanson", unite="lettres")          # 422 (ValueError du moteur)
    with pytest.raises(NotImplementedError):
        lex.ajouter("lecturiel")
    with pytest.raises(ValueError):
        Lexicon(api=serveur, seuils=object())
    hors_ligne = Lexicon(api="http://127.0.0.1:9", delai=2)
    with pytest.raises(ErreurAPI):
        hors_ligne.existe("chat")
    origine = urllib.request.Request.__init__

    def avec_quota(self, url, *a, headers=None, **k):
        origine(self, url, *a, headers={**(headers or {}), "X-Test-Quota": "1"}, **k)

    monkeypatch.setattr(urllib.request.Request, "__init__", avec_quota)
    with pytest.raises(QuotaDepasse):
        Lexicon(api=serveur).existe("maison")


def test_cle_envoyee(serveur, sans_reseau, monkeypatch):
    vues = []
    origine = urllib.request.urlopen

    def espion(requete, *a, **k):
        vues.append(requete.get_header("Authorization"))
        return origine(requete, *a, **k)

    monkeypatch.setattr(urllib.request, "urlopen", espion)
    Lexicon(api=serveur).existe("chat")
    Lexicon(api=serveur, cle="secret-de-test").existe("maison")
    assert vues == [None, "Bearer secret-de-test"]
