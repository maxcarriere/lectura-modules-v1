# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Tokeniseur anglais : texte orthographique (ou chaîne phonétique) → Document.

Le texte d'origine n'est jamais réécrit : la normalisation (NFC, apostrophe ’ → ', tirets) ne touche que la
``forme`` des mots ; les décalages visent toujours la chaîne reçue.

Orthographe — conventions d'UD English-EWT (référence des corpus du modèle de phrase ; mesure :
`outils/mesurer_decoupage_ewt.py`) :

- **contractions découpées en mots syntaxiques** : *don't* → do + n't, *can't* → ca + n't, *won't* → wo + n't,
  *I'm* → I + 'm, *Bush's* → Bush + 's, *workers'* → workers + ', *cannot* → can + not, *gonna* → gon + na, *wanna*,
  *gotta*. Le clitique est un mot sans espace avant (``espace_avant`` faux), contigu à son hôte ; *its* n'est pas
  découpé (*it + s* d'EWT est la faute pour *it's* : au modèle de phrase d'en décider) ;
- ponctuation détachée ; « ... », « ?! », « !. » = un token ; émoticônes « :) » « :-) » = un token ;
- abrègements (table ``data/abregements.tsv``) : point attaché (*Mr.*, *St.*, *e.g.*, *Jan.*), initiale *J.* devant
  un nom ; une abréviation ambiguë (« in. », « no. ») ne garde son point que devant un chiffre ou une minuscule ;
- trait d'union coupé entre deux mots (*Al-Zaman* → Al - Zaman, *self-rule*) sauf après un préfixe (*e-mail*,
  *non-human*, *anti-war*, *re-elected*, *mid-July*, *co-workers*) ; nombres à tirets (téléphones, *01-Feb-02*,
  *1990-95*) entiers ; tiret long et demi-cadratin toujours détachés ;
- symbole détaché d'un nombre (*$ 5*, *5 %*), unité collée détachée (*15 bn*, *7:30 PM*) ; la détection des formules
  regroupe ensuite *$3.50*, *5%*, *10 km*, *7:30 pm*, *1990–1995* en une formule lue (``formules/``) ;
- barre oblique coupée entre deux mots (*and / or*), gardée dans les nombres et *w/*, *b/c*.

Fins de phrase : « . ! ? … » (et fermants collés) devant une majuscule, un chiffre ou une ouverture ; jamais après
un titre (*Mr.*, *Dr.*, *St.*) ni une initiale ; après une abréviation qui peut finir une phrase (*etc.*, *Inc.*,
*U.S.*), seulement devant un mot-outil à majuscule (*The*, *In*, *He*…) — un sigle à points final perd alors son
point au profit d'un token « . » (*U.S* + *.*, comme EWT) ; paragraphe (ligne vide).

Phonétique (``tokeniser_phone``) : inventaire anglais (``phonetique.py``) ; « ‿ » = frontière de mot de nature inconnue,
recollée ou non par ``recomposition.py``.
"""

from __future__ import annotations

import re
import unicodedata

from .abregements import ABREVIATION, FINALES, INITIALE, SIGLE, TITRES, TITRES_SANS_POINT, a_points, table
from .decoupage import APO, SEG, TIR, TABLES_ORTHO, TABLES_PHONE, Piece, Tables, decouper_chaine
from .structures import Canal, Document, Mot, NiveauPhone, Phrase, Segment, TypeMot

APOSTROPHES = frozenset("'’ʼ")
TIRETS = frozenset("-‐‑−")
LIAISON = "‿"
SYLLABE = "."
TILDE = "̃"

_SYMBOLES = frozenset("%&@#*/\\§°+=<>|~^$£€¥")
_FIN_DE_PHRASE = frozenset(".!?…")
_DEBUTS_DE_PHRASE = frozenset(
    "The A An In On At It He She They We I You This That These Those His Her Its Their Our My There However But And "
    "As After Before During When While If Although Though Since By For From With Following Today Later Some Many Most "
    "All Other Both Each Such Despite According Under Between Among Also Then Thus Still Yet Meanwhile Furthermore "
    "Moreover Additionally Several Two Three Another What Why How Who Where Once Over Because So Instead Unlike Like "
    "To Of Upon Within Throughout Until Eventually Initially Currently Nevertheless Please Is Are Was Were Do Does Did "
    "Can Will Would Should Could Here No Not Thank Thanks Let".split()
)
_FERMANTS = frozenset("»”\"')]}’›")
_OUVRANTS = frozenset("\"“‘([{«‹„`")

# préfixes gardés attachés par le trait d'union (relevé EWT + PUD : gardé plus souvent que coupé)
PREFIXES = frozenset("e non anti re pre mid co post over pro multi ex counter semi sub cross neo psycho un socio micro "
                     "mis inter intra extra arch macro mini pseudo quasi ultra hyper trans bi tri mono poly proto meta "
                     "infra de dis geo bio eco euro afro cyber tele auto a".split())
ABREV_OBLIQUE = frozenset("w/ w/o b/c b/t l/c i/o c/o a/c n/a w/out y/o".split())
MOTS_COLLES = {"cannot": ("can", "not"), "gonna": ("gon", "na"), "wanna": ("wan", "na"), "gotta": ("got", "ta"),
               "gimme": ("gim", "me"), "lemme": ("lem", "me"), "outta": ("out", "ta"), "dunno": ("du", "n", "no"),
               # contractions sans apostrophe (fautes de l'écrit en ligne, découpées par EWT) ; pas « its », « your »,
               # « lets », « hes », ambigus
               **{h + "nt": (h, "nt") for h in "do did does ca wo could would should is was are were have has had ai "
                                                 "must need".split()},
               "im": ("i", "m"), "ive": ("i", "ve"), "youre": ("you", "re"), "theyre": ("they", "re"),
               "thats": ("that", "s"), "whats": ("what", "s"), "theres": ("there", "s")}
CLITIQUES = ("'s", "'m", "'re", "'ve", "'ll", "'d")
# Formes des mots qui suivent leur hôte sans espace dans une contraction (pour recoller les tokens de surface).
FORMES_CLITIQUES = frozenset(["n't", "'", "not", "na", "ta", "me", "nt", "m", "ve", "re", "s", "n", "no"] + list(CLITIQUES))

RE_SIGLE_POINTS = re.compile(r"^(?:[A-Za-z]{1,2}\.){2,}$")             # U.S. e.g. a.m. Ph.D.
RE_SIGLE_MAJ = re.compile(r"^(?:[A-Z]\.){2,}$")
RE_INITIALE = re.compile(r"^[A-Z]\.$")
RE_URL = re.compile(r"^(?:https?://|www\.)\S+$|^[\w.+-]+@[\w-]+(?:\.[\w-]+)+$|"
                    r"^\w[\w-]*(?:\.\w[\w-]*)*\.(?:com|org|net|edu|gov|htm|html|doc|xls|pdf)(?:/\S*)?$", re.I)
RE_POINTS = re.compile(r"^(?:\.{2,}|…+\.*)$")
RE_FINS = re.compile(r"^[.!?]{2,}$")
RE_EMOTICONE = re.compile(r"^[:;=8][-o'^]?[()DPpO/\\|\[\]*3]+$")
RE_NOMBRE_UNITE = re.compile(r"^(\d[\d,.:]*)([A-Za-z]{1,3})$")
SUFFIXES_NOMBRE = frozenset("st nd rd th s ST ND RD TH".split())


def tokeniser(texte: str) -> Document:
    """Tokenise un texte orthographique anglais."""
    mots = _mots_ortho(texte)
    return Document(texte, Canal.ORTHO, _phrases(texte, mots))


def tokeniser_phone(chaine: str, niveau: NiveauPhone | None = None) -> Document:
    """Tokenise une chaîne phonétique anglaise (inventaire de ``phonetique.py``) : mots séparés par des espaces ou par
    « ‿ » (frontière de mot de nature inconnue : enchaînement ou clitique, ``recomposition.py`` tranche), « . » « ˈ »
    « ˌ » entre syllabes (facultatifs), ponctuation ; « ' » et « - » (troisième niveau, ``phone_sep``) gardés dans le
    mot. Un mot suivi de « ‿ » a ``lie_au_suivant`` vrai."""
    if niveau is None:
        niveau = _niveau_phone(chaine)
    mots = _mots_phone(chaine)
    return Document(chaine, Canal.PHONE, _phrases(chaine, mots, casse=False), niveau)


# ── Orthographe ────────────────────────────────────────────────────────────────


def _est_lettre(c: str) -> bool:
    return unicodedata.category(c)[0] == "L"


def _est_chiffre(c: str) -> bool:
    return unicodedata.category(c)[0] == "N"


def _normaliser(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    return "".join("'" if c in APOSTROPHES else "-" if c in TIRETS else c for c in s)


def _mot_suivant(suivant: str | None) -> str:
    if not suivant:
        return ""
    m = re.match(r"^[\"“‘'(\[]*([\w.]+)", suivant)
    return m.group(1) if m else suivant


def _garde_le_point(x: str, suivant: str | None) -> bool:
    """Le point final de ``x`` fait-il partie d'un abrègement (Mr., e.g., J.) ?"""
    nxt = _mot_suivant(suivant)
    mot_nxt = re.match(r"^[A-Za-z]+", nxt)
    mot_nxt = mot_nxt.group(0) if mot_nxt else ""
    if x in TITRES:
        return True
    abrege = table().get(x)
    if abrege is not None:
        if not abrege.ambigu:
            return True
        if not nxt:
            return False
        if nxt[0].isdigit() or nxt[0].islower():
            return True
        return x in TITRES and nxt[0].isupper() and mot_nxt not in _DEBUTS_DE_PHRASE
    if x in FINALES or RE_SIGLE_POINTS.match(x):
        return True
    if RE_INITIALE.match(x):
        # « J. Smith », « J. R. R. Tolkien » ; pas « vitamin C. The… »
        return bool(nxt) and nxt[0].isupper() and mot_nxt not in _DEBUTS_DE_PHRASE
    return False


def _couper_tirets(x: str) -> list[str]:
    if any(c in x for c in "–—―") and len(x) > 1:
        res = []
        for p in re.split(r"([–—―]+)", x):
            if p:
                res.extend([p] if p[0] in "–—―" else _couper_tirets(p))
        return res
    if "-" not in x or x.strip("-") == "" or RE_URL.match(x):
        return [x]
    if "--" in x:
        res = []
        for p in re.split(r"(-{2,})", x):
            if p:
                res.extend([p] if p.startswith("--") else _couper_tirets(p))
        return res
    parties = x.split("-")
    if any(ch.isdigit() for ch in x) and all(re.match(r"^[\dA-Za-z#.]*$", p) for p in parties) \
            and sum(any(ch.isdigit() for ch in p) for p in parties) >= 2:
        return [x]                                        # 713-853-3989, 01-Feb-02, 1990-95
    res, courant = [], parties[0]
    for p in parties[1:]:
        if courant == "":
            courant = "-" + p                             # tiret initial laissé au mot (-ECT)
            continue
        if p == "":
            res.extend([courant, "-"])                    # tiret final détaché (worse-)
            courant = ""
            continue
        if "-" not in courant and courant.lower() in PREFIXES:
            courant = courant + "-" + p
        else:
            res.extend([courant, "-"])
            courant = p
    if courant:
        res.append(courant)
    return res


def _couper_obliques(x: str) -> list[str]:
    if "/" not in x or x == "/" or RE_URL.match(x) or x.lower() in ABREV_OBLIQUE:
        return [x]
    if re.match(r"^[\d/.,-]+$", x) or re.match(r"^[A-Za-z]/[A-Za-z]$", x):
        return [x]
    return [p for p in re.split(r"(/)", x) if p]


def _interieur(x: str) -> list[str]:
    """Noyau d'un morceau, sans ponctuation de bord."""
    if not x:
        return []
    if RE_URL.match(x) or RE_EMOTICONE.match(x):
        return [x]
    m = re.match(r"^([$£€¥₹#~≈±<>=+]+)(.+)$", x)
    if m and (m.group(2)[0].isdigit() or m.group(2)[0] == "."):
        return [m.group(1)] + _interieur(m.group(2))
    m = re.match(r"^(.*\d)(%|‰|°)$", x)
    if m:
        return _interieur(m.group(1)) + [m.group(2)]
    m = RE_NOMBRE_UNITE.match(x)
    if m and m.group(2) not in SUFFIXES_NOMBRE:
        return [m.group(1), m.group(2)]                   # 15bn, 7:30PM, 10km
    m = re.match(r"^([A-Za-z]{2,})(\.{2,}|…)([A-Za-z].*)$", x)
    if m:
        return [m.group(1), m.group(2)] + _interieur(m.group(3))   # today...but
    m = re.match(r"^([A-Za-z]{2,}):([A-Za-z].*)$", x)
    if m:
        return [m.group(1), ":"] + _interieur(m.group(2))          # TWO:Now
    m = re.match(r"^([A-Za-z]{2,})\(([A-Za-z]+)\)$", x)
    if m and m.group(2).lower() not in ("s", "es"):
        return [m.group(1), "(", m.group(2), ")"]                  # EnronOnline(TM)
    res = []
    for p in _couper_tirets(x):
        res.extend(_couper_obliques(p) if p != "-" else [p])
    return res


class _Etat:
    def __init__(self):
        self.simple_ouvert = False


def _morceau(x: str, etat: _Etat, suivant: str | None) -> list[str]:
    """Tokens de surface d'un morceau sans espace (leur concaténation redonne le morceau)."""
    if RE_EMOTICONE.match(x) or RE_URL.match(x):
        return [x]
    avant, apres = [], []
    while x:
        c = x[0]
        m = re.match(r"^(‘’|''|``|’’|“”)", x)
        if m and len(x) > 2:
            avant.append(m.group(1))
            x = x[2:]
            continue
        if c in APOSTROPHES:
            reste = x[1:].rstrip(".,;:!?)\"”’")
            if len(x) > 1 and (reste.lower() in ("s", "m", "re", "ve", "ll", "d", "em", "tis", "twas", "n")
                               or re.match(r"^\d\ds?$", reste)):
                break                                     # 's isolé, 'em, '90s
            avant.append(c)
            etat.simple_ouvert = True
            x = x[1:]
            continue
        if c in _OUVRANTS or c in "*•<>" and len(x) > 1 and not RE_EMOTICONE.match(x):
            m = re.match(r"^(<<|>>|\*+)", x)
            k = len(m.group(1)) if m else 1
            avant.append(x[:k])
            x = x[k:]
            continue
        if x.startswith("--") or (c in "–—" and len(x) > 1):
            m = re.match(r"^(-{2,}|[–—]+)", x)
            avant.append(m.group(1))
            x = x[m.end():]
            continue
        break
    while x:
        if RE_POINTS.match(x) or RE_FINS.match(x) or x in ("!", "?", ",", ";", ":", "*", ">>", "<<"):
            apres.insert(0, x)
            x = ""
            break
        m = re.search(r"(''|’’|””)$", x)
        if m and m.start() > 0:
            apres.insert(0, m.group(1))                   # word'' : guillemet fermant double
            x = x[:m.start()]
            continue
        m = re.search(r"[:;=][-o']?[()DP]$", x)
        if m and m.start() > 1 and x[m.start() - 1].isalpha():
            apres.insert(0, x[m.start():])                # series:)
            x = x[:m.start()]
            continue
        m = re.search(r"(\.{2,}|…+\.*)$", x)
        if m and m.start() > 0:
            apres.insert(0, m.group(1))
            x = x[:m.start()]
            continue
        m = re.search(r"([.!?]*[!?][.!?]*)$", x)
        if m and len(m.group(1)) > 1 and m.start() > 0:
            apres.insert(0, m.group(1))                   # fixed!. truck.? wow!!!
            x = x[:m.start()]
            continue
        c = x[-1]
        if c in "!?,;:" or c in "”»›)]}\"*>":
            if c == ")" and "(" in x[:-1] and x.count("(") >= x.count(")") and not x.startswith("("):
                break                                     # word(s)
            m = re.search(r"(>>|\*+)$", x)
            k = len(m.group(1)) if m else 1
            apres.insert(0, x[-k:])
            x = x[:-k]
            continue
        if c in APOSTROPHES:
            if len(x) > 2 and x[-2] in "sS" and x[:-1].replace("-", "").isalpha() and not etat.simple_ouvert:
                break                                     # workers' : possessif
            apres.insert(0, c)
            etat.simple_ouvert = False
            x = x[:-1]
            continue
        if c == ".":
            if len(x) == 1:
                apres.insert(0, ".")
                x = ""
                break
            if _garde_le_point(x, suivant if not apres else apres[0]):
                break
            apres.insert(0, ".")
            x = x[:-1]
            continue
        break
    return avant + _interieur(x) + apres


def decomposer(token: str) -> list[str] | None:
    """Mots syntaxiques d'une contraction (EWT), None sinon. *its* n'est pas découpé."""
    t = token.replace("’", "'")
    low = t.lower()
    if not any(c.isalpha() for c in re.sub(r"'.*$", "", t)):
        return None                                       # 80's, '90s : pas de contraction
    if low in MOTS_COLLES:
        res, k = [], 0
        for p in MOTS_COLLES[low]:
            res.append(token[k:k + len(p)])
            k += len(p)
        return res
    if low.endswith("n't") and len(t) > 3 and t[:-3].isalpha():
        return [token[:-3], token[-3:]]
    for cl in CLITIQUES:
        if low.endswith(cl) and len(t) > len(cl) and t[-len(cl) - 1].isalnum():
            return [token[:-len(cl)], token[-len(cl):]]
    if len(t) > 2 and t.endswith("'") and t[-2] in "sS" and t[:-1].replace("-", "").isalpha():
        return [token[:-1], token[-1]]
    return None


def _segments(forme: str, debut: int) -> list[Segment]:
    """Segments d'un mot (lettres entre apostrophes et traits d'union)."""
    segments, k, sep = [], 0, ""
    for p in re.split(r"(['-])", forme):
        if p in ("'", "-"):
            sep = p
        elif p:
            segments.append(Segment(p, debut + k, debut + k + len(p), sep))
            sep = ""
        k += len(p)
    return segments


def _est_ponctuation(f: str) -> bool:
    if RE_EMOTICONE.match(f):
        return True
    return bool(f) and all(unicodedata.category(c)[0] == "P" and c not in _SYMBOLES for c in f)


def _mot(brut: str, debut: int, abrege_ok: bool, clitique: bool = False) -> Mot:
    forme = _normaliser(brut)
    fin = debut + len(brut)
    if clitique:
        return Mot(TypeMot.MOT, forme, debut, fin, _segments(forme, debut))   # « ' » possessif, « n't »
    if _est_ponctuation(brut):
        return Mot(TypeMot.PONCTUATION, forme, debut, fin)
    if any(_est_chiffre(c) for c in brut):
        return Mot(TypeMot.FORMULE, forme, debut, fin)
    if not any(_est_lettre(c) for c in brut):
        return Mot(TypeMot.FORMULE, forme, debut, fin)          # symbole (& % $ @ +)
    nature = ""
    if abrege_ok and forme.endswith("."):
        connu = table().get(forme)
        if connu is not None:
            nature = connu.nature
        elif RE_INITIALE.match(forme):
            nature = INITIALE
        elif RE_SIGLE_POINTS.match(forme):
            nature = SIGLE
        elif forme in TITRES or forme in FINALES:
            nature = ABREVIATION
    return Mot(TypeMot.MOT, forme, debut, fin, _segments(forme, debut), abregement=nature)


def _mots_ortho(texte: str) -> list[Mot]:
    mots: list[Mot] = []
    etat = _Etat()
    morceaux = list(re.finditer(r"\S+", texte))
    for i, m in enumerate(morceaux):
        suivant = morceaux[i + 1].group(0) if i + 1 < len(morceaux) else None
        k = m.start()
        for j, t in enumerate(_morceau(m.group(0), etat, suivant)):
            dec = decomposer(t) if any(c.isalpha() for c in t) else None
            parties = dec or [t]
            for n, p in enumerate(parties):
                mot = _mot(p, k, abrege_ok=True, clitique=n > 0)
                mot.espace_avant = j == 0 and n == 0 and k > 0
                mots.append(mot)
                k += len(p)
    _abregements_sans_point(mots)
    return mots


# ── Abrègements sans point ─────────────────────────────────────────────────────


def _contexte_d_abreviation(mot: Mot, suivant: Mot | None) -> bool:
    """Une forme qui est aussi un mot n'est un abrègement que suivie d'un nombre (« No 5 »), ou, pour un titre,
    d'un nom propre (« St Louis », « Mr Smith »)."""
    if suivant is None or not suivant.espace_avant:
        return False
    if suivant.forme[:1].isdigit():
        return True
    return mot.forme in TITRES_SANS_POINT and suivant.forme[:1].isupper() and suivant.forme not in _DEBUTS_DE_PHRASE


def _abregements_sans_point(mots: list[Mot]) -> None:
    """Sigles, acronymes, abréviations et unités sans point connus du lexique (« FBI », « NASA », « Mr », « km »),
    écrits avec leur casse ; pas dans un passage tout en capitales (titre : « THE END OF THE WORLD »)."""
    capitales = [m.type is TypeMot.MOT and len(m.forme) > 1 and m.forme.isupper() for m in mots]
    for k, m in enumerate(mots):
        if m.type is not TypeMot.MOT or m.abregement or "." in m.forme:
            continue
        abrege = table().get(m.forme)
        if abrege is None:
            continue
        if abrege.ambigu == "unite":
            prec = mots[k - 1] if k > 0 else None
            if prec is not None and prec.type is TypeMot.FORMULE and any(c.isdigit() for c in prec.forme):
                m.abregement = abrege.nature                     # « 10 km »
            continue
        if len(m.forme) < 2 or m.forme.islower() and abrege.ambigu:
            continue
        if capitales[k] and ((k > 0 and capitales[k - 1]) or (k + 1 < len(mots) and capitales[k + 1])):
            continue
        if abrege.ambigu == "mot" and not _contexte_d_abreviation(m, mots[k + 1] if k + 1 < len(mots) else None):
            continue                     # « IT », « AM », « OR » : des mots, sauf contexte sûr
        m.abregement = abrege.nature


# ── Phrases ────────────────────────────────────────────────────────────────────


def _phrases(texte: str, mots: list[Mot], casse: bool = True) -> list[Phrase]:
    """``casse`` faux (canal phonétique) : pas de majuscule pour décider."""
    phrases: list[Phrase] = []
    courant: list[Mot] = []
    # guillemets droits ouverts avant chaque mot (dans tout le texte : une citation peut couvrir plusieurs phrases)
    guillemets, n = [], 0
    for m in mots:
        guillemets.append(n)
        n += m.forme == '"'
    k = 0
    while k < len(mots):
        mot = mots[k]
        courant.append(mot)
        k += 1
        fin = ""
        if mot.type is TypeMot.PONCTUATION and (mot.forme in _FIN_DE_PHRASE or RE_POINTS.match(mot.forme)
                                                 or RE_FINS.match(mot.forme)):
            fin = "ponct"
        elif mot.abregement and mot.forme.endswith(".") and (mot.forme in FINALES or RE_SIGLE_MAJ.match(mot.forme)):
            fin = "abrev"
        if not fin:
            if k < len(mots) and "\n\n" in texte[mot.fin : mots[k].debut].replace("\r", ""):
                phrases.append(Phrase(courant))
                courant = []
            continue
        # fermants collés (« ." », « .) ») ; un guillemet droit ne ferme que s'il en reste un ouvert
        j = k
        while j < len(mots) and mots[j].type is TypeMot.PONCTUATION and (
                (mots[j].forme in _FERMANTS and mots[j].forme not in "\"'")
                or (mots[j].forme == '"' and guillemets[j] % 2 == 1)
                or (mots[j].forme == "'" and not mots[j].espace_avant)):
            courant.append(mots[j])
            j += 1
        suivant = mots[j] if j < len(mots) else None
        if suivant is None:
            coupe = True
        elif fin == "abrev":
            coupe = suivant.forme in _DEBUTS_DE_PHRASE
        else:
            s = suivant
            if s.forme in _OUVRANTS and j + 1 < len(mots):
                s = mots[j + 1]
            coupe = (not casse) or s.forme[:1].isupper() or s.forme[:1].isdigit() or suivant.forme in _OUVRANTS \
                or (mot.forme[-1] in "!?" and suivant.espace_avant and s.forme[:1].isalpha())
        if coupe and fin == "abrev" and (RE_SIGLE_MAJ.match(mot.forme) or mot.forme == "etc.") and j == k:
            # « in the U.S. » en fin de phrase → U.S + . (EWT)
            courant[-1:] = [Mot(TypeMot.MOT, mot.forme[:-1], mot.debut, mot.fin - 1, _segments(mot.forme[:-1], mot.debut),
                                espace_avant=mot.espace_avant, abregement=mot.abregement),
                            Mot(TypeMot.PONCTUATION, ".", mot.fin - 1, mot.fin)]
        if coupe:
            phrases.append(Phrase(courant))
            courant = []
        k = j
    if courant:
        phrases.append(Phrase(courant))
    return phrases


# ── Phonétique (anglais) ───────────────────────────────────────────────────────

_PONCTUATION_PHONE = frozenset(",;:!?…\"“”«»()[]—–")


def _niveau_phone(chaine: str) -> NiveauPhone:
    from .phonetique import CARACTERES

    for i, c in enumerate(chaine):
        voisin = (i > 0 and chaine[i - 1] in CARACTERES) and (i + 1 < len(chaine) and chaine[i + 1] in CARACTERES)
        if c in ("'", "-") and voisin:
            return NiveauPhone.SEPARE
    if any(c in chaine for c in ".ˈˌ‿"):
        return NiveauPhone.SYLLABE
    return NiveauPhone.BRUT


def _mots_phone(chaine: str) -> list[Mot]:
    """Mots d'une chaîne phonétique. Un « . » est une frontière de syllabe entre deux caractères phonétiques, une
    ponctuation sinon (fin de mot, espace avant)."""
    from .phonetique import CARACTERES, phonemes, sans_marques

    mots: list[Mot] = []
    n, i, espace = len(chaine), 0, False
    while i < n:
        c = chaine[i]
        if c.isspace():
            espace, i = True, i + 1
            continue
        if c == LIAISON:
            if mots:
                mots[-1].lie_au_suivant = True
            i += 1
            continue
        if c in CARACTERES or c in "'-":
            j = i
            while j < n and (chaine[j] in CARACTERES or chaine[j] in "'-") and chaine[j] != LIAISON:
                if chaine[j] == "." and not (j + 1 < n and chaine[j + 1] in CARACTERES and chaine[j + 1] != LIAISON
                                             and j > i):
                    break
                j += 1
            brut = chaine[i:j]
            if brut.strip(".'-ˈˌ") and phonemes(sans_marques(brut).replace("'", "").replace("-", "")) is not None:
                mots.append(Mot(TypeMot.MOT, brut, i, j, [Segment(sans_marques(brut), i, j)], espace_avant=espace))
                espace, i = False, j
                continue
            if not brut.strip(".'-ˈˌ"):
                mots.append(Mot(TypeMot.PONCTUATION, chaine[i], i, i + 1, espace_avant=espace))
                espace, i = False, i + 1
                continue
        j = i + 1
        if _est_lettre(c) or unicodedata.category(c)[0] == "M":
            # caractère hors inventaire : toute la suite est signalée en bloc
            while j < n and not chaine[j].isspace() and chaine[j] != LIAISON and chaine[j] not in _PONCTUATION_PHONE:
                j += 1
            mots.append(Mot(TypeMot.INCONNU, chaine[i:j], i, j, espace_avant=espace))
        else:
            mots.append(Mot(TypeMot.PONCTUATION, c, i, j, espace_avant=espace))
        espace, i = False, j
    return mots
