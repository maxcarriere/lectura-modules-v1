# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Accords et conjugaison d'après l'analyse syntaxique (15/10) : ce que la phrase impose à chaque mot, et pourquoi.

Un changement de nombre, de genre, de personne ou de forme verbale n'est proposé que s'il est **justifié** par un mot
de la phrase qui l'impose : le sujet pour le verbe, le déterminant (ou un numéral) pour le nom, le nom pour
l'adjectif, le sujet pour l'attribut et le participe conjugué avec « être », l'auxiliaire ou la préposition pour la
forme du verbe qui suit. La justification sert deux fois : elle retient les fausses corrections d'un modèle trop sûr
de lui (« intacts » → « intact » sans raison) et elle donne l'explication, en français, qui accompagne la correction.

Règles (``Attente.regle``) :
- ``sujet`` : verbe ou auxiliaire conjugué → nombre et personne de son sujet (pronom ; nom : son déterminant, sinon
  sa forme quand elle n'est pas ambiguë ; coordination → pluriel) ; l'impératif, qui n'a pas de sujet, ne compte pas ;
- ``conjugaison`` : infinitif juste après un pronom sujet, sans auxiliaire (« je manger ») → présent de l'indicatif ;
- ``participe_apres_avoir`` : infinitif juste après une forme de l'auxiliaire « avoir » (« il a manger ») → participe ;
- ``infinitif_apres_verbe`` / ``infinitif_apres_preposition`` : participe passé après « aller », un semi-auxiliaire
  ou une préposition (« il va mangé », « pour mangé ») → infinitif ;
- ``determinant`` : nom → nombre de son déterminant ; ``numeral`` : nom précédé d'un numéral > 1 → pluriel ;
- ``genre_nom`` : déterminant d'un nom au genre fixe (« un substance ») → genre du nom ; ``des_de`` : « des » devant
  un adjectif épithète antéposé → « de » (« de bons gâteaux ») ;
- ``nom`` : adjectif épithète → nombre et genre de son nom ;
- ``attribut`` : adjectif attribut (verbe copule ou passif) → nombre et genre du sujet ;
- ``participe`` : participe passé conjugué avec « être » → sujet ; ``participe_avoir`` : avec « avoir » sans objet
  antéposé → masculin singulier.

Chaque règle n'emprunte que des arcs sûrs (probabilité de l'arc ≥ ``seuil``) et ne propose que des formes du lexique.
"""

from __future__ import annotations

from dataclasses import dataclass

SUJET = ("nsubj", "nsubj:pass", "nsubj:caus", "expl:subj")       # expl:subj : « il » impersonnel (« il es long »)
AUXILIAIRES = ("aux", "aux:pass", "aux:tense", "aux:caus", "cop")
NOMBRE = {"Sing": "singulier", "Plur": "pluriel"}
GENRE = {"Masc": "masculin", "Fem": "féminin"}
PERSONNE = {"1": "1re personne", "2": "2e personne", "3": "3e personne"}
_POSSESSIFS_ELIDES = {"mon", "ton", "son"}          # « mon amie » : le genre du déterminant ne dit rien
_VOYELLES = set("aeiouyàâäéèêëîïôöùûüœæh")
_NOMINATIFS = {"je", "j'", "j’", "tu", "il", "elle", "on", "ils", "elles"}
_PRONOMS_CONJOINTS = {"se", "s'", "s’", "me", "m'", "m’", "te", "t'", "t’", "nous", "vous", "le", "la", "l'", "l’", "les",
                      "lui", "leur", "y", "en"}      # entre la préposition et l'infinitif : « à se propager », « pour les voir »
_NOUS_VOUS = {"nous", "vous"}
_PRONOMS_GENRE = {"il": ("Masc", "Sing"), "elle": ("Fem", "Sing"), "ils": ("Masc", "Plur"), "elles": ("Fem", "Plur")}
# verbes attributifs : l'adjectif en xcomp s'accorde avec le sujet (« ses souffrances deviennent difficiles »)
_ATTRIBUTIFS = {"devenir", "redevenir", "rester", "demeurer", "sembler", "paraître", "apparaître", "mourir", "naître",
                "tomber", "vivre", "passer"}
_SEMI_AUXILIAIRES = {"pouvoir", "vouloir", "devoir", "savoir", "falloir", "aller", "venir", "faire", "laisser",
                     "voir", "entendre", "aimer", "préférer", "espérer", "oser", "sembler", "paraître", "souhaiter",
                     "désirer", "compter", "penser", "croire"}
_PREPOSITIONS_INF = {"pour", "sans", "à", "de", "d'", "d’", "afin", "avant"}
# semi-auxiliaires derrière lesquels une forme conjuguée ne peut être qu'un infinitif mal écrit (« on peut êtes »,
# « il va mange ») ; pas « faire » ni « laisser » (« il fait beau », « ce qu'il fait semble »)
_MODAUX = {"pouvoir", "devoir", "vouloir", "falloir", "savoir", "aller"}
# pronoms de 1re et 2e personne : s'il n'y en a aucun dans la phrase, une forme en « -ai », « -s » lue à la
# 3e personne par l'analyse est une faute de personne (« le dahu sauterai » → sauterait)
_PRONOMS_12 = {"je", "j'", "j’", "tu", "me", "m'", "m’", "te", "t'", "t’", "moi", "toi", "nous", "vous"}
_PREPOSITIONS = {"à", "au", "aux", "de", "du", "des", "d'", "d’", "par", "pour", "dans", "sur", "sous", "avec", "en",
                 "chez", "vers", "entre", "contre", "sans", "selon", "parmi", "depuis", "pendant", "malgré"}
# « la plupart des effets ont », « nombre d'investisseurs reconnaissent » : l'accord se fait avec le complément
_COLLECTIFS = {"plupart", "majorité", "minorité", "nombre", "moitié", "quantité", "foule", "multitude", "partie",
               "reste", "tiers", "quart", "ensemble", "totalité", "série", "groupe", "dizaine", "centaine",
               "millier", "infinité", "poignée", "beaucoup", "peu", "trop", "assez", "combien", "tant", "plus",
               "dizaines", "douzaine", "douzaines", "centaines", "milliers", "million", "millions", "milliard",
               "milliards"}                                  # « un million de personnes seront massacrées » : pas « massacrés »
# « les deux heures qu'il a dormi », « les cent euros que ça a coûté » : compléments de mesure, participe invariable
_ANTECEDENTS_MESURE = {"heure", "heures", "an", "ans", "année", "années", "jour", "jours", "mois", "minute", "minutes",
                       "seconde", "secondes", "semaine", "semaines", "siècle", "siècles", "temps", "fois", "euro", "euros",
                       "franc", "francs", "dollar", "dollars", "mètre", "mètres", "kilomètre", "kilomètres", "kilo", "kilos",
                       "kilogramme", "kilogrammes", "tonne", "tonnes", "litre", "litres", "nuit", "nuits", "pas"}
_INVARIABLES_MESURE = {"pleuvoir", "vivre", "coûter", "peser", "durer", "courir", "dormir", "régner", "marcher", "valoir",
                       "mesurer", "faire", "laisser", "falloir", "neiger"}
_ADVERBES_NEGATION = {"pas", "plus", "jamais", "rien", "point", "guère", "déjà", "encore", "toujours", "bien", "tout", "même"}
_MOIS = {"janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
         "décembre"}
_DEMONSTRATIFS = {"celui", "celle", "ceux", "celles"}      # antécédents sûrs de « qui » (« ceux qui pense »)
_LIENS_NOMINAUX = {"de", "du", "des", "d'", "d’", "à", "au", "aux", "en"}   # « la commune belge de Namur situé » : chaîne de noms
_CONTRACTES = {"du": "Sing", "au": "Sing", "aux": "Plur"}   # articles contractés : nombre du nom qui suit (pas « des », partitif ou indéfini)
# « il existe une bande dessiné » : après ces verbes, l'adjectif qui suit l'objet ne se rapporte pas au sujet
_EXISTENTIELS = {"exister", "avoir", "falloir", "rester", "manquer", "paraître", "sortir", "publier", "créer"}
# sujets de quantité : le verbe s'accorde avec le complément (« la plupart des religions intègrent », « beaucoup de
# gens pensent ») ; sans complément, « la plupart » et « beaucoup » sont au pluriel
_QUANTITES = {"plupart", "beaucoup", "peu", "trop", "assez", "tant", "combien"}
# « le nombre de personne », « des milliers de livre » : après ces mots (qui comptent) et « de », le nom est au pluriel ;
# pas « beaucoup de », « trop de », « peu de » (noms massifs : « trop de bruit », le modèle de langue ne suffit pas)
_QUANTITES_NOM = {"nombre", "centaines", "milliers", "millions", "milliards", "dizaines", "douzaines", "vingtaines",
                  "trentaines", "cinquantaines", "centaine", "dizaine", "douzaine", "vingtaine", "trentaine",
                  "cinquantaine", "millier", "million", "milliard", "multitude", "foule", "liste"}
_ORDINAUX = {"premier", "première", "premiers", "premières", "second", "seconde", "seconds", "secondes", "dernier",
             "dernière", "derniers", "dernières"}
_ADVERBES = {"soi-disant", "même", "tout", "pas", "plus", "jamais", "bien", "encore", "toujours", "déjà", "mal", "trop", "beaucoup", "vite",
             "rien", "souvent", "tout", "mieux", "guère"}


@dataclass
class Attente:
    traits: dict[str, str]                 # Number / Gender / Person attendus
    regle: str
    source: int                            # indice du mot qui impose l'accord
    source_texte: str                      # « les enfants », « ils »
    conjuguer: bool = False                # conjugaison d'un infinitif (présent de l'indicatif)
    forme_cible: str = ""                  # forme déjà connue (participe ↔ infinitif)


@dataclass
class Proposition:
    forme: str
    attente: Attente
    explication: str
    confiance: float
    fusion: bool = False                   # la proposition remplace aussi le mot précédent (« je ai » → « j'ai »)


def _traits(l) -> dict[str, str]:
    return l.traits()


def _unanime(lectures, trait: str) -> str | None:
    """Valeur d'un trait partagée par toutes les lectures qui le portent (aucune ambiguïté), sinon None."""
    valeurs = {_traits(l).get(trait) for l in lectures}
    valeurs.discard(None)
    return valeurs.pop() if len(valeurs) == 1 else None


class Accordeur:
    def __init__(self, lexique, seuil: float = 0.8):
        self.lex = lexique
        self.seuil = seuil

    # ── lecture des mots ──────────────────────────────────────────────────────

    def _participes(self, forme: str):
        """Lectures « participe passé » d'une forme (employé comme adjectif : « une tôle laminée »)."""
        return [l for l in self._lectures(forme, {"VERB"})
                if _traits(l).get("VerbForm") == "Part" and _traits(l).get("Tense") == "Past"]

    def _lectures(self, forme: str, upos: set[str]):
        return [l for l in self.lex.lectures(forme.lower()) if l.upos in upos]

    def _dependants(self, analyses, k: int, relations: tuple[str, ...]) -> list[int]:
        return [i for i, a in enumerate(analyses)
                if a.tete == k and a.relation in relations and a.confiance_tete >= self.seuil]

    def _nominal(self, formes, analyses, k: int, avant: int | None = None) -> tuple[dict[str, str], str] | None:
        """Nombre, genre et personne d'un sujet ou d'un nom (indice ``k``), tels que la phrase les dit ; avec le texte
        du groupe (« les enfants »). None si on ne sait pas. ``avant`` : seuls les noms coordonnés placés avant cet
        indice comptent (« l'endothélium capillaire et l'épithélium » : l'adjectif ne porte que sur le premier)."""
        a = analyses[k]
        forme = formes[k]
        traits: dict[str, str] = {}
        texte = forme
        if a.upos == "PRON" or forme.lower() in _NOMINATIFS | _NOUS_VOUS:
            lectures = self._lectures(forme, {"PRON"})
            if not lectures or any(_traits(l).get("PronType") == "Rel" for l in lectures):
                return None                                   # qui, que, lequel : nombre de l'antécédent
            for t in ("Number", "Gender", "Person"):
                v = _unanime(lectures, t)
                if v:
                    traits[t] = v
            traits.setdefault("Person", "3")
            if forme.lower() == "on":
                traits.pop("Gender", None)
        elif a.upos in ("NOUN", "PROPN"):
            traits["Person"] = "3"
            lectures = self._lectures(forme, {"NOUN", "PROPN"})
            dets = [d for d in self._dependants(analyses, k, ("det",)) if d < k]
            if dets:
                d = dets[-1]
                ld = self._lectures(formes[d], {"DET"})
                n = _unanime(ld, "Number")
                if n:
                    traits["Number"] = n
                g = _unanime(ld, "Gender")
                if g and not (formes[d].lower() in _POSSESSIFS_ELIDES and forme[:1].lower() in _VOYELLES):
                    traits["Gender"] = g
                texte = " ".join(formes[d:k + 1])
            nums = self._numeral(formes, analyses, k)
            if nums:
                traits["Number"] = nums
            if "Number" not in traits:
                n = _unanime(lectures, "Number")
                if n:
                    traits["Number"] = n
            g = _unanime(lectures, "Gender")
            if g and not (traits.get("Gender") not in (None, g) and self.contrepartie_genre(forme, traits["Gender"])):
                traits["Gender"] = g                          # le genre du nom prime (« un substance »)…
            # … sauf si le nom a un pendant du genre du déterminant (« un amie » → ami) : le déterminant dit l'intention
        else:
            return None
        conj = [i for i in self._dependants(analyses, k, ("conj",)) if analyses[i].upos in ("NOUN", "PROPN", "PRON")
                and (avant is None or i < avant)]
        if conj:
            if any(formes[i].lower() in ("ou", "ni") for i in range(k, conj[-1] + 1)):
                traits.pop("Number", None)                    # « le chat ou le chien est / sont » : les deux se disent
            else:
                traits["Number"] = "Plur"
            personnes = {traits.get("Person", "3")}
            genres = [traits.get("Gender")]
            for i in conj:
                autre = self._nominal(formes, analyses, i)
                if autre:
                    personnes.add(autre[0].get("Person", "3"))
                genres.append(autre[0].get("Gender") if autre else None)
            traits["Person"] = min(personnes)
            traits.pop("Gender", None)
            if all(genres) and all(analyses[i].upos == "NOUN" for i in [k] + conj):
                traits["Gender"] = "Masc" if "Masc" in genres else "Fem"   # « les pays et zones … tentés » : un masculin l'emporte
            texte = " ".join(formes[k:conj[-1] + 1])
        return traits, texte

    def _debut_numeral(self, formes, analyses, k: int) -> int:
        """Indice du premier mot du numéral qui précède le nom ``k`` (pour l'explication : « vingt et un »)."""
        i = k - 1
        while i >= 0 and (analyses[i].upos == "NUM" or formes[i].lower() == "et"
                          or formes[i].lower() in ("virgule", "point") and 0 < i < k - 1
                          or any(l.upos == "NUM" for l in self.lex.lectures(formes[i].lower()))):
            if any(ch.isdigit() for ch in formes[i]):
                return i if i == k - 1 else i + 1
            if i == k - 1 and formes[i].lower() in ("un", "une") and i >= 1 \
                    and formes[i - 1].lower() not in ("et", "cent", "cents", "mille", "million", "millions",
                                                      "milliard", "milliards"):
                return i
            i -= 1
        return i + 1

    def _numeral(self, formes, analyses, k: int) -> str | None:
        """Nombre imposé par un numéral devant le nom : « deux chats », « vingt et un ans » ; None sans numéral, ni
        devant un nom de mois (« le 30 novembre » : une date, pas une quantité)."""
        if formes[k].lower() in _MOIS:
            return None
        i, nums = k - 1, []
        while i >= 0 and (analyses[i].upos == "NUM" or formes[i].lower() == "et"
                          or any(l.upos == "NUM" for l in self.lex.lectures(formes[i].lower()))):
            if formes[i].lower() in _ORDINAUX or formes[i].lower().endswith(("ième", "ièmes")):
                return None                                   # « notre premier reportage » : pas une quantité
            if any(ch.isdigit() for ch in formes[i]):
                if nums:
                    break                                     # « 2006 un taxe » : le chiffre n'entre pas dans le nombre
                nums.append(formes[i].lower())
                i -= 1
                break                                         # un nombre en chiffres se suffit (« 3 000 », « 1,5 »)
            if i == k - 1 and formes[i].lower() in ("un", "une") and i >= 1 \
                    and formes[i - 1].lower() not in ("et", "cent", "cents", "mille", "million", "millions",
                                                      "milliard", "milliards"):
                nums.append(formes[i].lower())                # « en 2006 un taxe » (lu « deux mille six un ») : « un »
                break                                         # n'est l'unité d'un nombre qu'après « et », « cent », « mille »
            nums.append(formes[i].lower())
            i -= 1
        nums = [n for n in nums if n != "et"]
        if not nums:
            return None
        if i >= 1 and formes[i].lower() in ("virgule", "point"):
            # nombre décimal lu en mots (« zéro virgule cinquante-quatre but », « un virgule deux milliard »,
            # « vingt et un virgule quatre milliards ») : singulier si la partie entière est zéro ou un
            e = i - 1
            while e >= 1 and (analyses[e - 1].upos == "NUM" or formes[e - 1].lower() == "et"
                              or any(l.upos == "NUM" for l in self.lex.lectures(formes[e - 1].lower()))):
                e -= 1
            entier = [x.lower() for x in formes[e:i] if x.lower() != "et"]
            return "Sing" if entier in (["zéro"], ["un"], ["une"]) else "Plur"
        if len(nums) == 1 and any(ch.isdigit() for ch in nums[0]):
            try:
                valeur = float(nums[0].replace(",", ".").replace(" ", "").replace("\u00a0", ""))
            except ValueError:
                return None
            return "Plur" if valeur >= 2 else "Sing"          # « 0,54 but », « 1,2 milliard », « 1,5 millions » ? non
        if any(n not in ("un", "une", "zéro") for n in nums):
            return "Plur"
        return "Sing" if analyses[k - 1].upos == "NUM" else None

    def _forme_verbale(self, lectures, **traits: str):
        """Forme du même lemme qui porte exactement ces traits (participe, infinitif)."""
        for l in lectures:
            for x in self.lex.formes_de(l.id_lemme or l.lemme):
                t = _traits(x)
                if x.upos == l.upos and all(t.get(k) == v for k, v in traits.items()):
                    return x
        return None

    # ── attentes ──────────────────────────────────────────────────────────────

    def attentes(self, formes: list[str], analyses) -> dict[int, Attente]:
        """Pour chaque mot que la phrase contraint : traits attendus, règle, mot qui l'impose."""
        res: dict[int, Attente] = {}
        for j, a in enumerate(analyses):
            if j > 0 and formes[j][:1].isupper():
                continue                                      # nom propre, sigle
            att = None
            if a.upos in ("VERB", "AUX") or self._lectures(formes[j], {"VERB", "AUX"}) and a.upos in ("NOUN", "ADJ"):
                att = self._verbe(formes, analyses, j)
            if att is None and a.upos == "NOUN":
                att = self._nom(formes, analyses, j)
            elif att is None and (a.upos == "ADJ" or a.upos == "VERB" and a.relation == "acl"
                                  and a.feats.get("VerbForm") == "Part" and a.feats.get("Tense") == "Past"):
                att = self._adjectif(formes, analyses, j)     # participe épithète : « une tôle laminé »
            elif att is None and a.upos == "DET":
                att = self._determinant(formes, analyses, j)
            if att:
                res[j] = att
        return res

    def _sujet_de(self, formes, analyses, j: int):
        """Sujet du verbe ``j`` : dépendant nsubj de ``j``, ou de sa tête si ``j`` est un auxiliaire ou une copule.
        Rend (indice du sujet, verbe porteur, traits, texte)."""
        tetes = [j]
        a = analyses[j]
        if a.relation in AUXILIAIRES and a.tete is not None and a.tete >= 0 and a.confiance_tete >= self.seuil:
            tetes.append(a.tete)
        elif a.relation == "conj" and a.tete is not None and 0 <= a.tete < j and a.confiance_tete >= self.seuil \
                and analyses[a.tete].upos in ("VERB", "AUX") \
                and not any(b.tete == j and b.relation in SUJET for b in analyses) \
                and not (j + 1 < len(formes) and formes[j + 1].startswith("-")):   # « donnerait-on » : sujet inversé
            # verbe coordonné sans sujet propre : celui du premier verbe (« les avions font le plein et retourne »,
            # « elle est conçue …, mais atteins »)
            tetes.append(a.tete)
            t = analyses[a.tete]
            if t.relation in AUXILIAIRES and t.tete is not None and t.tete >= 0 and t.confiance_tete >= self.seuil:
                tetes.append(t.tete)
        for h in tetes:
            sujets = [s for s in self._dependants(analyses, h, SUJET)
                      if s < j and formes[s].lower() not in ("ce", "c'", "c’")]   # « ce » : « ce sont », « ce dit-on »
            if not sujets:                                    # « Beaucoup de gens pense » : « beaucoup » sujet moins sûr
                sujets = [s for s, b in enumerate(analyses) if b.tete == h and b.relation in SUJET and s < j
                          and b.confiance_tete >= 0.6 and formes[s].lower() in _QUANTITES]
            if sujets:
                s = sujets[-1]
                if formes[s].lower() == "qui":
                    return self._antecedent(formes, analyses, s, h)
                if formes[s].lower() in _NOUS_VOUS and not (s == 0 or analyses[s - 1].upos in ("PUNCT", "CCONJ", "SCONJ")):
                    return None                               # « ce qui nous est présenté » : objet, pas sujet
                if formes[s].lower() in _NOUS_VOUS and any(
                        l.lemme == "être" and _traits(l).get("Person") == "3"
                        for i in {h, j} for l in self._lectures(formes[i], {"AUX", "VERB"})):
                    return None                               # « nous est présenté » : objet d'un passif
                if s > 0 and (analyses[s - 1].upos == "ADP" or formes[s - 1].lower() in _PREPOSITIONS
                              and not (formes[s - 1].lower() in ("des", "du") and analyses[s - 1].upos == "DET")) \
                        and not (s > 1 and formes[s - 1].lower() in ("de", "d'", "d’") and formes[s - 2].lower() in _QUANTITES):
                    return None                               # « les clients à table n'étaient » : complément, pas sujet
                                                              # (mais « beaucoup de gens pense » : le complément commande)
                if formes[s].lower() in _QUANTITES:
                    return self._quantite(formes, analyses, s, h)   # « la plupart des religions intègre » → intègrent
                if formes[s].lower() in _COLLECTIFS or (s > 0 and formes[s - 1].lower() in _COLLECTIFS):
                    return None                               # « la plupart des effets ont » : accord avec le complément
                if j - s > 12:
                    return None                               # sujet trop loin : l'analyse n'est pas sûre
                n = self._nominal(formes, analyses, s)
                if n and n[0].get("Number") != "Plur" and s + 2 < j and formes[s + 1].lower() == "et" \
                        and (analyses[s + 2].upos in ("NOUN", "PROPN", "PRON")
                             or analyses[s + 2].upos == "DET" and s + 3 < j and analyses[s + 3].upos in ("NOUN", "PROPN")):
                    # coordination que l'analyse a manquée : « Claire et Marc avait », « le maire et son adjoint a »
                    fin = s + 3 if analyses[s + 2].upos in ("NOUN", "PROPN", "PRON") else s + 4
                    n = (dict(n[0], Number="Plur", Person=min(n[0].get("Person", "3"), "3")),
                         " ".join([n[1]] + formes[s + 1:fin]))
                    n[0].pop("Gender", None)
                elif n and s + 2 < j and formes[s + 1].lower() in ("ou", "ni") \
                        and analyses[s + 2].upos in ("NOUN", "PROPN", "PRON", "DET"):
                    return None                               # « Pierre ou Marie viendront » : les deux accords se disent
                elif n and n[0].get("Number") != "Plur" and any(
                        formes[i].lower() == "et" and i + 1 < j and analyses[i + 1].upos in ("NOUN", "PROPN", "PRON", "DET")
                        for i in range(s + 1, j)):
                    return None                               # « le fonctionnement … et les relations … créent »
                if n and "Gender" in n[0] and any(
                        analyses[i].upos == "NOUN" and i > s + 1 and analyses[i - 1].upos == "DET"
                        and formes[i - 2].lower() not in _PREPOSITIONS and analyses[i - 2].upos != "ADP"
                        for i in range(s + 2, j)):
                    n = (dict(n[0]), n[1])
                    n[0].pop("Gender")                        # « chaque choix, chaque mouvement avait été guidé » : genre incertain
                if n and len(sujets) >= 2 and all(analyses[i].upos in ("NOUN", "PROPN", "PRON") for i in sujets) \
                        and s - sujets[0] <= 3 and all(analyses[i].upos == "DET" for i in range(sujets[0] + 2, s)):
                    # deux arcs sujet contigus au lieu d'une coordination : « Claire et Marc avait » → avaient
                    # (pas « la membrane … et …, à travers elle s'effectue » : sujets éloignés)
                    entre = [formes[i].lower() for i in range(sujets[0] + 1, s)]
                    if entre[:1] in (["ou"], ["ni"]):
                        return None                           # « Pierre ou Marie viendra » : les deux accords se disent
                    if entre[:1] == ["et"] and n[0].get("Number") != "Plur":
                        deb = min([sujets[0]] + [d for d in self._dependants(analyses, sujets[0], ("det",)) if d < sujets[0]])
                        n = (dict(n[0], Number="Plur", Person=min(n[0].get("Person", "3"), "3")), " ".join(formes[deb:s + 1]))
                        n[0].pop("Gender", None)
                return (s, h) + n if n else None
        return None

    def _antecedent(self, formes, analyses, s: int, h: int):
        """Sujet « qui » : nombre et genre de l'antécédent, quand il est sûr : le nom juste devant « qui » (ou un
        démonstratif « ceux », « celle »…), tête de la relative, pas complément d'un collectif ou d'un partitif
        (« un des hommes qui », « la plupart des gens qui », « beaucoup de ceux qui » : les deux accords se disent).
        Rend (indice de l'antécédent, verbe porteur, traits, « qui »)."""
        ant = s - 1
        if ant < 0 or analyses[h].relation != "acl:relcl" or analyses[h].tete != ant or analyses[h].confiance_tete < self.seuil:
            return None
        a = analyses[ant]
        if a.upos == "NOUN":
            pass
        elif a.upos == "PRON" and formes[ant].lower() in _DEMONSTRATIFS:
            pass
        else:
            return None
        if ant >= 1 and (formes[ant - 1].lower() in ("des", "de", "d'", "d’", "du") or formes[ant - 1].lower() in _COLLECTIFS):
            return None
        if ant >= 2 and formes[ant - 2].lower() in _COLLECTIFS:
            return None
        n = self._nominal(formes, analyses, ant)
        if not n or "Number" not in n[0]:
            return None
        traits = dict(n[0], Person="3")
        k = ant - 1
        if k >= 0 and analyses[k].upos == "DET":
            k -= 1
        if k >= 1 and (analyses[k].upos == "ADP" or formes[k].lower() in _PREPOSITIONS) and analyses[k - 1].upos == "NOUN":
            # « les protestations contre le régime qui ont commencé », « le fils de la voisine qui est parti » :
            # deux antécédents possibles ; nombres différents → abstention, sinon le genre reste incertain
            n1 = self._nominal(formes, analyses, k - 1)
            if n1 and n1[0].get("Number") != traits["Number"]:
                return None
            traits.pop("Gender", None)
        return (ant, h, traits, "qui")

    def _quantite(self, formes, analyses, s: int, h: int):
        """Sujet de quantité (« la plupart », « beaucoup », « peu »…) : le verbe s'accorde avec le complément
        (« la plupart des religions intègrent », « peu de monde est venu ») ; sans complément, « la plupart » et
        « beaucoup » sont au pluriel ; « d'entre nous / vous » : on s'abstient. Rend (s, h, traits, texte)."""
        q = formes[s].lower()
        k = s + 1
        if k < len(formes) and formes[k].lower() in ("de", "d'", "d’", "des", "du"):
            k += 1
            if k < len(formes) and formes[k].lower() == "entre":
                if k + 1 < len(formes) and formes[k + 1].lower() in ("eux", "elles") and q in ("plupart", "beaucoup"):
                    return (s, h, {"Number": "Plur", "Person": "3"}, " ".join(formes[s:k + 2]))
                return None
            while k < len(formes) and analyses[k].upos in ("DET", "ADJ", "NUM", "ADV"):
                k += 1
            if k < len(formes) and analyses[k].upos in ("NOUN", "PRON") and analyses[k].tete in (s, h):
                n = self._nominal(formes, analyses, k)
                nombre = n[0].get("Number") if n else None
                if not nombre and n and analyses[k].upos == "NOUN":
                    nombre = analyses[k].feats.get("Number")   # « gens » : pluriel pour l'analyse (« la gens romaine » : rare)
                if nombre and (not n or n[0].get("Person", "3") == "3"):
                    traits = {"Number": nombre, "Person": "3"}
                    if n and n[0].get("Gender"):
                        traits["Gender"] = n[0]["Gender"]     # « la plupart des noms a été déformée » → déformés
                    return (s, h, traits, " ".join(formes[s:k + 1]))
            return None
        if q in ("plupart", "beaucoup") and (k >= len(formes) or analyses[k].upos != "ADP"):
            return (s, h, {"Number": "Plur", "Person": "3"}, formes[s])
        return None

    def _copule_adjacente(self, formes, analyses, j: int) -> bool:
        """« il est dure », « elles sont parti » : pronom de 3e personne + copule + attribut, contigus et rattachés à
        l'attribut, même quand l'analyse en doute (sous le seuil) : la structure ne laisse pas de place au doute."""
        return j >= 2 and formes[j - 2].lower() in _PRONOMS_GENRE and analyses[j - 2].tete == j \
            and analyses[j - 2].relation in SUJET and analyses[j - 1].tete == j and analyses[j - 1].relation in AUXILIAIRES \
            and any(l.lemme == "être" for l in self._lectures(formes[j - 1], {"AUX", "VERB"}))

    def _nombre_copule(self, formes, analyses, j: int) -> tuple[dict[str, str], int] | None:
        """Traits que dit la copule ou l'auxiliaire « être » de ``j`` quand sa forme n'est pas ambiguë (« est », « furent »,
        « sont », « a été », « ont été » ; pas « êtes », « suis ») et que le sujet est un nom ou un numéral (pas « on »,
        « ce », « vous ») : l'attribut ou le participe suit ce nombre même quand le sujet est un collectif (« un groupe
        de propulseurs est disponible ») ; le genre du sujet s'y ajoute quand il n'est pas ambigu et que son nombre
        concorde. Rend (traits, indice de la copule)."""
        aux = self._dependants(analyses, j, AUXILIAIRES)
        if self._copule_adjacente(formes, analyses, j) and j - 1 not in aux:
            aux = aux + [j - 1]
        ete = any(formes[c].lower() == "été" for c in aux)
        for c in aux:
            lc = self._lectures(formes[c], {"AUX", "VERB"})
            if not lc or analyses[c].relation not in ("cop", "aux:pass", "aux:tense"):
                continue
            if any(l.lemme != "être" for l in lc) and not (ete and all(l.lemme == "avoir" for l in lc)):
                continue                                      # « ont été faits » : le nombre vient de « ont »
            if any(_traits(l).get("VerbForm") != "Fin" or _traits(l).get("Person") != "3" for l in lc):
                continue
            n = _unanime(lc, "Number")
            if not n:
                continue
            sujets = [s for s, b in enumerate(analyses) if b.tete == j and b.relation in SUJET and s < c]
            if len(sujets) == 1 and formes[sujets[0]].lower() in _PRONOMS_GENRE and sujets[0] == c - 1:
                # « quand il est dure » : pronom de 3e personne juste devant la copule, même sous le seuil
                traits = {"Number": n}
                g, np_ = _PRONOMS_GENRE[formes[sujets[0]].lower()]
                if np_ == n:
                    traits["Gender"] = g
                return traits, c, sujets[0]
            if len(sujets) != 1 or analyses[sujets[0]].upos not in ("NOUN", "PROPN", "NUM"):
                continue                                      # le sujet peut être mal rattaché, il suffit que ce soit un nom
            if any(formes[i].lower() in ("et", "ou", "ni") for i in range(sujets[0], c)) and n == "Sing":
                continue                                      # « le chat ou le chien est noir » : coordination, on s'abstient
            traits = {"Number": n}
            ns = self._nominal(formes, analyses, sujets[0]) if analyses[sujets[0]].upos == "NOUN" else None
            if ns and ns[0].get("Number") == n and ns[0].get("Gender") \
                    and formes[sujets[0]].lower() not in _COLLECTIFS | _QUANTITES | _QUANTITES_NOM \
                    and not any(formes[i].lower() in ("et", "ou", "ni") or analyses[i].upos in ("VERB", "AUX")
                                for i in range(sujets[0] + 1, c)):
                # genre : pas d'un mot de quantité (« un million de personnes seront massacrées »), ni avec une relative
                # entre les deux (« la Normandie qui devient un duché est donnée ») ; l'arc du sujet peut être peu sûr
                # (« une information ait été modifié », 0,76)
                traits["Gender"] = ns[0]["Gender"]           # « une information ait été modifié » → modifiée
            return traits, c, c
        return None

    def _passe_simple(self, formes, analyses, j: int, lectures) -> Attente | None:
        """Participe passé employé comme verbe conjugué, sans auxiliaire (« Bonaparte dû revenir », « il connu des
        problèmes ») : le passé simple qui se prononce pareil (« dut », « connut », « permit », « mit ») ; jamais les
        participes en -é (« mangé » ≠ « mangea »), ni sans complément après le verbe (« Projet abandonné »)."""
        a = analyses[j]
        if a.upos != "VERB" or j + 1 >= len(formes):
            return None
        if self._dependants(analyses, j, AUXILIAIRES) or self._apres_auxiliaire(formes, j):
            return None
        if a.relation == "acl" and a.tete is not None and 0 <= a.tete < j and analyses[a.tete].relation == "root" \
                and not any(b.upos in ("VERB", "AUX") and b.feats.get("VerbForm") == "Fin" for b in analyses) \
                and any(b.tete == j and b.relation == "xcomp" for b in analyses[j + 1:]):
            # « The Stranger permis à Joel de remporter » : la phrase n'a aucun verbe conjugué, le participe rattaché
            # au nom racine est en fait son verbe ; il faut un infinitif derrière (pas « rapport remis à la commission »)
            sujets = [a.tete]
        elif a.relation not in ("root", "conj", "ccomp", "advcl", "parataxis"):
            return None
        else:
            sujets = [s for s in self._dependants(analyses, j, SUJET) if s < j]
        if len(sujets) != 1:
            return None
        s = sujets[0]
        if not (analyses[s].upos in ("NOUN", "PROPN") or formes[s].lower() in _NOMINATIFS - {"je", "j'", "j’", "tu"}):
            return None
        if any(formes[i].lower() in ("se", "s'", "s’", "ne", "n'", "n’") for i in range(s + 1, j)) and j - s > 3:
            return None
        if not any(b.tete == j and b.relation in ("xcomp", "obj", "iobj", "obl:arg", "ccomp", "obl:mod") for b in analyses[j + 1:]):
            return None
        n = self._nominal(formes, analyses, s)
        nombre = n[0].get("Number", "Sing") if n else "Sing"
        if n and n[0].get("Person", "3") != "3":
            return None
        for l in lectures:
            for x in self.lex.formes_de(l.id_lemme or l.lemme):
                t = _traits(x)
                if x.upos == l.upos and t.get("VerbForm") == "Fin" and t.get("Mood") == "Ind" and t.get("Person") == "3" \
                        and t.get("Number") == nombre and x.ortho != formes[j].lower() and self._memes_sons(formes[j], x.ortho):
                    return Attente({"VerbForm": "Fin"}, "passe_simple", s, n[1] if n else formes[s], forme_cible=x.ortho)
        return None

    def _verbe(self, formes, analyses, j: int) -> Attente | None:
        forme = formes[j]
        lectures = self._lectures(forme, {"VERB", "AUX"})
        if not lectures:
            return None
        fv = {_traits(l).get("VerbForm") for l in lectures}
        if "Part" not in fv:
            att = self._apres_avoir(formes, analyses, j, lectures) or self._apres_etre(formes, analyses, j, lectures)
            if att:
                return att
        if fv == {"Inf"}:
            return self._infinitif(formes, analyses, j, lectures)
        if "Part" in fv and "Fin" in fv and self._apres_auxiliaire(formes, j):
            lectures = [l for l in lectures if _traits(l).get("VerbForm") == "Part"]
            fv = {"Part"}
        if fv == {"Part", "Fin"} and analyses[j].feats.get("VerbForm") == "Part" \
                and all(_traits(l).get("Person") in ("1", "2") for l in lectures if _traits(l).get("VerbForm") == "Fin"):
            # « The Stranger permis à Joel de » : « permis » n'est conjugué qu'à « je / tu » ; lu participe, c'est un
            # passé simple de 3e personne mal écrit (« permit »)
            att = self._passe_simple(formes, analyses, j, [l for l in lectures if _traits(l).get("VerbForm") == "Part"])
            if att:
                return att
        if fv == {"Part"} and all(_traits(l).get("Tense") == "Past" for l in lectures):
            att = self._participe_mal_place(formes, analyses, j, lectures)
            if att or analyses[j].upos not in ("VERB", "AUX", "ADJ"):
                return att
            att = self._passe_simple(formes, analyses, j, lectures)
            if att:
                return att
            return self._participe(formes, analyses, j, lectures, self._sujet_de(formes, analyses, j))
        if fv == {"Fin"}:
            att = self._fini_apres_preposition(formes, analyses, j, lectures)
            if att:
                return att
        if "Fin" not in fv or analyses[j].upos not in ("VERB", "AUX"):
            return None
        if fv == {"Fin"}:
            att = self._apres_modal(formes, analyses, j, lectures)
            if att:
                return att
        sujet = self._sujet_de(formes, analyses, j)
        if not sujet:
            return self._personne(formes, analyses, j, lectures)
        if sujet[1] != j and analyses[j].relation not in AUXILIAIRES + ("conj",):
            return None
        if sujet[3].lower() in ("ce", "c'", "c’") and any(l.lemme == "être" for l in lectures):
            return None                                       # « c'est » / « ce sont » : les deux se disent
        traits = {k: v for k, v in sujet[2].items() if k in ("Number", "Person")}
        if "Number" not in traits:
            return None
        if sujet[3] == "qui":                                 # « un torrent qui inondent » : accord avec l'antécédent
            return Attente(traits, "sujet_relatif", sujet[0], formes[sujet[0]])
        return Attente(traits, "sujet", sujet[0], sujet[3])

    def _apres_modal(self, formes, analyses, j: int, lectures) -> Attente | None:
        """Forme conjuguée (jamais infinitif ni participe) juste après un semi-auxiliaire conjugué : « on peut êtes
        confronté », « il va mange » → l'infinitif. L'analyse doit rattacher la forme au semi-auxiliaire (xcomp) ou
        la prendre pour un auxiliaire ; un verbe qui en est la tête (« ce qu'il peut semble ») n'est pas touché."""
        if j == 0:
            return None
        k = j - 1
        if formes[k].lower() in _ADVERBES and k > 0:
            k -= 1
        prev = formes[k].lower()
        if not any(l.upos in ("VERB", "AUX") and l.lemme in _MODAUX and _traits(l).get("VerbForm") == "Fin"
                   for l in self.lex.lectures(prev)) or analyses[k].upos not in ("VERB", "AUX"):
            return None
        if analyses[k].relation == "acl:relcl":
            return None
        a = analyses[j]
        if not (a.relation == "xcomp" and a.tete == k or a.relation in AUXILIAIRES):
            return None
        if any(l.upos not in ("VERB", "AUX") for l in self.lex.lectures(formes[j].lower())):
            return None                                       # « il peut faire », « il va bien »
        cible = self._forme_verbale(lectures, VerbForm="Inf")
        if cible and cible.ortho != formes[j].lower():
            return Attente({}, "infinitif_apres_verbe", k, formes[k], forme_cible=cible.ortho)
        return None

    def _personne(self, formes, analyses, j: int, lectures) -> Attente | None:
        """Forme qui n'existe qu'à la 1re ou 2e personne (« permettrai », « es ») sans sujet repéré, dans une phrase
        sans « je », « tu », « me », « nous »…, et que l'analyse lit à la 3e personne : c'est une faute de personne ;
        la cible est la forme de la 3e personne (``_flechir`` préfère celle qui se prononce pareil : « permettrait »)."""
        if j == 0 or analyses[j].feats.get("Person") != "3":
            return None
        personnes = {_traits(l).get("Person") for l in lectures}
        if "3" in personnes or None in personnes or any(_traits(l).get("Mood") == "Imp" for l in lectures):
            return None                                       # « Viens ici » : impératif possible
        if any(f.lower() in _PRONOMS_12 for f in formes):
            return None
        toutes = self.lex.lectures(formes[j].lower())
        zipf_verbe = max(l.zipf for l in lectures)
        if any(l.upos not in ("VERB", "AUX") and l.zipf >= zipf_verbe - 1.0 for l in toutes):
            return None                                       # « es » (nom rare) passe, « vis » (la vis) non
        nombre = analyses[j].feats.get("Number") or _unanime(lectures, "Number")
        if not nombre:
            return None
        p = min(personnes)
        return Attente({"Number": nombre, "Person": "3"}, "personne", j, PERSONNE[p])

    def _infinitif(self, formes, analyses, j: int, lectures) -> Attente | None:
        if j == 0:
            return None
        prev = formes[j - 1].lower()
        # « je manger » : pronom sujet juste devant, sans auxiliaire → à conjuguer
        if self._dependants(analyses, j, AUXILIAIRES):
            return None
        if prev in _NOMINATIFS or (prev in _NOUS_VOUS and (j == 1 or analyses[j - 2].upos in ("PUNCT", "CCONJ", "SCONJ"))):
            s = self._nominal(formes, analyses, j - 1)
            if s and "Number" in s[0]:
                traits = {"Number": s[0]["Number"], "Person": s[0].get("Person", "3")}
                return Attente(traits, "conjugaison", j - 1, formes[j - 1], conjuguer=True)
        return None

    def _apres_auxiliaire(self, formes, j: int) -> bool:
        """Une forme conjuguée d'avoir ou d'être dans les deux mots qui précèdent (adverbe possible entre)."""
        for k in (j - 1, j - 2):
            if k < 0:
                break
            if formes[k].lower() == "été" or any(l.upos == "AUX" and _traits(l).get("VerbForm") == "Fin"
                                                 for l in self.lex.lectures(formes[k].lower())):
                return True                                   # « ont été fait prisonniers » : « été » compte comme auxiliaire
            if k == j - 1 and formes[k].lower() not in _ADVERBES \
                    and not any(l.upos == "ADV" for l in self.lex.lectures(formes[k].lower())):
                return False                                  # « avaient soi-disant écrit » : adverbe toléré
        return False

    def _apres_avoir(self, formes, analyses, j: int, lectures) -> Attente | None:
        """Après l'auxiliaire « avoir », une forme du verbe qui n'est pas un participe (« il a manger », « il a
        était », « ils ont mangeait ») : le participe passé, s'il a le même son ou presque (é / er / ait / ai)."""
        if j == 0:
            return None
        k = j - 1
        if formes[k].lower() in _ADVERBES and k > 0:
            k -= 1
        prev = formes[k].lower()
        if not any(l.upos == "AUX" and l.lemme == "avoir" and _traits(l).get("VerbForm") == "Fin"
                   for l in self.lex.lectures(prev)):
            return None
        forme = formes[j].lower()
        infinitif = all(_traits(l).get("VerbForm") == "Inf" for l in lectures)
        if not infinitif and any(l.upos in ("NOUN", "ADJ", "ADV", "ADP", "DET", "PRON")
                                 for l in self.lex.lectures(forme)):
            return None                                       # « a faim », « a peur », « a raison » : pas un verbe
        if not infinitif and not forme.endswith(("er", "é", "ée", "és", "ées", "ai", "ais", "ait", "aient", "ez")):
            return None                                       # forme conjuguée : seulement si elle sonne comme le participe
        cible = self._forme_verbale(lectures, VerbForm="Part", Tense="Past", Gender="Masc", Number="Sing")
        if cible and cible.ortho != forme:
            return Attente({}, "participe_apres_avoir", k, formes[k], forme_cible=cible.ortho)
        return None

    def _apres_etre(self, formes, analyses, j: int, lectures) -> Attente | None:
        """Après une forme de l'auxiliaire « être » (« est », « a été »), une forme conjuguée d'un verbe en -éer
        (« a été crée », « n'est pas agrée ») : le participe passé accordé avec le sujet (« créée »), qui a presque le
        même son (é / éé). Les autres verbes ne se confondent pas ainsi (« est mange » ne sonne pas comme « mangé »)."""
        if j == 0:
            return None
        k = j - 1
        if formes[k].lower() in _ADVERBES and k > 0:
            k -= 1
        prev = formes[k].lower()
        forme = formes[j].lower()
        infinitif_etre = prev == "être" and not (k > 0 and formes[k - 1].lower() in ("peut", "peux"))   # pas « peut être manger »
        if prev != "été" and not infinitif_etre \
                and not any(l.upos == "AUX" and l.lemme == "être" and _traits(l).get("VerbForm") == "Fin"
                            for l in self.lex.lectures(prev)):
            return None
        if all(_traits(l).get("VerbForm") == "Inf" for l in lectures) and forme.endswith("er"):
            # « je suis aller », « elle est aller » : l'infinitif sonne comme le participe ; accord avec le sujet
            # (masculin si le genre n'est pas dit : « je suis allé ») ; « pour être déplacer » : sujet du verbe dont
            # l'infinitif dépend (« ils ont été construits … pour être déplacés »)
            sujet = self._sujet_de(formes, analyses, j)
            a = analyses[j]
            if infinitif_etre and not sujet and a.relation in ("xcomp", "advcl", "acl", "conj", "ccomp") \
                    and a.tete is not None and a.tete >= 0 and a.confiance_tete >= 0.6:   # la faute est sûre, seul l'accord dépend du rattachement
                sujet = self._sujet_de(formes, analyses, a.tete)
                if sujet and sujet[1] != a.tete:
                    sujet = None
                elif sujet:
                    sujet = (sujet[0], j) + sujet[2:]
            if not sujet or sujet[1] != j or "Number" not in sujet[2] or sujet[3].lower() in ("vous", "on"):
                return None
            cible = self._forme_verbale(lectures, VerbForm="Part", Tense="Past", Gender=sujet[2].get("Gender", "Masc"),
                                        Number=sujet[2]["Number"])
            if cible and cible.ortho != forme:
                return Attente({}, "participe_apres_etre", k, formes[k], forme_cible=cible.ortho)
            return None
        if not all(_traits(l).get("VerbForm") == "Fin" and l.lemme.endswith("éer") for l in lectures):
            return None
        autres = [l for l in self.lex.lectures(forme) if l.upos not in ("VERB", "AUX")]
        if autres and (analyses[j].upos not in ("VERB", "AUX")
                       or any(l.zipf >= max(v.zipf for v in lectures) - 1.0 for l in autres)):
            return None                                       # « crée » est aussi un nom rare : l'analyse tranche
        sujet = self._sujet_de(formes, analyses, j)
        if not sujet or sujet[1] != j or not {"Gender", "Number"} <= set(sujet[2]):
            return None                                       # sans sujet sûr, on ne choisit pas entre créé / créée
        cible = self._forme_verbale(lectures, VerbForm="Part", Tense="Past", Gender=sujet[2]["Gender"],
                                    Number=sujet[2]["Number"])
        if cible and cible.ortho != forme:
            return Attente({}, "participe_apres_etre", k, formes[k], forme_cible=cible.ortho)
        return None

    def _fini_apres_preposition(self, formes, analyses, j: int, lectures) -> Attente | None:
        """Forme qui n'est que conjuguée, juste après une préposition qui appelle l'infinitif (« consiste à déforme le
        métal », « tend à se propage », « pour mange ») → l'infinitif ; un pronom conjoint peut s'intercaler. Pas après
        « de » hors « avant de », « afin de », « au lieu de » et les « de » de rection (mark) ; pas si la forme a aussi
        une lecture nominale ou adjectivale courante (« à peine », « sans cesse », « à table » ; « la déforme » est
        un nom rare : le verbe l'emporte). (18/10)"""
        if j == 0 or any(l.lemme in ("être", "avoir") for l in lectures):
            return None                                       # « à sont tour », « à l'aura » : homophones (son, aura), pas infinitifs
        k = j - 1
        if formes[k].lower() in _PRONOMS_CONJOINTS and k > 0:
            if analyses[k].upos == "DET":
                return None                                   # « contribué à l'aura mythique » : article, pas pronom
            k -= 1
        prev = formes[k].lower()
        if prev not in _PREPOSITIONS_INF or prev in ("avant", "afin") or analyses[k].upos != "ADP":
            return None                                       # « avant » et « afin » n'appellent l'infinitif que par « de »
        if prev in ("de", "d'", "d’") and not (analyses[k].relation == "mark"
                                              or (k > 0 and formes[k - 1].lower() in ("avant", "afin", "lieu"))):
            return None
        autres = [l for l in self.lex.lectures(formes[j].lower()) if l.upos not in ("VERB", "AUX")]
        if any(l.zipf >= max(v.zipf for v in lectures) - 1.0 for l in autres):
            return None                                       # « à table », « sans compte » : le nom est courant ; pas « la déforme »
        cible = self._forme_verbale(lectures, VerbForm="Inf")
        if cible and cible.ortho != formes[j].lower():
            return Attente({}, "infinitif_apres_preposition", k, formes[k], forme_cible=cible.ortho)
        return None

    def _participe_mal_place(self, formes, analyses, j: int, lectures) -> Attente | None:
        """Participe passé là où l'on attend un infinitif : après « aller » et les semi-auxiliaires, après une
        préposition (« il va mangé », « pour mangé »)."""
        if j == 0:
            return None
        k = j - 1
        if formes[k].lower() in _ADVERBES and k > 0:
            k -= 1
        prev = formes[k].lower()
        toutes = self.lex.lectures(formes[j].lower())
        autres = [l for l in toutes if l.upos in ("NOUN", "ADJ")]
        zipf_verbe = max(l.zipf for l in lectures)
        regle = None
        lp = self.lex.lectures(prev)
        if any(l.upos in ("VERB", "AUX") and l.lemme in _SEMI_AUXILIAIRES and _traits(l).get("VerbForm") == "Fin"
               for l in lp):
            if any(l.zipf >= zipf_verbe - 1.0 for l in autres):
                return None                                   # « font partie », « a découvert »
            regle = "infinitif_apres_verbe"
        elif prev in _PREPOSITIONS_INF and analyses[k].upos == "ADP" and not autres:
            if prev in ("de", "d'", "d’") and not (analyses[k].relation == "mark"
                                                  or (k > 0 and formes[k - 1].lower() in ("avant", "afin", "lieu"))):
                return None
            regle = "infinitif_apres_preposition"
        if not regle:
            return None
        cible = self._forme_verbale(lectures, VerbForm="Inf")
        if cible and cible.ortho != formes[j].lower():
            return Attente({}, regle, k, formes[k], forme_cible=cible.ortho)
        return None

    def _participe(self, formes, analyses, j, lectures, sujet) -> Attente | None:
        aux = self._dependants(analyses, j, AUXILIAIRES)
        lemmes = set()
        for i in aux + [k for k in range(max(0, min(aux, default=j) - 2), min(aux, default=j)) if k not in aux]:
            la = self._lectures(formes[i], {"AUX", "VERB"})
            if i in aux:
                lemmes |= {l.lemme for l in la}
            if la and all(_traits(l).get("VerbForm") == "Inf" for l in la) and (i in aux or formes[i].lower() in ("avoir", "être")):
                return self._participe_apres_infinitif(formes, analyses, j, formes[i].lower())
        if j >= 3:
            # « les fleurs que j'ai cueilli », « la lettre qu'il a écrit » : avec « avoir » et « que » relatif objet,
            # le sujet n'importe pas ; l'auxiliaire peut être sous le seuil de l'analyse
            if lemmes == {"avoir"}:
                k = max(aux)                                  # « qu'il a fait ont payé » : l'auxiliaire le plus proche
            else:
                k = j - 1
                if formes[k].lower() in _ADVERBES_NEGATION and k >= 1:
                    k -= 1                                    # « que nous n'avons pas lu »
                la = self._lectures(formes[k], {"AUX", "VERB"})
                k = k if la and all(l.lemme == "avoir" and _traits(l).get("VerbForm") == "Fin" for l in la) else None
            if k is not None:
                rel = self._relatif_objet(formes, analyses, j, k, structurel=not aux)
                if rel:
                    return rel
        if not sujet or sujet[1] != j:
            nc = self._nombre_copule(formes, analyses, j)
            if nc and "être" in lemmes and not any(formes[i].lower() in ("se", "s'", "s’") for i in range(max(0, nc[1] - 2), j)):
                if nc[2] != nc[1]:                            # « elles sont parti » : le pronom sujet dit tout
                    return Attente(nc[0], "participe", nc[2], formes[nc[2]])
                return Attente(nc[0], "participe_copule", nc[1], formes[nc[1]])
            return None
        debut = max(0, min([sujet[0]] + aux) - 3)
        if any(formes[i].lower() in ("se", "s'", "s’", "me", "m'", "m’", "te", "t'", "t’", "nous", "vous")
               for i in range(debut, j) if i != sujet[0]):
            return None                                       # verbe pronominal : accord avec le réfléchi s'il est objet
        if "être" in lemmes:
            traits = {k: v for k, v in sujet[2].items() if k in ("Number", "Gender")}
            if sujet[3].lower() == "vous":
                traits.pop("Number", None)                    # vouvoiement : « vous êtes parti »
            if not traits or sujet[3].lower() == "on":
                return None
            return Attente(traits, "participe", sujet[0], sujet[3])
        if lemmes == {"avoir"}:
            # pronom objet pluriel juste devant l'auxiliaire (« il les a mangé », « il ne les a pas mangé ») : accord
            # en nombre certain ; le genre n'est pas dit → masculin, l'explication signale le féminin
            k = min(aux)
            if k > 0 and formes[k - 1].lower() == "les":
                return Attente({"Number": "Plur"}, "participe_objet", k - 1, formes[k - 1])
            # objet antéposé : pronom conjoint, relatif « que », objet avant le verbe → on ne tranche pas
            for i in range(max(0, j - 12), j):
                f = formes[i].lower()
                if analyses[i].upos == "PUNCT" and f not in (",",) and i < sujet[0]:
                    continue
                if f in ("que", "qu'", "qu’", "l'", "l’", "la", "les", "le", "me", "m'", "te", "t'", "nous", "vous",
                         "se", "s'", "lesquels", "lesquelles", "laquelle", "lequel", "combien"):
                    return None
            if any(i < j for i in self._dependants(analyses, j, ("obj",))):
                return None
            return Attente({"Number": "Sing", "Gender": "Masc"}, "participe_avoir", aux[0], formes[aux[0]])
        return None

    def _relatif_objet(self, formes, analyses, j: int, k: int, structurel: bool = False) -> Attente | None:
        """« les fleurs que j'ai cueilli » → « cueillies » : « que » relatif, objet du participe ``j`` (auxiliaire en
        ``k``), dont l'antécédent est le nom juste devant (avec ses adjectifs). Entre « que » et l'auxiliaire, rien
        d'autre que le sujet (pronom, ou groupe nominal court) et la négation ; pas les compléments de mesure (« les
        deux heures qu'il a dormi »), ni devant un infinitif (« la chanson que j'ai entendu chanter »)."""
        for i in range(max(1, k - 5), k):
            if formes[i].lower() not in ("que", "qu'", "qu’"):
                continue
            entre = list(range(i + 1, k))
            if not entre or any(analyses[x].upos in ("VERB", "AUX", "PUNCT", "SCONJ", "CCONJ", "ADP") for x in entre):
                return None
            for x in entre:                                   # « les efforts qu'il a fait ont payé » : un verbe entre les deux
                lv = self._lectures(formes[x], {"VERB", "AUX"})
                if lv and any(_traits(l).get("VerbForm") in ("Fin", "Part") for l in lv) \
                        and not (self._lectures(formes[x], {"NOUN"}) and x > i + 1 and analyses[x - 1].upos == "DET"):
                    return None
            if not any(formes[x].lower() in _NOMINATIFS | _NOUS_VOUS or analyses[x].upos in ("NOUN", "PROPN") for x in entre):
                return None
            if not structurel and not (analyses[i].upos == "PRON" and analyses[i].relation == "obj" and analyses[i].tete == j) \
                    and not all(formes[x].lower() in _NOMINATIFS | _NOUS_VOUS | {"ne", "n'", "n’"} for x in entre):
                return None
            a = i - 1
            while a > 0 and analyses[a].upos == "ADJ":
                a -= 1
            if analyses[a].upos != "NOUN" or formes[a].lower() in _ANTECEDENTS_MESURE:
                return None
            if formes[a].lower() == "chose" and a >= 1 and formes[a - 1].lower() in ("quelque", "autre", "grand-chose", "grand"):
                return None                                   # « quelque chose qu'elle n'avait jamais senti » : neutre, invariable
            d = a - 1
            while d > 0 and analyses[d].upos in ("ADJ", "DET", "NUM"):
                d -= 1
            if d >= 0 and formes[d].lower() in ("de", "des", "du", "d'", "d’"):
                return None                                   # « le premier des ministres que le monde a connu » : l'antécédent peut être avant
            if j + 1 < len(formes) and self._lectures(formes[j + 1], {"VERB", "AUX"}) \
                    and all(_traits(l).get("VerbForm") == "Inf" for l in self._lectures(formes[j + 1], {"VERB", "AUX"})):
                return None
            if any(l.lemme in _INVARIABLES_MESURE for l in self._lectures(formes[j], {"VERB", "AUX"})):
                return None
            n = self._nominal(formes, analyses, a)
            if not n or not n[0].get("Number"):
                return None
            genre = n[0].get("Gender") or analyses[a].feats.get("Gender") or "Masc"   # « les livres » : genre ambigu, l'analyse tranche
            return Attente({"Number": n[0]["Number"], "Gender": genre}, "participe_relatif", a, n[1])
        return None

    def _participe_apres_infinitif(self, formes, analyses, j: int, infinitif: str) -> Attente | None:
        """Participe conjugué avec « être » à l'infinitif : « les modules ne peuvent pas être enregistré » → accord
        avec le sujet du semi-auxiliaire (pouvoir, devoir, sembler…) dont le participe dépend ; « d'avoir été
        pesée » (pas de sujet exprimé) : on s'abstient."""
        a = analyses[j]
        if infinitif != "être" or a.relation != "xcomp" or a.tete is None or a.tete < 0 or a.confiance_tete < self.seuil:
            return None
        h = a.tete
        if not any(l.lemme in _SEMI_AUXILIAIRES for l in self._lectures(formes[h], {"VERB", "AUX"})):
            return None
        sujet = self._sujet_de(formes, analyses, h)
        if not sujet or sujet[1] != h or any(formes[i].lower() in ("se", "s'", "s’", "me", "m'", "m’", "te", "t'", "t’",
                                                                      "nous", "vous") for i in range(h, j)):
            return None                                       # « elle peut se faire enregistrer » : pronominal
        traits = {k: v for k, v in sujet[2].items() if k in ("Number", "Gender")}
        if not traits or sujet[3].lower() in ("on", "vous", "ce", "c'", "c’"):
            return None
        return Attente(traits, "participe", sujet[0], sujet[3])

    def _nom(self, formes, analyses, j: int) -> Attente | None:
        lectures = self._lectures(formes[j], {"NOUN"})
        if not lectures:
            return None
        if formes[j].lower() == "demi" and j + 1 < len(formes) and analyses[j + 1].upos == "NOUN":
            return None                                       # « une demi encablure », « une demi heure » : invariable
        dets = [d for d in self._dependants(analyses, j, ("det",)) if d < j]
        nums = self._numeral(formes, analyses, j)
        if nums:
            source = j - 1
            debut = self._debut_numeral(formes, analyses, j)
            return Attente({"Number": nums}, "numeral", source, " ".join(formes[debut:j]))
        if dets:
            d = dets[-1]
            n = _unanime(self._lectures(formes[d], {"DET"}), "Number")
            if n:
                return Attente({"Number": n}, "determinant", d, formes[d])
        elif j >= 1 and formes[j - 1].lower() in _CONTRACTES and analyses[j - 1].upos in ("MWT", "ADP", "DET") \
                and analyses[j - 1].tete == j:
            # « du jeux vidéo », « au réformes » : l'article contracté dit le nombre (le cœur préfère « aux » si le
            # modèle de langue refuse le singulier)
            return Attente({"Number": _CONTRACTES[formes[j - 1].lower()]}, "determinant", j - 1, formes[j - 1])
        elif j >= 2 and formes[j - 1].lower() in ("de", "d'", "d’") and formes[j - 2].lower() in _QUANTITES_NOM \
                and analyses[j - 1].tete == j and _unanime(lectures, "Number") == "Sing" \
                and not (j + 1 < len(formes) and analyses[j + 1].upos == "NUM"):
            # « le nombre de personne », « beaucoup de livre » : nom comptable au pluriel ; le modèle de langue écarte
            # les noms massifs (« beaucoup de bruit », « peu de temps »)
            return Attente({"Number": "Plur"}, "quantite", j - 2, " ".join(formes[j - 2:j]))
        return None

    def _adjectif(self, formes, analyses, j: int) -> Attente | None:
        a = analyses[j]
        if not self._lectures(formes[j], {"ADJ"}) and not self._participes(formes[j]):
            return None                                       # « laminé » : participe employé comme adjectif
        if a.relation == "acl" and a.upos == "VERB" and a.tete is not None and a.tete >= 0 \
                and (a.confiance_tete < self.seuil or j - a.tete > 3) \
                and not any(analyses[i].upos == "PUNCT" for i in range(a.tete, j)):
            return self._tete_unanime(formes, analyses, j)     # tête incertaine : accord sûr si tous les noms concordent
        if a.relation == "acl" and a.tete is not None and (j - a.tete > 3 or any(analyses[i].upos == "PUNCT" for i in range(a.tete, j))):
            return None                                       # « le sac pèse 5 kg, rempli par » : apposition, tête incertaine
        if a.relation in ("amod", "acl") and a.tete is not None and a.tete >= 0 and a.confiance_tete >= self.seuil \
                and analyses[a.tete].upos in ("NOUN", "PROPN"):
            n = self._nominal(formes, analyses, a.tete, avant=j)
            if not n:
                return None
            traits = {k: v for k, v in n[0].items() if k in ("Number", "Gender")}
            if not traits:
                return None
            # un autre nom en amont (« conditions de transferts … originales ») ou le sujet du verbe dont le nom
            # est l'objet (« avaient pris la décision seuls ») s'accorde déjà avec l'adjectif reçu : on s'abstient
            # chaîne « N1 de N2 … » : l'adjectif peut se rapporter à N1 (« conditions de transferts … originales »)
            autres, i = [], a.tete
            while i >= 2 and formes[i - 1].lower() in ("de", "du", "des", "d'", "d’"):
                k = i - 2
                while k > 0 and analyses[k].upos == "ADJ":
                    k -= 1                                    # « marge nette d'intérêts solide » : N1 = marge
                if analyses[k].upos != "NOUN":
                    break
                autres.append(k)
                i = k
            if not autres and a.tete >= 3 and formes[a.tete - 1].lower() in ("la", "le", "les", "l'", "l’") \
                    and formes[a.tete - 2].lower() in ("de", "du", "des", "d'", "d’") and analyses[a.tete - 3].upos == "NOUN":
                autres.append(a.tete - 3)                     # « le tracé de la Méridienne vert »
            tete_nom = analyses[a.tete]
            if (tete_nom.relation == "conj" or self._dependants(analyses, a.tete, ("conj",))) \
                    and self.satisfait(formes[j], "ADJ", {"Number": "Plur"}):
                return None                                   # « d'une banalité, d'une simplicité extrêmes »
            if tete_nom.relation in ("obj", "iobj") and tete_nom.tete is not None and tete_nom.tete >= 0 \
                    and not (j == a.tete + 1 and a.relation == "acl"
                             and any(l.lemme in _EXISTENTIELS for l in self._lectures(formes[tete_nom.tete], {"VERB", "AUX"}))):
                sujet = self._sujet_de(formes, analyses, tete_nom.tete)   # « il existe une bande dessiné » : pas le sujet
                if sujet:
                    autres.append(sujet[0])
            for i in autres:
                m = self._nominal(formes, analyses, i)
                if m and self._satisfait_adj(formes[j], {k: v for k, v in m[0].items() if k in ("Number", "Gender")}):
                    return None
            return Attente(traits, "nom", a.tete, formes[a.tete])
        if j + 1 < len(formes) and analyses[j + 1].upos == "NOUN" and formes[j + 1][:1].islower():
            return None                                       # « elle est bon teint » : locution, pas un attribut du sujet
        if a.relation == "xcomp" and a.upos == "ADJ" and a.tete is not None and 0 <= a.tete < j \
                and a.confiance_tete >= self.seuil and analyses[a.tete].upos == "VERB" \
                and all(l.lemme in _ATTRIBUTIFS for l in self._lectures(formes[a.tete], {"VERB"})) \
                and not any(analyses[i].upos in ("NOUN", "PROPN", "PRON", "VERB") for i in range(a.tete + 1, j)
                            if formes[i].lower() not in ("en", "y")):
            # « ses souffrances deviennent de plus en plus difficile » : attribut du sujet d'un verbe attributif
            sujet = self._sujet_de(formes, analyses, a.tete)
            if not sujet or sujet[1] != a.tete or sujet[3].lower() in ("on", "ce", "c'", "c’", "ça", "cela", "ceci", "vous"):
                return None
            traits = {k: v for k, v in sujet[2].items() if k in ("Number", "Gender")}
            return Attente(traits, "attribut", sujet[0], sujet[3]) if traits else None
        if self._dependants(analyses, j, AUXILIAIRES) or self._copule_adjacente(formes, analyses, j):
            sujet = self._sujet_de(formes, analyses, j)
            traits = {k: v for k, v in sujet[2].items() if k in ("Number", "Gender")} if sujet and sujet[1] == j else {}
            if sujet and sujet[3].lower() == "vous":
                traits.pop("Number", None)
            if sujet and sujet[3].lower() in ("on", "ce", "c'", "c’", "ça", "cela", "ceci"):
                return None
            if "Number" not in traits:
                # sujet introuvable ou collectif (« un groupe de propulseurs est disponibles »), nombre du sujet inconnu
                # (« les autres pays furent tardif ») : la copule, quand sa forme n'est pas ambiguë, dit le nombre
                nc = self._nombre_copule(formes, analyses, j)
                if nc:
                    if nc[2] != nc[1]:                        # « quand il est dure » : le pronom sujet dit tout
                        return Attente(nc[0], "attribut", nc[2], formes[nc[2]])
                    return Attente(nc[0], "attribut_copule", nc[1], formes[nc[1]])
            if not traits or not sujet:
                return None
            return Attente(traits, "attribut", sujet[0], sujet[3])
        return None

    def _tete_unanime(self, formes, analyses, j: int) -> Attente | None:
        """Participe épithète dont l'analyse ne sait pas à quel nom le rattacher (« une section de la commune belge
        de Namur situé ») : si tous les noms de la chaîne nominale qui précède ont le même genre et le même nombre,
        l'accord est sûr quelle que soit la tête ; les noms propres ne comptent pas."""
        noms, k = [], j - 1
        while k >= 0:
            u, f = analyses[k].upos, formes[k].lower()
            if u == "NOUN":
                noms.append(k)
            elif u in ("PROPN", "ADJ", "DET") or f in _LIENS_NOMINAUX:
                pass
            else:
                break
            k -= 1
        if not noms or analyses[j - 1].upos not in ("NOUN", "PROPN", "ADJ") or noms[0] in self._dependants(analyses, j, SUJET):
            return None
        if k >= 0 and (analyses[k].upos in ("CCONJ", "NOUN", "PROPN") or formes[k] == ","
                       or analyses[k].upos == "ADP" and (k == 0 or analyses[k - 1].upos not in ("VERB", "AUX"))):
            return None                                       # « matière et d'énergie projeté », « Études sur le siècle éditées » :
                                                              # la chaîne continue de l'autre côté, la tête peut y être ;
                                                              # pas « définie par la quantité de chaleur dégagé » (verbe + préposition)
        # « les enfants ont regardé la télévision allongés » : le participe peut se rapporter au sujet du verbe qui précède
        for v in range(k, -1, -1):
            if analyses[v].upos in ("VERB", "AUX"):
                if any(l.lemme == "être" for l in self._lectures(formes[v], {"AUX", "VERB"})):
                    break                                     # « Beez est une section de la commune … situé » : attribut
                sujet = self._sujet_de(formes, analyses, v)
                if sujet and self._satisfait_adj(formes[j], {t: x for t, x in sujet[2].items() if t in ("Number", "Gender")}):
                    return None
                break
        traits = None
        for i in noms:
            n = self._nominal(formes, analyses, i)
            t = {k: v for k, v in n[0].items() if k in ("Number", "Gender")} if n else {}
            if len(t) < 2 or (traits is not None and t != traits):
                return None
            traits = t
        return Attente(traits, "nom", noms[0], formes[noms[0]])

    def _determinant(self, formes, analyses, j: int) -> Attente | None:
        """Déterminant d'un nom dont le genre est fixe et sans forme de l'autre genre : « un substance » ; « des »
        devant un adjectif antéposé : « de »."""
        a = analyses[j]
        if formes[j].lower() == "des" and j + 2 < len(formes) and analyses[j + 1].upos == "ADJ" \
                and analyses[j + 1].relation == "amod" and analyses[j + 1].tete == j + 2 \
                and analyses[j + 2].upos == "NOUN" and a.tete == j + 2 and a.confiance_tete >= self.seuil \
                and self._lectures(formes[j + 1], {"ADJ"}):
            return Attente({}, "des_de", j + 1, formes[j + 1], forme_cible="de")
        if a.tete is None or a.tete < 0 or a.tete <= j or a.confiance_tete < self.seuil \
                or analyses[a.tete].upos != "NOUN":
            return None
        nom = formes[a.tete]
        if nom.isupper() or analyses[a.tete].upos == "PROPN":
            return None                                       # « la MLS », « le Monde » : sigle ou nom propre
        if a.tete + 1 < len(formes) and analyses[a.tete + 1].upos in ("NOUN", "PROPN"):
            return None                                       # « le kundalini yoga » : nom composé, le genre est celui du tout
        ld = self._lectures(formes[j], {"DET"})
        gd = _unanime(ld, "Gender")
        ln = self._lectures(nom, {"NOUN"})
        gn = _unanime(ln, "Gender")
        if not gd or not gn or gd == gn or formes[j].lower() in _POSSESSIFS_ELIDES:
            return None
        # le nom existe-t-il dans l'autre genre (ami / amie) ? alors c'est au nom de suivre le déterminant
        if self.contrepartie_genre(nom, gd):
            return None
        return Attente({"Gender": gn}, "genre_nom", a.tete, nom)

    _SUFFIXES = (("trice", "teur"), ("euse", "eur"), ("ienne", "ien"), ("enne", "en"), ("onne", "on"),
                 ("elle", "el"), ("ette", "et"), ("ère", "er"), ("ève", "ef"), ("ve", "f"), ("e", ""))

    def contrepartie_genre(self, nom: str, genre: str) -> str | None:
        """Nom de l'autre genre (ami ↔ amie) : ``autre_genre`` du lexique (lectura-lexicon ≥ 0.3), sinon suffixes."""
        autre = getattr(self.lex, "autre_genre", None)
        if autre is not None:
            try:
                cibles = [c for c in autre(nom.lower()) if any(_traits(l).get("Gender") == genre
                                                              for l in self._lectures(c, {"NOUN"}))]
                if cibles:
                    return cibles[0]
            except Exception:                     # lexique sans la fonction ou base ancienne : suffixes
                pass
        return self._contrepartie_suffixes(nom, genre)

    def _contrepartie_suffixes(self, nom: str, genre: str) -> str | None:
        """Nom de l'autre genre d'un couple (amie → ami, acteur → actrice) : deux lemmes dans LeXiK, retrouvés par
        les suffixes usuels ; None s'il n'y en a pas."""
        nom = nom.lower()
        candidats = []
        for fem, masc in self._SUFFIXES:
            if genre == "Masc" and nom.endswith(fem) and fem:
                candidats.append(nom[: -len(fem)] + masc)
            elif genre == "Fem" and nom.endswith(masc):
                candidats.append(nom[: len(nom) - len(masc)] + fem if masc else nom + fem)
        for cand in candidats:
            if cand and cand != nom and any(l.upos == "NOUN" and _traits(l).get("Gender") == genre
                                            for l in self.lex.lectures(cand)) \
                    and self.lex.validite(cand) == "proposable":
                return cand
        return None

    # ── propositions ──────────────────────────────────────────────────────────

    def proposer(self, formes: list[str], analyses, attentes: dict[int, Attente] | None = None) -> dict[int, Proposition]:
        """Pour chaque attente que la forme reçue ne satisfait pas : la forme du lexique qui la satisfait."""
        if attentes is None:
            attentes = self.attentes(formes, analyses)
        res: dict[int, Proposition] = {}
        for j, att in attentes.items():
            forme = formes[j]
            if att.forme_cible:
                if att.forme_cible != forme.lower():
                    res[j] = Proposition(att.forme_cible, att, self._expliquer(forme, att.forme_cible, att),
                                         analyses[j].confiance_tete)
                continue
            upos = analyses[j].upos
            cats = {"VERB", "AUX"} if upos in ("VERB", "AUX") else {upos}
            lectures = self._lectures(forme, cats) or (self._participes(forme) if upos == "ADJ" else [])
            if att.regle == "sujet":
                lectures = [l for l in lectures if _traits(l).get("Mood") != "Imp"] or lectures
            if att.regle.startswith("participe"):
                # « la lettre qu'il a écrit » : la lecture « il écrit » (présent) ne doit pas passer pour satisfaisante
                lectures = [l for l in lectures if _traits(l).get("VerbForm") == "Part"] or lectures
            if att.conjuguer:
                cible = self._conjuguer(lectures, att.traits)
                if cible and cible.ortho != forme.lower():
                    texte, fusion = cible.ortho, False
                    if j > 0 and formes[j - 1].lower() == "je" and texte[:1] in _VOYELLES:
                        texte, fusion = "j'" + texte, True      # « je ai » → « j'ai »
                    res[j] = Proposition(texte, att, self._expliquer(forme, texte, att),
                                         analyses[att.source].confiance_tete, fusion)
                continue
            if any(self._satisfait(l, att.traits) for l in lectures):
                continue
            cible = self._flechir(forme, lectures, att.traits, analyses[j], formes[j + 1] if j + 1 < len(formes) else "")
            if cible and cible.lower() != forme.lower():
                src = formes[att.source]
                if att.regle == "nom" and "Number" in att.traits and att.source not in attentes and att.source not in res \
                        and not self._memes_sons(forme, cible):
                    # « maître en art martiaux » : l'adjectif est au pluriel et ne se prononce pas comme « martial » ;
                    # si le nom, libre de tout déterminant, a une forme de ce nombre qui se prononce pareil, c'est lui
                    # qu'on accorde (« arts martiaux »)
                    n_adj = _unanime(lectures, "Number")
                    g = att.traits.get("Gender")
                    if n_adj and n_adj != att.traits["Number"] and (not g or self.satisfait(forme, upos, {"Gender": g})):
                        ln = self._lectures(src, {"NOUN"})
                        cible_nom = self._flechir(src, ln, {"Number": n_adj}, analyses[att.source]) if ln else None
                        if cible_nom and self._memes_sons(src, cible_nom):
                            res[att.source] = Proposition(
                                cible_nom, att, f"L'adjectif « {forme} » est au {NOMBRE[n_adj]} et ne se prononce pas comme "
                                                f"« {cible} » : c'est le nom qu'on accorde, « {cible_nom} {forme} ».",
                                analyses[j].confiance_tete)
                            continue
                if att.regle == "sujet" and src.lower() in ("il", "elle") and att.source not in res \
                        and all(_traits(l).get("Number") == "Plur" for l in lectures) and not self._memes_sons(forme, cible):
                    # « Il sont formés » : le verbe est au pluriel et ne se prononce pas comme « est » ; la correction
                    # la plus proche de ce qui a été dit est le pronom (« Ils »), pas le verbe
                    pluriel = "ils" if src.lower() == "il" else "elles"
                    res[att.source] = Proposition(
                        pluriel, att, f"« {src} » est au singulier, mais le verbe « {forme} » est au pluriel et ne se "
                                      f"prononce pas comme « {cible} » : c'est le pronom qu'on corrige, « {pluriel} {forme} ».",
                        analyses[j].confiance_tete)
                    continue
                res[j] = Proposition(cible, att, self._expliquer(forme, cible, att),
                                     analyses[att.source].confiance_tete)
        return res

    def _sons_neutres(self, forme: str) -> set[str]:
        """Formes du lexique qui se prononcent comme ``forme`` au timbre près (e/ɛ : « sauterai » / « sauterait »)."""
        return {h.ortho.lower() for p in self.lex.phones(forme.lower()) for h in self.lex.homophones(p, neutre=True)}

    def _memes_sons(self, a: str, b: str) -> bool:
        """Les deux formes ont une prononciation commune (« mange » / « mangent » ; pas « est » / « sont »)."""
        def sons(f):
            return {"".join(ch for ch in p if ch not in " .‿") for p in self.lex.phones(f.lower())}
        return bool(sons(a) & sons(b))

    @staticmethod
    def _satisfait(l, traits: dict[str, str]) -> bool:
        t = _traits(l)
        return all(t.get(k) in (v, None) for k, v in traits.items())

    def _satisfait_adj(self, forme: str, traits: dict[str, str]) -> bool:
        """Adjectif ou participe employé comme adjectif (« allongés », absent de LeXiK comme ADJ) portant ces traits."""
        return any(self._satisfait(l, traits) for l in self._lectures(forme, {"ADJ"}) + self._participes(forme))

    def satisfait(self, forme: str, upos: str, traits: dict[str, str]) -> bool | None:
        """La forme satisfait-elle les traits ? None si le lexique ne la connaît pas dans cette catégorie."""
        cats = {"VERB", "AUX"} if upos in ("VERB", "AUX") else {upos}
        lectures = self._lectures(forme, cats)
        if not lectures:
            return None
        return any(self._satisfait(l, traits) for l in lectures)

    def _conjuguer(self, lectures, traits):
        for l in lectures:
            if not l.id_lemme:
                continue
            for x in self.lex.formes_de(l.id_lemme):
                t = _traits(x)
                if t.get("Mood") == "Ind" and t.get("Tense") == "Pres" and t.get("VerbForm") == "Fin" \
                        and t.get("Number") == traits["Number"] and t.get("Person") == traits["Person"]:
                    return x
        return None

    _ELIDEES = {"nouvel", "bel", "vieil", "fol", "mol"}        # devant une voyelle : « le nouvel élément », « un bel arbre »

    def _flechir(self, forme: str, lectures, traits: dict[str, str], analyse, suivant: str = "") -> str | None:
        """Forme du même lemme où seuls les traits demandés changent ; la lecture de départ est celle que l'analyse
        préfère (mode, temps), sinon la plus fréquente ; devant une voyelle, la forme élidée de l'adjectif."""
        def accord(l) -> int:
            t = _traits(l)
            return sum(1 for k in ("Mood", "Tense", "VerbForm") if k in t and t[k] == analyse.feats.get(k))

        candidats = []
        for l in sorted(lectures, key=lambda l: (-accord(l), -l.zipf)):
            cible = dict(_traits(l))
            cible.update(traits)
            if cible == _traits(l):
                continue
            for x in self.lex.formes_de(l.id_lemme or l.lemme):
                if x.upos == l.upos and _traits(x) == cible and x.ortho != forme.lower():
                    candidats.append((accord(l), x.zipf, x.ortho))
        if lectures and lectures[0].upos in ("VERB", "AUX") and traits.keys() <= {"Number", "Person"} \
                and all(_traits(l).get("VerbForm") == "Fin" for l in lectures):     # pas les participes (« trompé » → trompez)
            # « le dahu sauterai » → « sauterait » plutôt que « sautera », « il mangeai » → « mangeait » : parmi les
            # formes du lemme qui portent les traits demandés, celle qui se prononce comme ce qui a été écrit
            sons = self._sons_neutres(forme)
            sonores = []
            for l in lectures:
                for x in self.lex.formes_de(l.id_lemme or l.lemme):
                    t = _traits(x)
                    if x.upos == l.upos and x.ortho != forme.lower() and x.ortho in sons and t.get("VerbForm") == "Fin" \
                            and t.get("Mood") not in ("Imp", "Sub") and all(t.get(k) == v for k, v in traits.items()):
                        # pas le subjonctif (« il y ai » → « a », pas « ait ») ; l'indicatif et le conditionnel seulement
                        sonores.append((accord(x), x.zipf, x.ortho))
            if sonores:
                sonores.sort(key=lambda c: (-c[0], -c[1]))
                return sonores[0][2]
        if not candidats:
            return None
        voyelle = suivant[:1].lower() in _VOYELLES
        elidees = [c for c in candidats if c[2] in self._ELIDEES]
        if elidees and voyelle:
            return elidees[0][2]
        candidats = [c for c in candidats if c[2] not in self._ELIDEES] or candidats
        candidats.sort(key=lambda c: (-c[0], -c[1]))
        return candidats[0][2]

    @staticmethod
    def _expliquer(forme: str, cible: str, att: Attente) -> str:
        t = att.traits
        n, g, p = t.get("Number"), t.get("Gender"), t.get("Person")
        desc = " ".join(x for x in (GENRE.get(g, ""), NOMBRE.get(n, "")) if x)
        if p and n:
            desc = f"{PERSONNE[p]} du {NOMBRE[n]}"
        src = att.source_texte
        r = att.regle
        if r == "sujet":
            return f"Le verbe « {forme} » s'accorde avec son sujet « {src} » ({desc}) : « {cible} »."
        if r == "sujet_relatif":
            return (f"Le verbe « {forme} » s'accorde avec son sujet « qui », mis pour « {src} » ({desc}) : « {cible} ».")
        if r == "attribut_copule":
            return (f"« {src} » est au {NOMBRE[n]} : l'attribut « {forme} » suit le même nombre, « {src} {cible} ».")
        if r == "participe_copule":
            return (f"« {src} » est au {NOMBRE[n]} : le participe « {forme} » qui suit s'accorde de même, « {cible} ».")
        if r == "passe_simple":
            return (f"« {forme} » est un participe passé, qui demande un auxiliaire (« a {forme} ») ; ici le verbe est "
                    f"conjugué, après le sujet « {src} » : au passé simple, « {cible} ».")
        if r == "personne":
            return (f"« {forme} » est une forme de la {src} (« je », « tu »), mais la phrase n'a pas de sujet à cette "
                    f"personne : à la 3e personne, on écrit « {cible} ».")
        if r == "conjugaison":
            fin = " ; « je » s'élide devant une voyelle" if cible.startswith("j'") else ""
            return f"Après le sujet « {src} », le verbe « {forme} » se conjugue au présent ({desc}) : « {cible} »{fin}."
        if r == "participe_apres_avoir":
            return (f"Après l'auxiliaire « {src} », on écrit le participe passé, pas l'infinitif : « {cible} » "
                    f"(on dirait « {src} vendu », pas « {src} vendre »).")
        if r == "participe_apres_etre":
            if forme.lower().endswith("er"):
                return (f"Après « {src} » (auxiliaire être), on écrit le participe passé accordé avec le sujet, pas "
                        f"l'infinitif : « {cible} » (on dirait « {src} parti », pas « {src} partir »"
                        + (" ; au féminin : « " + cible + "e »" if cible.endswith("é") else "") + ").")
            return (f"Après « {src} » (auxiliaire être), on écrit le participe passé « {cible} », pas la forme "
                    f"conjuguée « {forme} » (on dirait « {src} vendu », pas « {src} vend »).")
        if r == "participe_relatif":
            return (f"Conjugué avec « avoir », le participe « {forme} » s'accorde avec le complément d'objet direct placé "
                    f"avant lui : « que », mis pour « {src} » ({desc}) : « {cible} ».")
        if r == "participe_objet":
            feminin = cible[:-1] + "es" if cible.endswith("és") else cible + "es"       # mangées, prises, vues
            return (f"Conjugué avec « avoir », le participe « {forme} » s'accorde avec le complément d'objet direct placé "
                    f"avant lui, « {src} » (pluriel) : « {cible} » (« {feminin} » si « {src} » désigne des noms féminins).")
        if r == "infinitif_apres_verbe":
            return (f"Après « {src} », le verbe est à l'infinitif : « {cible} » "
                    f"(on dirait « {src} vendre », pas « {src} vendu »).")
        if r == "infinitif_apres_preposition":
            return f"Après la préposition « {src} », le verbe est à l'infinitif : « {cible} »."
        if r == "determinant":
            return f"Après « {src} », le nom « {forme} » est au {NOMBRE[n]} : « {cible} »."
        if r == "numeral":
            return f"Après le numéral « {src} », le nom « {forme} » est au {NOMBRE[n]} : « {cible} »."
        if r == "quantite":
            return (f"Après « {src} », un nom qu'on peut compter est au pluriel : « {src} {cible} » "
                    f"(un nom de matière ou de notion reste au singulier : « beaucoup de bruit »).")
        if r == "des_de":
            return f"Devant un adjectif placé avant le nom, « des » devient « de » : « de {src} … »."
        if r == "genre_nom":
            return f"« {src} » est un nom {GENRE[g]} : « {cible} {src} »."
        if r == "nom":
            return f"L'adjectif « {forme} » s'accorde avec le nom « {src} » ({desc}) : « {cible} »."
        if r == "attribut":
            return f"L'attribut « {forme} » s'accorde avec le sujet « {src} » ({desc}) : « {cible} »."
        if r == "participe":
            return f"Conjugué avec « être », le participe « {forme} » s'accorde avec le sujet « {src} » ({desc}) : « {cible} »."
        if r == "participe_avoir":
            return (f"Conjugué avec « avoir » sans complément d'objet placé avant, le participe « {forme} » reste au "
                    f"masculin singulier : « {cible} ».")
        return f"« {forme} » → « {cible} » ({r})."
