# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Tables du correcteur anglais : contractions sans apostrophe, modaux, déterminants, mots répétés admis, paires de
confusion. Relevées sur les fautes courantes de l'anglais écrit (apprenants, web) ; chaque usage passe par le
cœur (``coeur.py``), et les cas ambigus par le modèle de langue."""

from __future__ import annotations

# Contractions écrites sans apostrophe. Sûres : la forme sans apostrophe n'est pas un mot courant.
APOSTROPHES = {
    "dont": "don't", "doesnt": "doesn't", "didnt": "didn't", "isnt": "isn't", "wasnt": "wasn't", "werent": "weren't",
    "arent": "aren't", "hasnt": "hasn't", "havent": "haven't", "hadnt": "hadn't", "couldnt": "couldn't",
    "wouldnt": "wouldn't", "shouldnt": "shouldn't", "mustnt": "mustn't", "neednt": "needn't", "mightnt": "mightn't",
    "shant": "shan't", "aint": "ain't", "im": "I'm", "ive": "I've", "youre": "you're", "theyre": "they're",
    "youve": "you've", "theyve": "they've", "weve": "we've", "youll": "you'll", "theyll": "they'll",
    "thats": "that's", "whats": "what's", "theres": "there's", "heres": "here's", "wheres": "where's",
    "whos": "who's", "shes": "she's", "itll": "it'll", "wouldve": "would've", "couldve": "could've",
    "shouldve": "should've", "mightve": "might've", "mustve": "must've", "youd": "you'd", "theyd": "they'd",
    "howd": "how'd", "whatre": "what're", "wholl": "who'll", "thatll": "that'll", "everyones": "everyone's",
}
# Ambiguës : la forme sans apostrophe est aussi un mot (cant, wont, lets…) : modèle de langue exigé.
APOSTROPHES_AMBIGUES = {"cant": "can't", "wont": "won't", "lets": "let's", "hes": "he's", "ill": "I'll",
                        "were": "we're", "id": "I'd", "hed": "he'd", "wed": "we'd", "shell": "she'll",
                        "well": "we'll", "its": "it's", "hell": "he'll", "whose": "who's", "your": "you're"}
# Les mêmes, utilisées seulement pour proposer ; les dernières sont traitées par les confusions.
APOSTROPHES_AMBIGUES_ACTIVES = {"cant", "wont", "lets"}

MODAUX = {"can", "could", "will", "would", "shall", "should", "may", "might", "must", "ca", "wo"}
MODAUX_OF = {"could", "would", "should", "must", "might", "may"}

DET_SINGULIER = {"a", "an", "this", "that", "each", "every", "another", "one", "either", "neither"}
DET_PLURIEL = {"these", "those", "many", "several", "few", "both", "various", "numerous", "two", "three", "four",
               "five", "six", "seven", "eight", "nine", "ten", "twelve", "twenty", "hundred", "thousand", "million"}
DEMONSTRATIFS = {"this": "these", "these": "this", "that": "those", "those": "that"}
# Après « a » : « a few days », « a lot of », « a couple of »… (le nom dépend du quantifieur, pas de l'article)
QUANTIFIEURS = {"few", "lot", "lots", "couple", "number", "great", "good", "dozen", "hundred", "thousand", "million",
                "billion", "series", "pair", "set", "total", "majority", "variety", "range", "group", "bunch",
                "other", "more", "further", "additional", "extra", "last", "first", "next", "past", "following",
                "fewer", "many", "several", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}

# Mots répétés légitimes (« had had », « that that », « is is » dans un discours rapporté…)
DOUBLES_ADMIS = {"had", "that", "is", "do", "bye", "very", "no", "so", "really", "ha", "haha", "la", "now", "yes",
                 "go", "there", "many", "far", "long", "more", "again", "blah", "bla", "boo", "tut", "knock", "well",
                 "say", "much", "too", "on", "and", "hey", "oh", "yeah", "please", "away", "round", "over", "out",
                 "night", "chop", "hip", "pom", "tom", "can", "mi", "dum", "ho", "ta", "ba", "boom", "bang", "tick",
                 "who", "what", "you", "it", "her", "will", "one", "by", "aye", "million", "billion", "thousand", "ding", "dong", "bla", "wee", "hush",
                 "quack", "cha", "cho", "wow", "come", "run", "here", "baby", "never", "less", "worse", "better",
                 "faster", "higher", "harder", "bigger", "louder", "closer", "deeper", "longer", "slower", "on"}

# Paires et groupes de confusion (homophones ou presque) jugés par le modèle de langue.
CONFUSIONS = [
    {"their", "there", "they're"}, {"your", "you're"}, {"its", "it's"}, {"to", "too"}, {"then", "than"},
    {"whose", "who's"}, {"lose", "loose"}, {"affect", "effect"}, {"affects", "effects"}, {"affected", "effected"},
    {"accept", "except"}, {"weather", "whether"}, {"quiet", "quite"}, {"advice", "advise"},
    {"principal", "principle"}, {"principals", "principles"}, {"breath", "breathe"}, {"passed", "past"},
    {"choose", "chose"}, {"hear", "here"}, {"know", "no"}, {"knew", "new"}, {"threw", "through"}, {"peace", "piece"},
    {"were", "where", "we're"}, {"brake", "break"}, {"aloud", "allowed"}, {"desert", "dessert"},
    {"lead", "led"}, {"loose", "lose"}, {"site", "sight", "cite"}, {"complement", "compliment"},
    {"stationary", "stationery"}, {"bear", "bare"}, {"wear", "where"}, {"weak", "week"}, {"waist", "waste"},
    {"whole", "hole"}, {"which", "witch"}, {"sea", "see"},
    {"meet", "meat"}, {"plane", "plain"}, {"role", "roll"}, {"tail", "tale"}, {"steal", "steel"},
    {"threw", "through"}, {"later", "latter"}, {"lie", "lay"}, {"rise", "raise"},
    {"council", "counsel"}, {"personal", "personnel"}, {"emigrate", "immigrate"}, {"ensure", "insure"},
    {"its", "it's"}, {"every day", "everyday"}, {"a lot", "allot"}, {"alter", "altar"}, {"bored", "board"},
    {"course", "coarse"}, {"die", "dye"}, {"dying", "dyeing"}, {"fair", "fare"}, {"flour", "flower"},
    {"heal", "heel"}, {"hour", "our"}, {"mail", "male"}, {"pain", "pane"}, {"pair", "pear"}, {"pause", "paws"},
    {"poor", "pour", "pore"}, {"pray", "prey"}, {"rain", "reign", "rein"}, {"sail", "sale"}, {"scene", "seen"},
    {"sole", "soul"}, {"son", "sun"}, {"stair", "stare"}, {"suite", "sweet"}, {"vain", "vein"},
    {"wait", "weight"}, {"way", "weigh"}, {"wood", "would"}, {"heard", "herd"}, {"allowed", "aloud"},
]
# Écartées après mesure (WikEd dev, 16/10) : form / from, was / were, than / that, thought / though, been / being,
# lose / loss, of / off, write / right, buy / by : le 4-grammes s'y trompe trop (« to form », « school of thought »,
# « 10% off », « to write O levels »).

# Mots-outils dont la confusion n'est proposée que par la liste ci-dessus (jamais par homophonie générique).
OUTILS = {"a", "an", "the", "to", "too", "two", "for", "four", "fore", "i", "eye", "aye", "be", "bee", "by", "buy",
          "bye", "in", "inn", "one", "won", "or", "oar", "ore", "our", "hour", "so", "sew", "sow", "no", "know",
          "new", "knew", "not", "knot", "would", "wood", "we", "wee", "i'll", "isle", "aisle", "him", "hymn",
          "which", "witch", "their", "there", "they're", "your", "you're", "its", "it's", "here", "hear", "were",
          "where", "we're", "whose", "who's", "then", "than", "of", "off", "u", "you", "ewe", "yew", "oh", "owe",
          "o", "ah", "are", "r", "c", "see", "sea", "y", "why", "t", "tea", "tee", "b", "q", "queue", "cue"}

# Variantes britanniques / américaines homophones que le lexique ne marque pas toujours (humour, cheque…) : la tête de
# graphie ne propose pas l'une pour l'autre (les deux variétés sont admises ; ``variete="US"`` a sa propre étape).
VARIANTES_GB_US = {frozenset(p) for p in [
    ("cheque", "check"), ("cheques", "checks"), ("draught", "draft"), ("draughts", "drafts"), ("storey", "story"),
    ("storeys", "stories"), ("tyre", "tire"), ("tyres", "tires"), ("kerb", "curb"), ("kerbs", "curbs"),
    ("plough", "plow"), ("grey", "gray"), ("programme", "program"), ("programmes", "programs"), ("czar", "tsar"),
    ("ok", "okay"), ("mould", "mold"), ("moult", "molt"), ("sulphur", "sulfur"), ("aeroplane", "airplane"),
    ("cosy", "cozy"), ("pyjamas", "pajamas"), ("whisky", "whiskey"), ("disc", "disk"), ("annexe", "annex"),
    ("axe", "ax"), ("racquet", "racket"), ("manoeuvre", "maneuver"), ("doughnut", "donut"), ("catalogue", "catalog"),
]}


def variantes_gb_us(a: str, b: str) -> bool:
    """Deux graphies d'un même mot selon la variété (table, ou -our / -or, -re / -er, -ogue / -og)."""
    if frozenset((a, b)) in VARIANTES_GB_US:
        return True
    for gb, us in (("our", "or"), ("re", "er"), ("ogue", "og"), ("ours", "ors"), ("res", "ers")):
        for x, y in ((a, b), (b, a)):
            if x.endswith(gb) and y.endswith(us) and x[: -len(gb)] == y[: -len(us)] and len(y) > len(us) + 2:
                return True
    return False
