"""Reconnaissance d'entités nommées (noms, organisations, lieux) via spaCy.

Optionnel : sans spaCy, l'outil fonctionne en « règles seules » et ne détecte
alors que les personnes introduites par une civilité (Mme, M., Dr...).
"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Sequence, Tuple

from .detectors import Entity

# Libellés spaCy (modèles français) -> types internes.
LABEL_MAP = {"PER": "PERSONNE", "ORG": "ORGANISATION", "LOC": "LIEU"}

# On traite le texte paragraphe par paragraphe (séparés par une ligne vide).
_PARAGRAPH = re.compile(r"(?:[^\n]|\n(?!\n))+")


def load_ner(model_name: str = "fr_core_news_md") -> Tuple[Optional[Any], Optional[str]]:
    """Retourne (pipeline, None) ou (None, message d'erreur)."""
    try:
        import spacy  # type: ignore
    except ImportError:
        return None, "spaCy n'est pas installé (pip install spacy)"
    try:
        return spacy.load(model_name), None
    except OSError:
        return None, (
            f"modèle spaCy « {model_name} » introuvable "
            f"(python -m spacy download {model_name})"
        )


def detect_ner(nlp: Any, text: str, labels: Sequence[str] = ("PER", "ORG", "LOC")) -> List[Entity]:
    chunks = list(_PARAGRAPH.finditer(text))
    docs = nlp.pipe(m.group() for m in chunks)
    entities: List[Entity] = []
    for chunk, doc in zip(chunks, docs):
        for ent in doc.ents:
            if ent.label_ in labels and ent.label_ in LABEL_MAP:
                entities.append(
                    Entity(
                        chunk.start() + ent.start_char,
                        chunk.start() + ent.end_char,
                        LABEL_MAP[ent.label_],
                        ent.text,
                    )
                )
    return entities
