# Copyright (C) 2025-2026 Maxime Carrière (Lectura)
# Licence : AGPL-3.0-or-later — voir LICENCE.txt
# Licence commerciale disponible — contact via https://www.lectura.world
"""Commande : ``python -m lectura_lexicon convertir|denuder|indexer|installer|tailles|mode``.

    python -m lectura_lexicon convertir LeXiK/ ma_base/lexicon.db            # depuis LeXiK téléchargée
    python -m lectura_lexicon convertir LeXiK/ standard.db --taille standard  # formes de fréquence > 0
    python -m lectura_lexicon convertir Lexique383.tsv l3.db --format lexique3
    python -m lectura_lexicon installer lexicon-fr-standard.db.xz            # base livrée (nue), index compris
    python -m lectura_lexicon tailles [--langue en]
    python -m lectura_lexicon mode [--langue en]                               # mode qu'utiliserait Lexicon()
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m lectura_lexicon", description="Module Lexicon (lectura-lexicon)")
    sous = p.add_subparsers(dest="commande", required=True)
    c = sous.add_parser("convertir", help="construire une base au format rapide depuis un lexique (hors ligne)")
    c.add_argument("source", help="LeXiK (dossier ou lexik_formes_mots.tsv.gz), Lexique 3, GLÀFF, CSV/TSV")
    c.add_argument("sortie", help="fichier lexicon.db (ou dossier) à écrire")
    c.add_argument("--langue", default="fr", choices=("fr", "en"))
    c.add_argument("--format", default="auto", choices=("auto", "lexik", "lexique3", "glaff", "tableau"))
    c.add_argument("--separateur", help="séparateur d'un CSV/TSV maison (détecté sinon)")
    c.add_argument("--phonetique", default="api", choices=("api", "lexique3"),
                   help="code phonétique d'un CSV/TSV maison (api par défaut)")
    c.add_argument("--variantes", help="TSV « forme, graphie usuelle » des graphies variantes")
    c.add_argument("--taille", default="complet", choices=("complet", "standard", "mini"),
                   help="complet : toutes les formes validées ; standard : fréquence > 0 ; mini : zipf ≥ --seuil")
    c.add_argument("--seuil", type=float, default=2.0, help="zipf minimal de la mini (2 par défaut)")
    c.add_argument("--zipf-voisins", type=float, default=1.0)
    c.add_argument("--suppressions", type=int, default=1, choices=(1, 2))
    c.add_argument("--avec-non-classes", action="store_true",
                   help="LeXiK : garder les formes « non classées » (drapeau non_valide ; exclues par défaut)")
    d = sous.add_parser("denuder", help="base nue (sans index) tirée d'une base au format rapide")
    d.add_argument("base")
    d.add_argument("sortie")
    d.add_argument("--taille", default="complet", choices=("complet", "standard", "mini"),
                   help="complet : toutes les formes ; standard : zipf > 0 ; mini : zipf ≥ --seuil")
    d.add_argument("--seuil", type=float, default=2.0, help="zipf minimal de la mini (2 par défaut)")
    d.add_argument("--complements", default="", help="variantes, marque, confiance (séparés par des virgules)")
    x = sous.add_parser("indexer", help="construire la base au format rapide (index compris) depuis une base nue")
    x.add_argument("nue")
    x.add_argument("sortie")
    x.add_argument("--zipf-voisins", type=float, default=1.0)
    x.add_argument("--suppressions", type=int, default=1, choices=(1, 2))
    i = sous.add_parser("installer", help="installer une base Lexicon livrée (base nue .db ou .db.xz), index compris")
    i.add_argument("source", help="base reçue : lexicon-<langue>-<taille>.db.xz")
    i.add_argument("--dossier", help="dossier d'installation (défaut : ~/.lectura/models/lexicon[_en])")
    i.add_argument("--sha256", help="empreinte attendue de la base reçue")
    t = sous.add_parser("tailles", help="bases installées en local")
    t.add_argument("--langue", default="fr", choices=("fr", "en"))
    t.add_argument("--dossier")
    m = sous.add_parser("mode", help="mode (api ou local) que choisirait Lexicon() ici")
    m.add_argument("--langue", default="fr", choices=("fr", "en"))
    a = p.parse_args(argv)

    if a.commande == "convertir":
        from .conversion import convertir

        try:
            convertir(a.source, a.sortie, a.langue, a.format, taille=a.taille, seuil=a.seuil, zipf_voisins=a.zipf_voisins,
                      suppressions=a.suppressions, separateur=a.separateur, phonetique=a.phonetique,
                      variantes=a.variantes, non_classes=a.avec_non_classes, afficher=print)
        except (ValueError, FileNotFoundError) as e:
            print(f"erreur : {e}", file=sys.stderr)
            return 1
        return 0
    if a.commande in ("denuder", "indexer"):
        from . import nue

        try:
            if a.commande == "denuder":
                nue.denuder(a.base, a.sortie, a.taille, a.seuil, [x for x in a.complements.split(",") if x],
                            afficher=print)
            else:
                nue.indexer(a.nue, a.sortie, a.zipf_voisins, a.suppressions, afficher=print)
        except (ValueError, FileNotFoundError) as e:
            print(f"erreur : {e}", file=sys.stderr)
            return 1
        return 0
    if a.commande == "mode":
        from ._lexicon import choisir_mode

        print(choisir_mode(a.langue))
        return 0
    if a.commande == "installer":
        from .nue import installer

        try:
            installer(a.source, a.dossier, a.sha256, afficher=print)
        except (ValueError, FileNotFoundError) as e:
            print(f"erreur : {e}", file=sys.stderr)
            return 1
        return 0
    if a.langue == "fr":
        from .fr import allegee
    else:
        from .en import allegee
    trouvees = allegee.installees(a.dossier)
    for taille in ("mini", "standard", "complet"):
        print(f"{taille:9} {trouvees.get(taille, 'non installée')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
