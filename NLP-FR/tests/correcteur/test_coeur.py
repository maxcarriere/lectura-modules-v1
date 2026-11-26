"""Tests du Correcteur sur des phrases témoins, écrites pour ces tests (aucune phrase de corpus).

Ils demandent les modèles (Analyseur, Correcteur et son juge v2b) et une base Lexicon locale ; sans eux, ils sont
sautés. Variables : ``LECTURA_NLP_FR_DIR``, ``LECTURA_JUGE_DIR`` (juge de l'écriture), ``LECTURA_CORRECTEUR_DIR``,
``LECTURA_JUGE_CORRECTEUR_DIR`` (ou ``<dossier du Correcteur>/juge``), ``LECTURA_LEXICON_DATA``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("kenlm", reason="Correcteur : kenlm absent")
pytest.importorskip("onnxruntime", reason="Correcteur : onnxruntime absent")


@pytest.fixture(scope="module")
def coeur():
    from lectura_nlp_fr.analyseur.moteur import dossier_modeles as modeles_analyseur
    from lectura_nlp_fr.correcteur import charger, dossier_modeles, lexique_local

    if modeles_analyseur() is None or dossier_modeles() is None:
        pytest.skip("modèles de l'Analyseur ou du Correcteur absents")
    try:
        lexique = lexique_local()
    except FileNotFoundError:
        pytest.skip("base Lexicon locale absente")
    return charger(lexique=lexique)


def test_juge_du_correcteur_est_v2b(coeur):
    """Le Correcteur reçoit le juge v2b (ses seuils ont été réglés avec lui), jamais le juge v3 de l'écriture."""
    from lectura_nlp_fr.correcteur import EMPREINTE_JUGE_V2B

    juge = coeur.juge_homophones
    assert juge is not None, "juge du Correcteur absent (LECTURA_JUGE_CORRECTEUR_DIR ou <Correcteur>/juge)"
    empreinte = juge.empreinte()
    print(f"\njuge du Correcteur : {juge.modele} sha256 {empreinte}")
    assert empreinte == EMPREINTE_JUGE_V2B, f"juge chargé {empreinte}, attendu v2b {EMPREINTE_JUGE_V2B}"
    ecriture = getattr(coeur.chaine, "recherche", None)
    if hasattr(ecriture, "empreinte"):
        print(f"juge de l'écriture (chaîne) : sha256 {ecriture.empreinte()}")
        assert juge._juge is not ecriture


def _props(coeur, texte: str, mode: str = "suggestions") -> dict[str, str]:
    return {k.original: k.proposition for k in coeur.corriger(texte, mode=mode).corrections}


# ── corrections attendues ────────────────────────────────────────────────────

@pytest.mark.parametrize("texte, attendu", [
    ("Les enfant mange des pomme et ils ont manger a la cantine.",
     {"enfant": "enfants", "mange": "mangent", "pomme": "pommes", "manger": "mangé", "a": "à"}),
    ("Une ami est venue.", {"ami": "amie"}),                     # le déterminant dit l'intention
    ("Un amie est venu.", {"amie": "ami"}),
    ("Il parle francais et habite un chateau.", {"francais": "français", "chateau": "château"}),
    ("Il est trés content, déja parti aprés sa carriere.",
     {"trés": "très", "déja": "déjà", "aprés": "après", "carriere": "carrière"}),
    ("Il aime son coeur et ses oeuvres.", {"coeur": "cœur", "oeuvres": "œuvres"}),
    ("Il faut rendre grace a Dieu, dit-il a son frere.", {"grace": "grâce", "a": "à", "frere": "frère"}),
    ("Le menu est provisoireainsi que les horaires.", {"provisoireainsi": "provisoire ainsi"}),
    ("Il va mourrir parmis les siens parceque c'est ainsi.", {"mourrir": "mourir", "parmis": "parmi", "parceque": "parce que"}),
    ("C'est à dire vis à vis de lui, au dessus de tout.",
     {"C'est à dire": "C'est-à-dire", "vis à vis": "vis-à-vis", "au dessus": "au-dessus"}),
    # élisions oubliées (voyelle, h muet, nom propre, locution) ; apostrophe manquante
    ("Le site de la administration, de Andrew et de Ukraine, parle de le homme.",
     {"la administration": "l'administration", "de Andrew": "d'Andrew", "de Ukraine": "d'Ukraine", "le homme": "l'homme"}),
    ("Je pense que il viendra parce que elle est là ; l ouverture a eu lieu.",
     {"que il": "qu'il", "parce que elle": "parce qu'elle", "l ouverture": "l'ouverture"}),
    ("Il ne est pas venu et je ai attendu ; ce est tout.", {"ne est": "n'est", "je ai": "j'ai", "ce est": "c'est"}),
    ("Il mange l'haricot avec d'hauteur.", {"l'haricot": "le haricot", "d'hauteur": "de hauteur"}),   # h aspiré
    ("Les Soeurs lisent Oedipe et l'Oeuvre ; la main-d'oeuvre et le caecum.",   # ligatures : majuscules, composés
     {"Soeurs": "Sœurs", "Oedipe": "Œdipe", "Oeuvre": "Œuvre", "main-d'oeuvre": "main-d'œuvre", "caecum": "cæcum"}),
    ("Celui ci vit aux Etats Unis et ceux là au Royaume Uni.",
     {"Celui ci": "Celui-ci", "Etats Unis": "États-Unis", "ceux là": "ceux-là", "Royaume Uni": "Royaume-Uni"}),
    ("Il en veut d'avantage que son frère.", {"d'avantage": "davantage"}),   # = plus ; « pas d'avantage à » reste
    ("Il travaille à lHôpital de la ville.", {"lHôpital": "l'Hôpital"}),     # majuscule du nom conservée
    ("Ces dossiers ne peuvent pas être classé aujourd'hui.", {"classé": "classés"}),  # être à l'infinitif
    ("Une tôle laminé est posée sur le toit.", {"laminé": "laminée"}),        # participe épithète
    ("Il sont partis ce matin.", {"Il": "Ils"}),                       # « sont » ≠ « est » : le pronom
    ("Dés 1990, la route sera refaite dés le début de l'été.", {"Dés": "Dès", "dés": "dès"}),
    ("Elle est la trésorière des l'Amicale des Pêcheurs.", {"des": "de"}),   # « des » devant un déterminant (18/10)
    ("Sa décision dépend de celle des ses parents.", {"des": "de"}),
    ("Il a chanté des sa naissance.", {"des": "dès"}),                        # « de » et « dès » se valent : suggestion seulement
    ("Cette mode tend à se propage dans les villes.", {"propage": "propager"}),   # forme conjuguée après « à » (+ pronom conjoint)
    ("Le pliage consiste à déforme la feuille.", {"déforme": "déformer"}),   # « la déforme » : nom rare, le verbe l'emporte
    ("De part le monde, il est un héro de fiction.", {"De part le": "De par le", "héro": "héros"}),
    ("Il a fait une grosse fote.", {"fote": "faute"}),
    ("Ce n'est que tardivemenent qu'il est venu.", {"tardivemenent": "tardivement"}),   # syllabe doublée : raccourci permis                       # même son au timbre près (o/ɔ), pas « fête »
    ("Il les a mangé.", {"mangé": "mangés"}),                                 # COD « les » devant l'auxiliaire
    ("Je suis aller au marché.", {"aller": "allé"}),                           # infinitif après être, les deux modes
    ("Elle est aller au bois.", {"aller": "allée"}),
    ("L'entreprise a été crée en 1985.", {"crée": "créée"}),                   # verbes en -éer après « être »
    ("Le prix est crée en son honneur.", {"crée": "créé"}),
    # personne du verbe : « il » impersonnel, verbe coordonné, forme de 1re personne sans « je » (même son : -ait)
    ("Il es long de 12 km.", {"es": "est"}),
    ("Les deux camions font le plein et retourne au dépôt.", {"retourne": "retournent"}),
    ("Elle est construite en bois, mais atteins un prix élevé.", {"atteins": "atteint"}),
    ("En ouvrant la porte, le chien sauterai dehors.", {"sauterai": "sauterait"}),
    ("Partir tôt lui permettrai d'éviter la foule.", {"permettrai": "permettrait"}),
    ("On peut êtes confronté à un problème.", {"êtes": "être"}),             # forme conjuguée après un semi-auxiliaire
    ("Il y ai trois façons de jouer et il n'y à pas de règle.", {"ai": "a", "à": "a"}),
    ("Ils rangent touts les jouets.", {"touts": "tous"}),
    ("Il est très contant d'avoir gagné.", {"contant": "content"}),         # participe présent / adjectif verbal
    ("Ces résultats sont équivalant, en différent peu.", {"équivalant": "équivalents", "différent": "différant"}),
    ("Il l'a fait lui même ; eux mêmes, jusque là, n'avaient rien vu ; quelques uns sont cités ci après.",
     {"lui même": "lui-même", "eux mêmes": "eux-mêmes", "jusque là": "jusque-là", "quelques uns": "quelques-uns",
      "ci après": "ci-après"}),
    ("Ce quartier figure parmi les plus dense de la ville ; les fêtes les plus importante du village ont lieu en été.",
     {"dense": "denses", "importante": "importantes"}),                     # « les plus » + adjectif
    ("À la fin, seul 3 nageurs parviennent à finir la course.", {"seul": "seuls"}),
    ("Sortez moi d'ici, et allez y vite.", {"Sortez moi": "Sortez-moi", "allez y": "allez-y"}),   # impératif + pronom
    # accords « muets » à structure sûre (16/10 après-midi)
    ("Mon voisin, professeur en art martiaux, est très calme.", {"art": "arts"}),   # adjectif audiblement pluriel : le nom
    ("Un lot de crayons est disponibles pour les élèves.", {"disponibles": "disponible"}),   # nombre de la copule
    ("Les autres régions furent beaucoup plus tardif à adopter cette règle.", {"tardif": "tardifs"}),
    ("Ma tante habite une maison de la ville voisine situé près du port.", {"situé": "située"}),   # têtes toutes féminines
    ("Cette chanson est dans la bande sonore du jeux vidéo préféré de mon frère.", {"jeux": "jeu"}),       # article contracté
    ("La salle servait aux réunions (jusqu'au travaux de l'été dernier).", {"au": "aux"}),   # le LM refuse « réforme »
    ("Le capitaine dû revenir au port et attendre la fin de la tempête.", {"dû": "dut"}),   # participe pris pour un passé simple
    ("Il connu ensuite quelques soucis d'argent.", {"connu": "connut"}),
    ("Les orages le transforment en un torrent qui inondent souvent le village.", {"inondent": "inonde"}),
    ("Il y a deux milles ans, la ville a été fondée.", {"milles": "mille"}),   # numéral invariable
    ("Les deux immeubles remplacent les huits maisons.", {"huits": "huit"}),
    ("Avec entre autre : des livres.", {"autre": "autres"}),
    ("Les enfants rient lorsqu'il se retrouvent.", {"il": "ils"}),         # le LM préfère le pronom au verbe
    ("Il existe une bande dessiné de la série intitulé Les petits loups.", {"dessiné": "dessinée", "intitulé": "intitulée"}),
    ("La chance qu'une lettre ait été modifié par erreur est faible.", {"modifié": "modifiée"}),
    ("La plupart des recettes précédant ce livre intègre un ou plusieurs fruits.", {"intègre": "intègrent"}),
    ("Beaucoup de gens pense que c'est faux.", {"pense": "pensent"}),
    ("Peu de gens sait cela.", {"sait": "savent"}),
    ("Deux des trois soldats de la patrouille ont été fait prisonniers.", {"fait": "faits"}),
    ("Ces chalets ont été construits légers pour être déplacer d'un champ à l'autre.", {"déplacer": "déplacés"}),
    ("Les garçons et filles peuvent être tentées de tricher aux examens.", {"tentées": "tentés"}),
    ("Le salaire était calculé sur le nombre de personne travaillant dans la ferme.", {"personne": "personnes"}),
    ("Mi-mars 2010 un taxe nouvelle de 5 % est venue frapper les cafés.", {"un": "une", "taxe": None}),   # « 2006 un » n'est pas un nombre
    # 16/10 soir : pronom + copule contigus même sous le seuil, passé simple « je / tu » homographe, chaîne après
    # verbe + préposition, attribut d'un verbe attributif
    ("Le pain se conserve au sec et peut, quand il est dure, se faire griller.", {"dure": "dur"}),
    ("Sa victoire permis à l'équipe de remporter deux titres.", {"permis": "permit"}),
    ("Le degré est une mesure qui est définie par la quantité de chaleur dégagé pour chauffer la pièce.", {"dégagé": "dégagée"}),
    ("Ils restent fidèle à leur chef.", {"fidèle": "fidèles"}),
    ("* 12 mai : A Lyon, l'équipe de Nantes bat l'équipe de Lille.", {"A": "À"}),     # « A » en tête de proposition
    ("Ces propos n'ont rien a voir avec la réalité.", {"a": "à"}),                     # « a » + infinitif
    ("La liste a biffer est longue.", {"a": "à", "biffer": None}),
    ("Il faudra deux voir trois ans, c'est difficile voir impossible.", {"voir": "voire"}),
    ("Á Lyon, notre club bat celui de Lille.", {"Á": "À"}),
    ("Il part en Egypte avec Etienne et Eric.", {"Egypte": "Égypte", "Etienne": "Étienne", "Eric": None}),
    # mots collés : premier mot après une puce, mot-outil collé, « à » collé
    ("* Lappareil photo est rangé dans le tiroir.", {"Lappareil": "L'appareil"}),
    ("* Cest la fin des vacances.", {"Cest": "C'est"}),
    ("Il a écrit une dizaine de romans policiersdont le dernier est sorti hier.", {"policiersdont": "policiers dont"}),
    ("Mes deux frères participentà un concours.", {"participentà": "participent à"}),
    # règles d'école (16/10 soir) : leur / leurs, quel que, quoi que, tout, « que » relatif + participe, soudures
    ("Ils ont pris leur affaires.", {"leur": "leurs", "affaires": None}),
    ("Ils leurs ont dit la vérité.", {"leurs": "leur"}),
    ("Quelque soit la raison, il part.", {"Quelque": "Quelle que"}),
    ("Quelques soient les raisons, il part.", {"Quelques": "Quelles que"}),
    ("Quoiqu'il arrive, nous partirons.", {"Quoiqu'": "Quoi qu'"}),
    ("Il a mangé tout les gâteaux.", {"tout": "tous"}),
    ("Il travaille tout les nuits.", {"tout": "toutes"}),
    ("Tous le monde est là.", {"Tous": "Tout"}),
    ("Les fleurs que j'ai cueilli sont belles.", {"cueilli": "cueillies"}),
    ("La lettre qu'il a écrit est longue.", {"écrit": "écrite"}),
    ("La décision que le conseil a pris est contestée.", {"pris": "prise"}),
    ("Les livres que nous n'avons pas lu restent là.", {"lu": "lus"}),
    ("Il vient quelque fois nous voir.", {"quelque fois": "quelquefois"}),
    ("Toute fois, il reste long temps.", {"Toute fois": "Toutefois", "long temps": "longtemps"}),
    ("Ce chapeau a la forme d'un cone régulier.", {"cone": "cône"}),                    # pas « conne » (nettoyage du Module)
    ("Il est directeur par interim de l'école.", {"interim": "intérim"}),
    ("il a finir son travail", {"finir": "fini", "a": None}),                            # « a » après un pronom : participe
    ("Il conduit les 40 passagers sur lAlbatros vers le port.", {"lAlbatros": "l'Albatros"}),
    ("Claire et Marc avait raison.", {"avait": "avaient"}),                               # coordination manquée par l'analyse
    ("Le père et la mère de Jean habite Lyon.", {"habite": "habitent"}),
    ("Le maire et son adjoint a signé le décret.", {"a": "ont"}),
    ("Le chat à mangé la souris.", {"à": "a"}),                                            # « à » + participe passé
    ("Il annonca sa retraite peu de temps après.", {"annonca": "annonça"}),                # cédille, pas « annonce »
    ("Le ministre a déclarer que tout allait bien.", {"déclarer": "déclaré", "a": None}),  # auxiliaire sûr : pas « à »
    ("D'autre parts, la neige est normale dans ces pays.", {"parts": "part"}),
    ("jai mangé une pomme.", {"jai": "j'ai"}),                                             # élisions collées (17/10)
    ("Jai vu lhomme.", {"Jai": "J'ai", "lhomme": "l'homme"}),
    ("jé mangé une pomme.", {"jé": "j'ai"}),
    ("Je sais que jé raison.", {"jé": "j'ai"}),
    ("jé mange une pomme.", {"jé": "je"}),
    ("Cest lécole de mon frère.", {"Cest": "C'est", "lécole": "l'école"}),
    ("Il sait quil pleut.", {"quil": "qu'il"}),
    ("Il dit que lortograf est difficile.", {"lortograf": "l'orthographe"}),
    ("jaimme les pommes.", {"jaimme": "j'aime"}),
])
def test_corrige(coeur, texte, attendu):
    props = _props(coeur, texte)
    for original, proposition in attendu.items():
        assert props.get(original) == proposition, (texte, props)


def test_fini_apres_preposition_garde_fous(coeur):
    """Forme conjuguée après une préposition (18/10) : jamais « être » / « avoir » (« à sont tour » est un homophone de
    « son »), ni quand « l' » est un article (« à l'aura mythique »)."""
    for texte in ("Elle reçoit à sont tour une médaille.", "Il a contribué à l'aura mystérieuse du château.",
                  "Elle aura avant tout marqué l'histoire de son village."):
        props = _props(coeur, texte)
        assert not any(p in ("être", "avoir", "marquer") for p in props.values()), (texte, props)


def test_explications(coeur):
    r = coeur.corriger("Les enfant mange des pomme.")
    assert r.corrections and all(k.explication for k in r.corrections)


# ── fausses corrections à ne pas faire (garde-fous, second juge) ─────────────

@pytest.mark.parametrize("texte", [
    "Le 3 juin 2015, il met un terme à son contrat.",                          # tête de graphie sûre à tort
    "Il vient des Landes et parle des uns et des autres, dès ses premiers pas.",   # « des » + un(e)s : pas « de »
    "Il arrive à peine à table, sans cesse dérangé, et pense à elle sans compte rendu.",   # noms courants après la préposition
    "Un poisson ancien, proche de l'ancêtre commun aux salmonidés et ésocidés.",   # dérivés inconnus du lexique : pas raccourcis
    "Ils testent des authentifieurs comme la carte à puce, puis la réingestion des données.",
    "Le chêne vert (quercus ilex) pousse au sud.",                  # latin entre parenthèses : passage étranger
    "Quel est le coût d'un tel projet ?",
    "Plus de 10 élèves ont en outre été punis, dont un garçon.",
    "Les directeurs avaient pris la décision seuls, sans ordre, sans autorisation.",
    "Le sentiment d'avoir été pesée, mesurée, évaluée.",                       # pas de sujet exprimé
    "Chaque geste, chaque mot avait été guidé par une idée qu'il avait prise pour la sienne.",
    "Les élèves, héritiers de celle-ci, créent des formes de récits collectifs originales.",
    "La plupart des ennuis associés à ce vieux moteur ont tendance à se produire en hiver.",
    "Les clients à table n'étaient que des habitués, et la salle était pleine.",
    "Il y avait un décalage entre ce qu'ils avaient soi-disant écrit et ce qu'ils disaient.",
    "Sa moyenne de 0,8 but par match est la meilleure du club.",
    "Il a placé à Lyon 1,5 milliard d'euros.",
    "C'était avant qu'on découvre notre premier reportage.",
    "Il a joué 12 matches cette saison, a indiqué le club.",
    "Il venait seul, parfois à trois, parfois quatre quand Marc venait accompagné.",
    "Il a posté une lettre, il est retraité et coté en bourse.",               # pas « poste », « retraite »
    "Elle aime les poèmes, la moelle et les coefficients.",                    # pas « mœlle »
    "Il a du gout et sait paraitre sûr de lui.",                               # orthographe rectifiée de 1990
    "Brown, The quiet hills of Wales, Weekly Review, June 2, 2011.",  # passage en anglais
    "Il mange le haricot, lit la une du journal, va de A à Z et parle de Henri IV avec Miguel de Unamuno.",
    "Le huitième jour, le onze de France joue ; la hiérarchie et le hockey de Hollande, oui ou non ?",
    "L'homme et l'hélice, l'habitude d'hier, qu'il garde jusqu'à l'hiver.",   # h muets : élisions justes
    "Goethe lit Boeing et Michael, le foehn souffle sur le curriculum vitae.",  # pas de ligature
    "Le sud est pauvre, une croix rouge orne le mur, le nord est froid.",      # pas « sud-est », « Croix-Rouge »
    "Il n'y a pas d'avantage à cela, et beaucoup d'avantages à partir.",     # « d'avantage » = d'un avantage
    "Elle semble être partie tôt, et ils doivent être rentrés avant la nuit.",  # participes déjà accordés
    "Lisez d'autres textes sur https://humanuscrit.com et écrivez à max@exemple.fr.",  # adresses
    "Le match a lieu à l'Eden Park, Eclipse est un logiciel et Eric vient.",  # noms propres en E
    "Il lance les dés, deux dés rouges, et le jeu de dés reprend.",           # « dés » à jouer
    "Mis à part les radiations, de part et d'autre, elle prend de l'héro.",   # « part » nom, « héro » féminin
    "Demain je sauterai dedans, et toi tu atteins le sommet ; viens ici et mange !",   # 1re / 2e personne légitimes
    "Il y a trois façons de jouer, pourvu qu'il y ait une règle ; j'y ai pensé.",   # « il y a » juste, subjonctif
    "Ce qu'il peut sembler dire ; il va et vient ; il peut faire froid.",     # pas « infinitif après verbe »
    "Les tout-petits dorment ; il est content ; un cas sans précédent ; en précédant la file.",   # paires justes
    "Il est très différent, en différant peu de son frère ; des touts cohérents.",
    "Il est le seul des survivants, reste seul des trois, et seul un homme le sait ; les plus grands gagnent le plus souvent.",
    "Venez nous voir demain ; vous sortez les poubelles et le soir vous allez y dormir.",   # pronom de l'infinitif, indicatif
    "Arrêtez la lecture, envoyez le mot et admirez le résultat ; disons les mots comme ils sont.",   # article, pas pronom
    # accords « muets » (16/10 après-midi) : structures où les deux accords se disent, ou formes justes
    "Le chat ou le chien est noir ; la plupart des gens sont venus ; un des hommes qui ont parlé ; beaucoup de ceux qui pensent.",
    "Le travail fini, il part ; le produit fini est vendu ; il a dû partir, elle avait connu la gloire et pu revenir.",
    "Il navigue sur dix milles marins ; deux cents ans ; quatre-vingts ans ; des bungalows neufs et des touts cohérents.",
    "Entre autres choses, il lit ; les propos du ministre rapportés par la presse ; le fils de la voisine parti tôt.",
    "Le lac aux eaux claires ; il va au marché ; du pain et des jeux ; une section de la commune située au nord.",
    "C'est moi qui ai raison ; les gens qui pensent ; celui qui pense ; ceux qui pensent ; vous êtes content ; on est contents.",
    "Les sports de combat ou arts martiaux ; un art martial ; les chevaux de la ferme voisine sont beaux.",
    "Trop de bruit nuit ; peu de temps après, peu de monde est venu ; la plupart du temps est perdu ; beaucoup de ces livres sont bons.",
    "Il a été fait chevalier ; elle a été faite prisonnière ; il va peut être manger ; la plupart d'entre eux pensent.",
    "Beaucoup d'entre nous pensons ainsi, et il a trouvé la porte fermée.",
    "Les enfants ont regardé la télévision allongés.",                          # le participe se rapporte au sujet
    "En 1950 une loi est votée ; il a vingt et un ans, elle a 1 500 livres.",   # « un » après un chiffre : article
    "Le coût est chiffré à 3,5 milliards d'euros, soit 1,5 milliard de plus, et 0,8 but par match.",   # décimaux en mots
    "A participé au concours du journal ; il a été vu ; ce n'est pas vrai.",      # « A » verbe
    "Je veux manger et voir un film ; il laisse les enfants voir le film ; il faut voir grand.",
    "Quoiqu'il soit malade, il travaille ; elle a quelques amis et quelque peu d'argent ; leurs amis leur parlent.",
    "Les épisodes seront disponibles dès le 30 novembre prochain, et le 1er mai suivant.",   # date : pas un numéral
    "Les deux heures qu'il a dormi lui ont fait du bien ; la chanson que j'ai entendu chanter était belle.",
    "Les efforts qu'il a fait ont payé ; les gens que j'ai vu partir ; les cent euros que ça a coûté.",
    "Elles sont toutes contentes et tout émues ; tout le monde est là ; toutes les nuits il travaille.",
    "Je permis à Joel de partir ; un rapport remis à la commission ; il est difficile de partir ; il a mis la table.",
    "Il est vrai que la tâche reste difficile ; elles deviennent grandes ; il devient difficile de partir.",
    "Le chat ou le chien est noir.",                                                   # « ou » : les deux accords se disent
    "Pierre ou Marie viendront demain.",
    "Ni Pierre ni Paul n'est venu.",
    "Il est tout à fait prêt à partir, elle a été à Paris et les livres à lire sont là.",
    "La sauce est composée de beurre fondu et de crème fraîche.",   # adjectif avant le « et »
    "C'est la suite des longues discussions avec le voisin qui ont commencé en mai.",   # deux antécédents
    "Cette étoffe est bon teint, disait le marchand.",                                           # locution, pas un attribut
    "Sa barque se trouvait à une demi encablure du quai.",                                     # « demi » invariable
    "Avec le kundalini yoga, le souffle est guidé.",                                  # nom composé
    "Lyon est une ville ; Jaime est venu hier.",                                       # noms propres en tête de phrase
])
def test_ne_corrige_pas(coeur, texte):
    assert _props(coeur, texte) == {}, _props(coeur, texte)


def test_sans_plantage(coeur):
    # sortie du transducteur sur de l'oral (Module NLP, 17/10) : « sa dit » déclenchait un KeyError (verdict de genre
    # sans attente de l'analyse) ; « dit » → « dix » n'est pas un couple de genre
    texte = ("À sa dit le marin au capitaine quand celui-ci reparut sur le pont c'était une barque maintenant ce n'est "
             "rien attachons une corde à chacun de ses mâts jetons la dans la mer et n'y pense plus")
    for mode in ("suggestions", "automatique"):
        props = _props(coeur, texte, mode)
        assert "dit" not in props, props


def test_abreviations_sms(coeur):
    """Couche optionnelle : langage SMS réécrit, formes ambiguës sous le contrôle du modèle de langue."""
    coeur.abreviations = True
    try:
        props = _props(coeur, "bjr cava ? pk tu réponds pas, il y a bcp de monde.")
        assert props.get("bjr") == "bonjour" and props.get("cava") == "ça va", props
        assert props.get("pk") == "pourquoi" and props.get("bcp") == "beaucoup", props
        assert _props(coeur, "Je pense que vs avez raison.").get("vs") == "vous"
        assert "vs" not in _props(coeur, "Nous avons vu Paris vs Marseille au stade.")
        assert _props(coeur, "Mme Dupont est arrivée.") == {}
    finally:
        coeur.abreviations = False
    assert "pk" not in _props(coeur, "pk tu viens pas ? il y a bcp de monde.")        # couche éteinte par défaut


def test_mode_automatique_plus_strict(coeur):
    texte = "Les enfant mange des pomme et ils ont manger a la cantine."
    assert set(_props(coeur, texte, "automatique")) <= set(_props(coeur, texte, "suggestions"))


def test_juge_homophones(coeur):
    """Troisième juge des homophones (juge du transducer, 18/10) : veto quand il ne préfère pas nettement la graphie
    proposée, troisième voie quand il est très net. Sauté si le modèle n'est pas installé."""
    juge = coeur.juge_homophones
    if juge is None:
        pytest.skip("juge des homophones du Correcteur non installé")
    formes = ["Ses", "amis", "sont", "la", "."]
    assert juge.note(formes, 3, "la", "là") > 3.0
    assert juge.note(formes, 3, "là", "la") < -3.0
    assert juge.note(formes, 1, "amis", "amies") is None or isinstance(juge.note(formes, 1, "amis", "amies"), float)
    assert juge.note(formes, 3, "la", "xyzzy") is None                # hors vocabulaire
    ancien = coeur.juge_homophones
    coeur.juge_homophones = juge
    try:
        assert _props(coeur, "Ses amis sont la.").get("la") == "là"
        assert _props(coeur, "C'est sa qu'il faut faire.").get("sa") == "ça"
        assert _props(coeur, "Il a pris ses affaires et il est parti.") == {}
    finally:
        coeur.juge_homophones = ancien
