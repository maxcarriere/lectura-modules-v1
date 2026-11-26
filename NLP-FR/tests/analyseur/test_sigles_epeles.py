"""Sigles épelés inconnus du lexique, à l'écriture (recherche v2, 28/10/2026) : « ɛf ka pe » → « FKP » et non « F cas
P » ; les mots-outils homophones d'une lettre ne sont pas pris dans un sigle (« au B », « ses dés »)."""

import pytest

from lectura_nlp_fr.analyseur.chaine import _lettres
from lectura_nlp_fr.analyseur.moteur import dossier_modeles


def test_decoupage_en_lettres():
    assert _lettres("ɛfkape") == [("ɛf", "F"), ("ka", "K"), ("pe", "P")]
    assert _lettres("zɛdiks") == [("zɛd", "Z"), ("iks", "X")]
    assert _lettres("dubləve") == [("dubləve", "W")]
    assert _lettres("ʃa") is None


@pytest.fixture(scope="module")
def moteur():
    from lectura_nlp_fr.analyseur import creer_moteur

    return creer_moteur("local", juge=False)


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
@pytest.mark.parametrize("texte, attendu", [
    ("La livre FKP dont la valeur", "FKP"),
    ("la livre sterling GBP.", "GBP"),
    ("les ZX Spectrum", "ZX"),
    ("le U.S. Corps", "US"),
    ("Il a vu ses dés.", "ses dés"),
    ("Il passe au B.", "au B"),
    ("La SNCF et la RATP", "SNCF"),
])
def test_sigles_epeles(moteur, texte, attendu):
    phone = " ".join(p["phone"] for p in moteur.lire(texte))
    assert attendu in " ".join(p["ortho"] for p in moteur.ecrire(phone))



@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
@pytest.mark.parametrize("phone, accordes", [
    ("le ljɔ̃ sɔ̃ le ʃa le ply sɔ.sjabl, vi.vɑ̃ ɑ̃ ɡʁɑ̃ ɡʁu.p‿a.pə.le møt.", {"grand groupe", "grands groupes"}),
    ("le tɑ̃ vjɔ.lɑ̃ ɛ lə tɛʁm ʒe.ne.ʁik puʁ tu fe.nɔ.mɛn me.te.ɔ.ʁɔ.lɔ.ʒik dɑ̃.ʒə.ʁø.",
     {"phénomène météorologique", "phénomènes météorologiques"}),
])
def test_groupe_nominal_coherent(moteur, phone, accordes):
    """Groupe nominal cohérent en nombre, même quand rien ne s'entend (28/10/2026) : jamais « grand groupes »."""
    ecrit = " ".join(p["ortho"] for p in moteur.ecrire(phone))
    assert any(a in ecrit for a in accordes), ecrit


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
def test_sigle_connu_ecrit_depuis_mots_rares_ou_lettres(moteur):
    """Sigle de la table des abrègements prononcé comme des mots : écrit s'il y a un indice (lettre isolée, mot inconnu
    ou rare) ; des mots courants seuls restent des mots (« des pays » n'est pas « DPI »)."""
    from lectura_nlp_fr.analyseur.chaine import _sigles_connus

    assert _sigles_connus()["devede"] == "DVD" and _sigles_connus()["ɛlsede"] == "LCD"
    for texte, attendu in [("Il a vu des pays.", "pays"), ("Il achète un DVD.", "DVD")]:
        assert attendu in " ".join(m["ortho"] for m in moteur.ecrire(moteur.lire(texte)[0]["phone"]))


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
@pytest.mark.parametrize("texte, sigle, phone", [
    ("La FIH a son siège.", "FIH", "ɛf.i.aʃ"),
    ("Le rapport de l'USGS.", "USGS", "y.ɛs.ʒe.ɛs"),
    ("La SCLC agit.", "SCLC", "ɛs.se.ɛl.se"),
])
def test_capitales_inconnues_epelees_d_un_tenant(moteur, texte, sigle, phone):
    """Lecture (1.0.3) : un mot en capitales inconnu et imprononçable est épelé d'un seul tenant, comme un sigle du
    lexique ; l'écriture le retrouve."""
    (lu,) = moteur.lire(texte)
    (mot,) = [m for m in lu["mots"] if m["forme"] == sigle]
    assert mot["phone"].replace(".", "").rstrip("‿") == phone.replace(".", "")
    assert sigle in " ".join(m["ortho"] for m in moteur.ecrire(lu["phone"]))


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
@pytest.mark.parametrize("texte, attendu", [
    ("DANS LEQUEL CRAIG ET FRY SONT PRÉSENTÉS", "fʁaj"),        # passage en capitales : pas épelé
    ("Grande-duchesse JUDITH, douairière", "ʒy.dit"),          # capitales connues du lexique en « Judith »
    ("KIN fo ne débarqua pas.", "kin"),                        # consonne, voyelle, consonne : lu comme un mot
    ("Chapitre XLV. Je ne veux pas.", "ka.ʁɑ̃t.sɛ̃k"),          # romain court annoncé
    ("XXVIII. La vie élégante.", "vɛ̃.t‿ɥit"),                 # titre de chapitre en tête de phrase
    ("-- Tous.", "tus"),                                       # pronom seul
    ("Quand CD serait bien loin.", "se.de"),                   # pas un romain hors contexte sûr
])
def test_regressions_1_0_3(moteur, texte, attendu):
    """Régressions de la 1.0.3 relevées par Corpus sur 1,27 million de phrases (31/10/2026), corrigées en 1.0.4."""
    assert attendu in moteur.lire(texte)[0]["phone"]


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
@pytest.mark.parametrize("texte, attendu", [
    ("Chut! Ils se moqueraient de nous.", "ʃyt!"),            # phrase d'un mot dans un texte : lue comme en 1.0.2
    ("« Chut! » Fit-elle.", "ʃyt!"),
    ("X. L'homme des eaux.", "dis."),
    ("Chut!", "ʃyt!"),                                         # entrée d'un seul mot : pas le nom propre « Chu »
    ("« XI. Le villageois et le serpent. »", "ɔ̃z."),          # titre romain après un guillemet ouvrant
])
def test_regressions_1_0_4(moteur, texte, attendu):
    """Régressions relevées par les témoins de Corpus (31/10/2026) : la lecture du mot seul ne vaut que pour une
    entrée entière d'un seul mot (listes de mots), pas pour une phrase d'un mot au milieu d'un texte."""
    assert attendu in " ".join(p["phone"] for p in moteur.lire(texte))


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
@pytest.mark.parametrize("texte, attendu", [
    ("Le comité du RC Montvert.", "RC"),                # nom propre rare fait de lettres (« Hercé »)
    ("Le club du BK Valmont.", "BK"),                           # « Becca »
    ("Le SLS décolle.", "SLS"),                                # « hesse el hesse »
    ("Le MVP américain.", "MVP"),
    ("Le CIO a décidé.", "CIO a"),                             # un mot-outil ne prolonge pas le sigle (pas « CIOA »)
    ("La RDA à Berlin.", "RDA à"),
    ("Il passe au B.", "au B"),
    ("Il a vu des pays.", "des pays"),
    ("L'Office régional pour le transport scolaire (ORTS) est un organisme.", "(ORTS)"),  # annoncé par ses initiales
])
def test_sigles_hors_table(moteur, texte, attendu):
    """Écriture (30/10/2026) : sigles absents de la table des abrègements, faits de noms de lettres avec un indice, ou
    annoncés par leur forme longue entre parenthèses."""
    phone = " ".join(p["phone"] for p in moteur.lire(texte))
    assert attendu in " ".join(p["ortho"] for p in moteur.ecrire(phone))
