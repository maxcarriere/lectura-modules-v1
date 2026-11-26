# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Couche optionnelle : abréviations et graphies du langage SMS (« bjr », « cc », « cava », « engros », « pk »…)
réécrites en français courant, chacune expliquée. Dictionnaire fermé : une forme n'y entre que si elle n'est pas
un mot français (« vs », « pa » et « ms » restent sous le contrôle du modèle de langue). Les formes qui ne sont que
des fautes d'orthographe (« jai », « cest ») relèvent des autres règles."""

from __future__ import annotations

ABREVIATIONS: dict[str, str] = {
    # salutations
    "cc": "coucou", "bjr": "bonjour", "bjour": "bonjour", "bsr": "bonsoir", "slt": "salut", "biz": "bises",
    "bizz": "bises", "bizou": "bisou", "bizous": "bisous", "a+": "à plus", "a2m1": "à demain", "@+": "à plus",
    # formules
    "cava": "ça va", "sava": "ça va", "stp": "s'il te plaît", "svp": "s'il vous plaît",
    "dsl": "désolé", "dsolé": "désolé", "dac": "d'accord", "dak": "d'accord", "tkt": "t'inquiète", "jsp": "je ne sais pas",
    "jtm": "je t'aime", "jtd": "je t'adore", "mdr": "mort de rire", "ptdr": "pété de rire", "lol": "mort de rire",
    "tfk": "tu fais quoi", "koi29": "quoi de neuf", "rstp": "réponds s'il te plaît", "cmb": "combien",
    # mots-outils
    "pk": "pourquoi", "pq": "pourquoi", "pkoi": "pourquoi", "pcq": "parce que", "pck": "parce que", "paske": "parce que",
    "pasque": "parce que", "parcke": "parce que", "bcp": "beaucoup", "tjs": "toujours", "tjrs": "toujours", "tjr": "toujours",
    "jms": "jamais", "jamé": "jamais", "qd": "quand", "kan": "quand", "qq": "quelques", "qqs": "quelques", "qqn": "quelqu'un",
    "qqun": "quelqu'un", "qqch": "quelque chose", "qqc": "quelque chose", "kelk": "quelque", "kelke": "quelque",
    "tt": "tout", "tte": "toute", "ttes": "toutes", "ts": "tous", "ds": "dans", "pr": "pour", "ac": "avec", "av": "avec",
    "avc": "avec", "ns": "nous", "vs": "vous", "mm": "même", "mme": "même", "nn": "non", "oué": "ouais", "wé": "ouais",
    "wai": "ouais", "koi": "quoi", "kwa": "quoi", "ki": "qui", "ke": "que", "kel": "quel", "kelle": "quelle",
    "keske": "qu'est-ce que", "kom": "comme", "komme": "comme", "koman": "comment", "cmt": "comment", "cmb": "combien",
    "mnt": "maintenant", "mtn": "maintenant", "mtnt": "maintenant", "auj": "aujourd'hui", "ajd": "aujourd'hui",
    "aprem": "après-midi", "pdt": "pendant", "dps": "depuis", "dpuis": "depuis", "lgtps": "longtemps", "lgtmps": "longtemps",
    "engros": "en gros", "entk": "en tout cas", "entouka": "en tout cas", "ptet": "peut-être", "ptete": "peut-être",
    "ptetre": "peut-être", "vrmt": "vraiment", "vrmnt": "vraiment", "grv": "grave", "trkl": "tranquille", "tranquil": "tranquille",
    "nimporte": "n'importe", "cad": "c'est-à-dire", "ya": "il y a", "yavait": "il y avait", "yaura": "il y aura",
    "vla": "voilà", "vlà": "voilà", "msieur": "monsieur", "msieu": "monsieur",
    # verbes contractés
    "chui": "je suis", "chuis": "je suis", "jsuis": "je suis", "jsui": "je suis", "jvais": "je vais", "jveux": "je veux",
    "jpeux": "je peux", "jsais": "je sais", "jsé": "je sais", "jfais": "je fais", "jpense": "je pense", "jcrois": "je crois",
    "jvoulais": "je voulais", "jdois": "je dois", "jconnais": "je connais", "tsais": "tu sais", "tveux": "tu veux",
    "tpeux": "tu peux", "tfais": "tu fais",
    # noms
    "pb": "problème", "pbm": "problème", "prob": "problème", "msg": "message", "tel": "téléphone", "ordi": "ordinateur",
    "bg": "beau gosse", "boulo": "boulot", "resto": "restaurant", "aprèm": "après-midi", "bibli": "bibliothèque",
    "appart": "appartement", "ciné": "cinéma", "prof": "professeur", "fac": "faculté", "exam": "examen",
    "exams": "examens", "vacs": "vacances", "anniv": "anniversaire", "pseudo": "pseudonyme", "photo": "photographie",
}

# formes du dictionnaire qui sont aussi des mots ou des sigles courants : seulement si le modèle de langue préfère nettement
AMBIGUES = {"mme", "vs", "tel", "prof", "photo", "fac", "exam", "exams", "ciné", "resto", "ordi", "prob", "biz",
            "tt", "ts", "ac", "av", "ns", "mm", "nn", "ke", "ki", "kom", "pseudo", "appart", "anniv", "vacs"}
# familières mais pas fautives : ne rien dire d'elles en mode automatique (registre, pas orthographe)
FAMILIERES = {"ordi", "resto", "ciné", "prof", "fac", "exam", "exams", "appart", "anniv", "photo", "pseudo", "aprem",
              "aprèm", "bibli", "boulo", "vacs", "tel"}


def expliquer(forme: str, cible: str) -> str:
    if forme.lower() in FAMILIERES:
        return (f"« {forme} » est une abréviation familière ; en français écrit, on préfère le mot entier : "
                f"« {cible} ».")
    return f"« {forme} » est une abréviation du langage SMS ; en français écrit, on écrit « {cible} »."
