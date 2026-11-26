# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Explication en français de chaque correction (correcteur pédagogique, 15/10).

Les accords, la conjugaison et les formes verbales sont expliqués par ``accords.py`` (le mot qui impose l'accord est
connu). Ici : les autres types — mot hors du dictionnaire, homophones (avec l'astuce classique quand il y en a une),
quasi-homophones, graphies anciennes, nettoyage du Module.
"""

from __future__ import annotations

CATEGORIES = {"NOUN": "nom", "PROPN": "nom propre", "VERB": "verbe", "AUX": "auxiliaire", "ADJ": "adjectif",
              "ADV": "adverbe", "ADP": "préposition", "DET": "déterminant", "PRON": "pronom",
              "CCONJ": "conjonction", "SCONJ": "conjonction", "NUM": "numéral", "INTJ": "interjection"}

# Astuces d'école pour les paires d'homophones les plus courantes (clé : paire triée, en minuscules).
ASTUCES = {
    ("a", "à"): "« a » (verbe avoir) peut se remplacer par « avait » ; « à » est une préposition.",
    ("est", "et"): "« est » (verbe être) peut se remplacer par « était » ; « et » par « et puis ».",
    ("ou", "où"): "« ou » peut se remplacer par « ou bien » ; « où » indique un lieu ou un moment.",
    ("ce", "se"): "« se » précède un verbe (il se lave) ; « ce » précède un nom (ce livre) ou se trouve dans « ce que », « c'est ».",
    ("ces", "ses"): "« ses » = les siens (on peut dire « les siens ») ; « ces » = ceux-là (on peut dire « ces … -là »).",
    ("son", "sont"): "« sont » (verbe être) peut se remplacer par « étaient » ; « son » = le sien.",
    ("on", "ont"): "« ont » (verbe avoir) peut se remplacer par « avaient » ; « on » = quelqu'un, nous.",
    ("la", "là"): "« là » indique un lieu (on peut dire « ici ») ; « la » est un déterminant ou un pronom.",
    ("l'a", "la"): "« l'a » = « l'avait » (verbe avoir) ; « la » est un déterminant ou un pronom.",
    ("leur", "leurs"): "« leur » devant un verbe est invariable ; devant un nom, « leurs » s'il y a plusieurs choses.",
    ("mais", "mes"): "« mes » = les miens ; « mais » = pourtant.",
    ("mes", "met"): "« met » est le verbe mettre (on peut dire « mettait ») ; « mes » = les miens.",
    ("peu", "peut"): "« peut » est le verbe pouvoir (on peut dire « pouvait ») ; « peu » = pas beaucoup.",
    ("peut", "peux"): "« peux » va avec « je » ou « tu » ; « peut » avec « il », « elle », « on ».",
    ("qu'elle", "quelle"): "« qu'elle » = « qu'il » au féminin ; « quelle » interroge ou s'exclame (quelle idée !).",
    ("sa", "ça"): "« ça » = cela ; « sa » = la sienne.",
    ("n'y", "ni"): "« n'y » = ne + y (il n'y a pas) ; « ni » = et pas non plus.",
    ("d'en", "dans"): "« dans » = à l'intérieur de ; « d'en » = de + en (il vient d'en parler).",
    ("tous", "tout"): "« tous » est au pluriel (tous les jours) ; « tout » au singulier ou adverbe (tout petit).",
    ("quand", "quant"): "« quand » = lorsque ; « quant à » = en ce qui concerne.",
    ("qu'en", "quand"): "« quand » = lorsque ; « qu'en » = que + en (qu'en penses-tu ?).",
    ("plus tôt", "plutôt"): "« plutôt » = de préférence ; « plus tôt » = moins tard.",
    ("d'avantage", "davantage"): "« davantage » = plus ; « d'avantage » = de + avantage.",
    ("près", "prêt"): "« prêt » = préparé (prêt à partir) ; « près » = à côté (près de).",
    ("voir", "voire"): "« voire » = et même ; « voir » = regarder.",
    ("censé", "sensé"): "« censé » = supposé ; « sensé » = plein de bon sens.",
    ("m'a", "ma"): "« m'a » = « m'avait » (verbe avoir) ; « ma » = la mienne.",
    ("t'a", "ta"): "« t'a » = « t'avait » (verbe avoir) ; « ta » = la tienne.",
    ("c'est", "s'est"): "« s'est » précède un participe (il s'est levé) ; « c'est » = cela est.",
    ("c'est", "ces"): "« c'est » = cela est ; « ces » = ceux-là, devant un nom.",
    ("s'est", "ses"): "« s'est » précède un participe (elle s'est levée) ; « ses » = les siens.",
    ("ma", "m'a"): "« m'a » = « m'avait » ; « ma » = la mienne.",
    ("dont", "donc"): "« donc » = par conséquent ; « dont » = de qui, de quoi.",
    ("an", "ans"): "« ans » prend un s après un nombre supérieur à un.",
}

MOTIFS_LEXICAUX = {"accent": "accent manquant ou mal placé", "consonne": "consonne double ou simple",
                   "frappe": "faute de frappe", "clavier": "touche voisine sur le clavier",
                   "transposition": "deux lettres inversées", "colle": "deux mots collés", "elision": "élision",
                   "sms": "abréviation"}


def _categorie(c, lex) -> str:
    upos = c.mesures.get("upos", "")
    if not upos and lex is not None:
        cats = {l.upos for l in lex.lectures(c.proposition.lower())}
        upos = cats.pop() if len(cats) == 1 else ""
    return f" ({CATEGORIES[upos]})" if upos in CATEGORIES else ""


def expliquer(c, lex=None) -> str:
    """Texte d'explication d'une ``Correction`` qui n'en a pas encore."""
    if c.explication:
        return c.explication
    o, p, t = c.original, c.proposition, c.type
    if t == "lexical":
        return f"« {o} » n'est pas dans le dictionnaire ({MOTIFS_LEXICAUX.get(c.motif, c.motif)}) : « {p} »."
    if t == "hors_lexique":
        voie = "par la prononciation" if c.mesures.get("origine") == "phone" else "par l'orthographe"
        return f"« {o} » n'est pas dans le dictionnaire ; le mot le plus proche {voie} qui convient dans la phrase : « {p} »."
    if t == "homophone":
        astuce = ASTUCES.get(tuple(sorted((o.lower(), p.lower()))), "")
        return (f"« {o} » et « {p} » se prononcent de la même façon. Dans cette phrase, c'est « {p} »{_categorie(c, lex)}."
                + (f" {astuce}" if astuce else ""))
    if t == "quasi_homophone":
        return f"« {o} » et « {p} » se prononcent presque de la même façon ; dans cette phrase, c'est « {p} »{_categorie(c, lex)}."
    if t == "graphie":
        return f"« {o} » est une graphie ancienne ou rare ; la graphie usuelle est « {p} »."
    if t == "flexion":
        return f"« {p} » plutôt que « {o} » : la phrase est plus naturelle avec cette forme."
    return f"« {o} » → « {p} »."
