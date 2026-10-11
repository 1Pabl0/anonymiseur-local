"""Mesure ce que la détection rate (rappel par type) et ce qu'elle masque à tort.

    python benchmark.py            # règles seules
    python benchmark.py --ner      # avec spaCy si installé

Les documents sont FICTIFS. Le jeu est petit et écrit par l'auteur de l'outil :
les résultats sont donc optimistes. Ajoute tes propres cas (surtout les cas
tordus) dans DOCS / CLEAN_DOCS pour obtenir une mesure réaliste.
"""
from __future__ import annotations

import argparse
from collections import defaultdict

from anonymiseur import Anonymizer

# (texte, termes à toujours masquer, [(type attendu, sous-chaîne sensible)])
DOCS = [
    (
        "Bonjour Mme Martin, voici le RIB de M. Jean Dupont : IBAN FR76 3000 6000 0112 3456 "
        "7890 189. Contact : jean.dupont@example.com, 06 12 34 56 78.",
        [],
        [
            ("PERSONNE", "Mme Martin"),
            ("PERSONNE", "M. Jean Dupont"),
            ("IBAN", "FR76 3000 6000 0112 3456 7890 189"),
            ("EMAIL", "jean.dupont@example.com"),
            ("TELEPHONE", "06 12 34 56 78"),
        ],
    ),
    (
        "Le client habite au 45 avenue des Champs-Élysées, 75008 Paris. "
        "Son numéro de sécurité sociale est le 1 85 05 78 006 084 36.",
        [],
        [
            ("ADRESSE", "45 avenue des Champs-Élysées, 75008 Paris"),
            ("NUM_SECU", "1 85 05 78 006 084 36"),
        ],
    ),
    (
        "Carte bancaire : 4111 1111 1111 1111 (exp 12/27). "
        "Appeler le +33 7 98 76 54 32 ou le 0145678901.",
        [],
        [
            ("CARTE", "4111 1111 1111 1111"),
            ("TELEPHONE", "+33 7 98 76 54 32"),
            ("TELEPHONE", "0145678901"),
        ],
    ),
    (
        "Dossier confidentiel du Projet Phoenix pour la société Acme Industries.",
        ["Projet Phoenix", "Acme Industries"],
        [("TERME", "Projet Phoenix"), ("TERME", "Acme Industries")],
    ),
    (
        "Adresse de livraison : 8 bis impasse des Lilas, 69003 Lyon. Dr. Leroy sera présent.",
        [],
        [
            ("ADRESSE", "8 bis impasse des Lilas, 69003 Lyon"),
            ("PERSONNE", "Dr. Leroy"),
        ],
    ),
    # --- Cas difficiles : les règles seules sont censées les rater ---
    (
        "Contactez Jean Dupont, directeur à Lyon, pour le dossier.",
        [],
        [("PERSONNE", "Jean Dupont"), ("LIEU", "Lyon")],
    ),
    (
        "NOM : DUPONT Jean. Écrire à contact [at] exemple [dot] fr.",
        [],
        [("PERSONNE", "DUPONT Jean"), ("EMAIL", "contact [at] exemple [dot] fr")],
    ),
]

# Textes sans aucune donnée sensible : toute détection est un faux positif.
CLEAN_DOCS = [
    "La réunion aura lieu mardi à 14 h dans la salle 3. Il reste 3 places disponibles et 2 cours de maths.",
    "Le chiffre d'affaires atteint 50 000 euros en 2024, en hausse de 12 %.",
    "Article 12 : le contrat est résilié avec un préavis de 3 mois.",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ner", action="store_true", help="active la détection spaCy si disponible")
    args = parser.parse_args()

    totals = defaultdict(lambda: [0, 0])  # type -> [trouvés, attendus]
    missed = []

    for text, terms, expected in DOCS:
        anonymizer = Anonymizer(extra_terms=terms, use_ner=args.ner)
        entities = anonymizer.detect(text)
        for type_, sub in expected:
            start = text.find(sub)
            assert start >= 0, f"annotation introuvable : {sub!r}"
            end = start + len(sub)
            hit = any(e.type == type_ and e.start <= start and e.end >= end for e in entities)
            totals[type_][1] += 1
            if hit:
                totals[type_][0] += 1
            else:
                missed.append((type_, sub))

    mode = "règles + spaCy" if args.ner else "règles seules"
    if args.ner and not Anonymizer(use_ner=True).ner_active:
        mode = "règles seules (spaCy indisponible)"
    print(f"Mode : {mode}\n")
    print(f"{'Type':<14}{'Trouvés':>9}{'Attendus':>10}{'Rappel':>9}")
    all_found = all_exp = 0
    for type_ in sorted(totals):
        f, e = totals[type_]
        all_found, all_exp = all_found + f, all_exp + e
        print(f"{type_:<14}{f:>9}{e:>10}{f / e:>9.0%}")
    print(f"{'TOTAL':<14}{all_found:>9}{all_exp:>10}{all_found / all_exp:>9.0%}")

    if missed:
        print("\nDonnées NON détectées (fuites potentielles) :")
        for type_, sub in missed:
            print(f"  - {type_:<12} {sub}")

    false_pos = []
    for text in CLEAN_DOCS:
        for e in Anonymizer(use_ner=args.ner).detect(text):
            false_pos.append((e.type, e.text))
    print(f"\nFaux positifs sur {len(CLEAN_DOCS)} textes sans donnée sensible : {len(false_pos)}")
    for type_, sub in false_pos:
        print(f"  - {type_:<12} {sub}")


if __name__ == "__main__":
    main()
