"""Interface en ligne de commande.

  python -m anonymiseur anonymiser contrat.txt -o contrat.anon.txt
  python -m anonymiseur desanonymiser reponse.txt --table contrat.txt.table.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .core import Anonymizer, deanonymize


def _read(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _write(path: Optional[str], content: str) -> None:
    if path:
        Path(path).write_text(content, encoding="utf-8")
    else:
        sys.stdout.write(content)


def _load_table(path: Path) -> Dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data.get("mapping", {}))


def _save_table(path: Path, mapping: Dict[str, str]) -> None:
    payload = {"version": 1, "mapping": mapping}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)  # la table contient les vraies données : lecture réservée
    except OSError:
        pass


def _highlight(text: str, entities) -> str:
    out, pos = [], 0
    for e in entities:
        out.append(text[pos : e.start])
        out.append(f"\x1b[43;30m{text[e.start:e.end]}\x1b[0m\x1b[2m<{e.type}>\x1b[0m")
        pos = e.end
    out.append(text[pos:])
    return "".join(out)


def cmd_anonymiser(args: argparse.Namespace) -> int:
    terms: List[str] = list(args.terme)
    if args.termes_fichier:
        terms += [t for t in Path(args.termes_fichier).read_text(encoding="utf-8").splitlines() if t.strip()]

    anonymizer = Anonymizer(
        extra_terms=terms,
        use_ner=not args.sans_ner,
        ner_labels=args.labels,
        spacy_model=args.modele,
    )
    if not anonymizer.ner_active:
        reason = anonymizer.ner_warning or "NER désactivé"
        print(
            f"⚠  Mode « règles seules » ({reason}).\n"
            "   Les noms SANS civilité (ex. « Jean Dupont ») ne seront PAS détectés.",
            file=sys.stderr,
        )

    text = _read(args.entree)

    if args.apercu:
        entities = anonymizer.detect(text)
        sys.stdout.write(_highlight(text, entities) + "\n")
        print(f"\n{len(entities)} élément(s) détecté(s) :", file=sys.stderr)
        for e in entities:
            line = text.count("\n", 0, e.start) + 1
            print(f"  ligne {line:>4}  {e.type:<13} {e.text}", file=sys.stderr)
        return 0

    table_path = Path(args.table) if args.table else Path(
        "table.json" if args.entree == "-" else f"{args.entree}.table.json"
    )
    previous = _load_table(table_path) if table_path.exists() else {}
    result = anonymizer.anonymize(text, previous)
    _write(args.sortie, result.text)
    _save_table(table_path, result.mapping)

    summary = ", ".join(f"{n} {t}" for t, n in sorted(result.counts().items())) or "aucun élément"
    print(f"\n✓ Anonymisé : {summary}", file=sys.stderr)
    print(f"✓ Table de correspondance : {table_path}  (CONFIDENTIELLE, ne pas l'envoyer à l'IA)", file=sys.stderr)
    print("→ Relis le texte anonymisé avant de l'envoyer (option --apercu pour voir les détections).", file=sys.stderr)
    return 0


def cmd_desanonymiser(args: argparse.Namespace) -> int:
    mapping = _load_table(Path(args.table))
    result = deanonymize(_read(args.entree), mapping)
    _write(args.sortie, result.text)
    if result.unknown_labels:
        print(
            "⚠  Étiquettes absentes de la table (inventées par l'IA ?) : "
            + ", ".join(result.unknown_labels),
            file=sys.stderr,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m anonymiseur",
        description="Anonymise un texte en local avant envoi à une IA, puis restaure la réponse.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("anonymiser", help="remplace les données sensibles par des étiquettes")
    a.add_argument("entree", help="fichier texte, ou - pour lire l'entrée standard")
    a.add_argument("-o", "--sortie", help="fichier de sortie (défaut : sortie standard)")
    a.add_argument("--table", help="table de correspondance JSON (défaut : <entree>.table.json). "
                                   "Si elle existe, elle est réutilisée pour garder des étiquettes cohérentes.")
    a.add_argument("--terme", action="append", default=[], metavar="TEXTE",
                   help="terme à toujours masquer (client, projet...). Répétable.")
    a.add_argument("--termes-fichier", metavar="FICHIER", help="un terme à masquer par ligne")
    a.add_argument("--sans-ner", action="store_true", help="désactive la détection des noms par spaCy")
    a.add_argument("--labels", nargs="+", default=["PER", "ORG", "LOC"], choices=["PER", "ORG", "LOC"],
                   help="types d'entités spaCy à masquer (défaut : PER ORG LOC)")
    a.add_argument("--modele", default="fr_core_news_md", help="modèle spaCy (défaut : fr_core_news_md)")
    a.add_argument("--apercu", action="store_true",
                   help="affiche les détections surlignées, sans rien écrire")
    a.set_defaults(func=cmd_anonymiser)

    d = sub.add_parser("desanonymiser", help="remet les vraies valeurs dans la réponse de l'IA")
    d.add_argument("entree", help="réponse de l'IA (fichier, ou - pour l'entrée standard)")
    d.add_argument("--table", required=True, help="table de correspondance créée à l'anonymisation")
    d.add_argument("-o", "--sortie", help="fichier de sortie (défaut : sortie standard)")
    d.set_defaults(func=cmd_desanonymiser)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
