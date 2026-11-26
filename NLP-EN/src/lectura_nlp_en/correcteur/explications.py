# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Explications pédagogiques des corrections, en français (public francophone qui apprend l'anglais, défaut) ou en
anglais (``langue="en"``). Chaque règle du cœur a son gabarit ; ``expliquer`` choisit selon ``Correction.mesures``.
"""

from __future__ import annotations

LANGUES = ("fr", "en")

PERSONNES = {
    "fr": {"1s": "1re personne du singulier", "2": "2e personne", "3s": "3e personne du singulier",
           "p": "pluriel"},
    "en": {"1s": "first person singular", "2": "second person", "3s": "third person singular", "p": "plural"},
}

GABARITS = {
    "fr": {
        "i_majuscule": "Le pronom « I » (je) s'écrit toujours avec une majuscule en anglais : « {p} ».",
        "apostrophe": "« {o} » est une contraction : l'apostrophe marque les lettres omises, on écrit « {p} ».",
        "doublon": "Le mot « {o} » est répété deux fois de suite.",
        "modal_of": "Après « {m} », on emploie « have » (« {m} have » se prononce comme « {m} of ») : « {m} have ».",
        "variante": "« {o} » est une faute d'orthographe courante : on écrit « {p} ».",
        "hors_lexique": "« {o} » n'est pas un mot anglais connu ; vouliez-vous écrire « {p} » ?",
        "scission": "« {o} » : deux mots collés, on écrit « {p} ».",
        "article_an": "On écrit « an » devant un mot qui commence par un son de voyelle (« {n} » se prononce /{s}/) : "
                      "« an {n} ».",
        "article_a": "On écrit « a » devant un mot qui commence par un son de consonne (« {n} » se prononce /{s}/) : "
                     "« a {n} ».",
        "accord_sujet": "Avec le sujet « {s} » ({pers}), le verbe s'écrit « {p} »{temps}.",
        "accord_3s": " : au présent, la 3e personne du singulier prend un -s",
        "determinant_sing": "« {d} » s'emploie avec un nom au singulier : « {p} ».",
        "determinant_plur": "« {d} » s'emploie avec un nom au pluriel : « {p} ».",
        "determinant_demonstratif": "Devant un nom {nombre}, le démonstratif devient « {p} » (this / these, that / those).",
        "base_modal": "Après le modal « {a} », le verbe reste à la base verbale (sans -s, -ed ni -ing) : « {p} ».",
        "base_do": "Après l'auxiliaire « {a} », c'est lui qui porte le temps : le verbe reste à la base verbale, « {p} ».",
        "base_to": "Après « to », on emploie l'infinitif (base verbale) : « {p} ».",
        "participe_have": "Aux temps composés avec « {a} », on emploie le participe passé : « {p} » (et non le prétérit "
                          "« {o} »).",
        "participe_be": "Au passif, après « {a} », on emploie le participe passé : « {p} ».",
        "confusion": "« {o} » et « {p} » se confondent souvent ; ici le contexte demande « {p} ».",
        "homophone": "« {o} » et « {p} » se prononcent pareil ; ici le contexte demande « {p} ».",
        "variete": "Graphie britannique ; en anglais américain, on écrit « {p} ».",
        "possessif_sing": "Pour dire « le … de … » (possessif), on ajoute « 's » au nom : « {p} ».",
        "possessif_plur": "Possessif d'un nom au pluriel : l'apostrophe se place après le s du pluriel (ou « 's » "
                          "après un pluriel sans s) : « {p} ».",
    },
    "en": {
        "i_majuscule": "The pronoun “I” is always capitalized: “{p}”.",
        "apostrophe": "“{o}” is a contraction: the apostrophe marks the missing letters, so write “{p}”.",
        "doublon": "The word “{o}” is repeated.",
        "modal_of": "After “{m}”, use “have” (“{m} have” sounds like “{m} of”): “{m} have”.",
        "variante": "“{o}” is a common misspelling of “{p}”.",
        "hors_lexique": "“{o}” is not a known English word; did you mean “{p}”?",
        "scission": "“{o}”: two words run together, write “{p}”.",
        "article_an": "Use “an” before a word that begins with a vowel sound (“{n}” is pronounced /{s}/): “an {n}”.",
        "article_a": "Use “a” before a word that begins with a consonant sound (“{n}” is pronounced /{s}/): “a {n}”.",
        "accord_sujet": "With the subject “{s}” ({pers}), the verb is “{p}”{temps}.",
        "accord_3s": ": in the present tense, the third person singular takes -s",
        "determinant_sing": "“{d}” goes with a singular noun: “{p}”.",
        "determinant_plur": "“{d}” goes with a plural noun: “{p}”.",
        "determinant_demonstratif": "Before a {nombre} noun, the demonstrative is “{p}” (this / these, that / those).",
        "base_modal": "After the modal “{a}”, use the base form of the verb (no -s, -ed or -ing): “{p}”.",
        "base_do": "After “{a}”, the auxiliary carries the tense: use the base form, “{p}”.",
        "base_to": "After “to”, use the infinitive (base form): “{p}”.",
        "participe_have": "Perfect tenses with “{a}” take the past participle: “{p}” (not the simple past “{o}”).",
        "participe_be": "The passive after “{a}” takes the past participle: “{p}”.",
        "confusion": "“{o}” and “{p}” are often confused; this context calls for “{p}”.",
        "homophone": "“{o}” and “{p}” sound the same; this context calls for “{p}”.",
        "variete": "British spelling; American English writes “{p}”.",
        "possessif_sing": "The possessive takes an apostrophe: “{p}”.",
        "possessif_plur": "Possessive of a plural noun: the apostrophe goes after the plural s (or 's after a plural "
                          "without s): “{p}”.",
    },
}

# Astuces pour les confusions les plus fréquentes (clé : paire triée), en français et en anglais.
ASTUCES = {
    ("their", "there"): ("« their » = leur(s) (possessif) ; « there » = là, ou « there is / are » (il y a).",
                         "“their” is possessive; “there” is a place, or “there is / are”."),
    ("their", "they're"): ("« they're » = they are ; « their » = leur(s).", "“they're” = they are; “their” is possessive."),
    ("there", "they're"): ("« they're » = they are ; « there » = là, il y a.", "“they're” = they are; “there” = a place."),
    ("it's", "its"): ("« it's » = it is / it has ; « its » = son, sa, ses (possessif, sans apostrophe).",
                      "“it's” = it is / it has; “its” is possessive (no apostrophe)."),
    ("you're", "your"): ("« you're » = you are ; « your » = ton, ta, votre.", "“you're” = you are; “your” is possessive."),
    ("then", "than"): ("« than » sert à comparer (bigger than) ; « then » = ensuite, alors.",
                       "“than” compares (bigger than); “then” means next, or so."),
    ("to", "too"): ("« too » = trop, aussi ; « to » = à, vers, ou marque de l'infinitif.",
                    "“too” means also / excessively; “to” is a preposition or the infinitive marker."),
    ("who's", "whose"): ("« who's » = who is / who has ; « whose » = dont, à qui.",
                         "“who's” = who is / who has; “whose” is possessive."),
    ("lose", "loose"): ("« lose » = perdre ; « loose » = lâche, desserré.", "“lose” = fail to keep; “loose” = not tight."),
    ("affect", "effect"): ("« affect » est le plus souvent le verbe (affecter), « effect » le nom (l'effet).",
                           "“affect” is usually the verb, “effect” the noun."),
    ("accept", "except"): ("« accept » = accepter ; « except » = sauf.", "“accept” = to receive; “except” = but, excluding."),
    ("weather", "whether"): ("« whether » = si (whether or not) ; « weather » = le temps qu'il fait.",
                             "“whether” introduces alternatives; “weather” is rain and sun."),
    ("quiet", "quite"): ("« quite » = assez, tout à fait ; « quiet » = calme.", "“quite” = fairly / completely; “quiet” = silent."),
    ("of", "off"): ("« off » = éteint, hors de (turn off, get off) ; « of » = de.", "“off” = away / not on; “of” = belonging to."),
    ("passed", "past"): ("« passed » est le passé de « pass » ; « past » = passé (nom, adjectif) ou après.",
                         "“passed” is the past of “pass”; “past” is a noun, adjective or preposition."),
    ("advice", "advise"): ("« advice » = le conseil (nom) ; « advise » = conseiller (verbe).",
                           "“advice” is the noun; “advise” is the verb."),
    ("principal", "principle"): ("« principle » = le principe ; « principal » = principal, directeur.",
                                 "“principle” = a rule or belief; “principal” = main, or a head teacher."),
    ("breath", "breathe"): ("« breath » = le souffle (nom) ; « breathe » = respirer (verbe).",
                            "“breath” is the noun; “breathe” is the verb."),
    ("hear", "here"): ("« hear » = entendre ; « here » = ici.", "“hear” = perceive sound; “here” = this place."),
    ("know", "no"): ("« know » = savoir ; « no » = non, aucun.", "“know” = be aware; “no” = negative."),
    ("knew", "new"): ("« knew » = passé de « know » ; « new » = nouveau.", "“knew” is the past of “know”; “new” = not old."),
    ("right", "write"): ("« write » = écrire ; « right » = droit, juste.", "“write” = put words down; “right” = correct."),
    ("threw", "through"): ("« threw » = passé de « throw » (lancer) ; « through » = à travers.",
                           "“threw” is the past of “throw”; “through” = from one side to the other."),
    ("peace", "piece"): ("« peace » = la paix ; « piece » = un morceau.", "“peace” = no war; “piece” = a part."),
    ("we're", "were", "where"): ("« where » = où ; « were » = passé de « be » ; « we're » = we are.",
                                 "“where” = place; “were” = past of “be”; “we're” = we are."),
}


def astuce(a: str, b: str, langue: str) -> str:
    cle = tuple(sorted({a.lower(), b.lower()}))
    for k, (fr, en) in ASTUCES.items():
        if set(cle) <= set(k):
            return fr if langue == "fr" else en
    return ""


def texte(regle: str, langue: str, **champs) -> str:
    g = GABARITS.get(langue if langue in GABARITS else "fr", GABARITS["fr"])
    return g.get(regle, "").format(**champs) if regle in g else ""
