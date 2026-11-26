# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
"""Conversions de formules d'une convention à l'autre (sans modèle) : 19 cas repris de lectura-translator 0.1.2."""
import pytest

from lectura_traducteur.formules import convertir

NB = " "


@pytest.mark.parametrize("forme,type_f,attendu", [
    ("$3.50", "monnaie", f"3,50{NB}$"),
    ("$325m", "monnaie", "325 millions de dollars"),
    ("$1 billion", "monnaie", "1 milliard de dollars"),
    ("14.2%", "pourcentage", f"14,2{NB}%"),
    ("5 p.m.", "heure", f"17{NB}h"),
    ("16:35", "heure", f"16{NB}h{NB}35"),
    ("March 3, 2024", "date", "3 mars 2024"),
    ("1970s", "date", "années 1970"),
    ("1,200", "nombre", f"1{NB}200"),
    ("2012", "nombre", "2012"),
    ("21st", "ordinal", "21e"),
    ("50ft", "mesure", f"50{NB}pieds"),
])
def test_en_fr(forme, type_f, attendu):
    assert convertir(forme, type_f, "en", "fr") == attendu


@pytest.mark.parametrize("forme,type_f,attendu", [
    ("3,50 €", "monnaie", "€3.50"),
    ("250 000 $", "monnaie", "$250,000"),
    ("17 h", "heure", "5 p.m."),
    ("12h30", "heure", "12:30 p.m."),
    ("1er novembre 2013", "date", "November 1, 2013"),
    ("18 %", "pourcentage", "18%"),
    ("2e", "ordinal", "2nd"),
])
def test_fr_en(forme, type_f, attendu):
    assert convertir(forme, type_f, "fr", "en") == attendu
