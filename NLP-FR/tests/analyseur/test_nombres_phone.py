"""Phonétique → orthographe : suites de mots de nombre converties sans mot d'ancrage quand elles sont sûres."""

import pytest

from lectura_nlp_fr.analyseur.moteur import dossier_modeles


@pytest.mark.skipif(dossier_modeles() is None, reason="modèles absents")
@pytest.mark.parametrize("phone, attendu", [
    ("plys də ɥi sɑ̃ mil sɔl.da", "Plus de 800 000 soldats"),
    ("ɑ̃ mil ɥi sɑ̃ ka.tʁə vɛ̃", "En 1880"),
    ("si sɑ̃ twa ʒə nə pø ʁjɛ̃", "Si sans toi je ne peux rien"),      # « si sɑ̃ » : pas assez sûr
    ("il lə di sɑ̃ ʁiʁ", "Il le dit sans rire"),
    ("ʒə di mil fwa", "Je dis mille fois"),                          # verbe : pas un nombre
    ("ɥi sɑ̃ a.bi.tɑ̃", "800 habitants"),                              # nom au pluriel après le nombre
    ("tʁwa ɡʁɑ̃ ʒaʁ.dɛ̃", "3 grands jardins"),
    ("tʁwa u katʁ", "3 ou 4"),                                        # mot-outil : rien à accorder
    ("ɑ̃ mil ɥi sɑ̃ dis.pa.ʁi.sjɔ̃", "En 1800 disparition"),            # année : pas d'accord forcé
    ("ɑ̃.vi.ʁɔ̃ vɛ̃ puʁ sɑ̃ də la pɔ.py.la.sjɔ̃.", "Environ 20 % de la population."),   # « pour cent » : ancre
    ("i.l‿e sy.ʁ‿a sɑ̃ puʁ sɑ̃.", "Il est sûr à 100 %."),
    ("il va a.fɛk.te di.z‿a.ʒɑ̃.", "Il va affecter 10 agents."),       # liaison en z devant un nom : dix
    ("di.z‿e.di.sjɔ̃ sɔ̃ ʁe.a.li.ze.", "10 éditions sont réalisées."),
    ("il nə pʁɑ̃ pa də vɛ̃.", "Il ne prend pas de vin."),
    ("i.l‿a mɑ̃.ʒe sɑ̃.z‿ø.", "Il a mangé sans eux."),
])
def test_nombre_sans_ancre(phone, attendu):
    from lectura_nlp_fr.analyseur import creer_moteur

    assert " ".join(p["ortho"] for p in creer_moteur("local", relecture=False).ecrire(phone)) == attendu
