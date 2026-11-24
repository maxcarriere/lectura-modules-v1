# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Le module Lexique v0 inclus (``lectura_lexicon.Lexique``) lit toujours un CSV/TSV quelconque."""

from conftest import MOTS_FR
from lectura_lexicon import Lexique


def test_lexique_v0_sur_csv(tmp_path):
    src = tmp_path / "lex.csv"
    lignes = ["ortho,phone,lemme,cgram,genre,nombre,freq"]
    cgram = {"NOUN": "NOM", "VERB": "VER", "ADJ": "ADJ", "ADP": "PRE", "PROPN": "NOM"}
    lignes += [f"{o},{p.replace('.', '')},{l},{cgram.get(u, u)},,,{q}" for o, p, l, u, f, q in MOTS_FR]
    src.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    with Lexique(src) as lex:
        assert lex.existe("chat")
        assert lex.phone_de("chat") == "ʃa"
        assert {e["ortho"] for e in lex.homophones("vɛʁ")} == {"verre", "vers", "vert", "vair"}
        assert lex.lemme_de("mangeons") == "manger"
        assert lex.compter(cgram="NOM") >= 5
