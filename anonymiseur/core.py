"""Anonymisation réversible : remplace les données sensibles par des étiquettes
([PERSONNE_1], [IBAN_1]...) puis les remet à leur place dans la réponse d'une IA."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .detectors import _TITLES, PRIORITY, Entity, detect_rules
from .ner import detect_ner, load_ner


def resolve_overlaps(entities: Iterable[Entity]) -> List[Entity]:
    """Garde la détection la plus longue quand plusieurs se chevauchent
    (à longueur égale : priorité du type), puis trie par position."""
    ordered = sorted(entities, key=lambda e: (-e.length, PRIORITY.get(e.type, 99), e.start))
    chosen: List[Entity] = []
    for e in ordered:
        if all(e.end <= c.start or e.start >= c.end for c in chosen):
            chosen.append(e)
    return sorted(chosen, key=lambda e: e.start)


def _normalize(type_: str, text: str) -> str:
    """Clé de comparaison : deux écritures de la même donnée -> même étiquette."""
    if type_ in ("IBAN", "NUM_SECU", "CARTE"):
        return re.sub(r"[^0-9A-Za-z]", "", text).upper()
    if type_ == "TELEPHONE":
        d = re.sub(r"\D", "", text)
        if d.startswith("00"):
            d = d[2:]
        if d.startswith("33") and len(d) == 12 and d[2] == "0":  # +33 (0)6...
            d = "0" + d[3:]
        elif d.startswith("33") and len(d) == 11:  # +33 6...
            d = "0" + d[2:]
        return d
    text = " ".join(text.split())
    if type_ == "PERSONNE":  # « Mme Claire Martin » et « Claire Martin » = même personne
        text = re.sub(rf"^{_TITLES}\s+", "", text)
    return text.lower()


@dataclass
class AnonymizationResult:
    text: str
    mapping: Dict[str, str]  # étiquette -> valeur d'origine (SENSIBLE)
    entities: List[Entity]

    def counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for e in self.entities:
            counts[e.type] = counts.get(e.type, 0) + 1
        return counts


@dataclass
class DeanonymizationResult:
    text: str
    unknown_labels: List[str]  # étiquettes de la réponse absentes de la table


class Anonymizer:
    def __init__(
        self,
        extra_terms: Sequence[str] = (),
        use_ner: bool = True,
        ner_labels: Sequence[str] = ("PER", "ORG", "LOC"),
        spacy_model: str = "fr_core_news_md",
    ):
        self.extra_terms = list(extra_terms)
        self.ner_labels = tuple(ner_labels)
        self.ner = None
        self.ner_warning: Optional[str] = None
        if use_ner:
            self.ner, self.ner_warning = load_ner(spacy_model)

    @property
    def ner_active(self) -> bool:
        return self.ner is not None

    def detect(self, text: str) -> List[Entity]:
        entities = detect_rules(text, self.extra_terms)
        if self.ner is not None:
            entities += detect_ner(self.ner, text, self.ner_labels)
        return resolve_overlaps(entities)

    def anonymize(self, text: str, mapping: Optional[Dict[str, str]] = None) -> AnonymizationResult:
        """Anonymise `text`. Passer le `mapping` d'un appel précédent pour garder
        des étiquettes cohérentes entre plusieurs documents d'une même session."""
        mapping = dict(mapping or {})
        keymap: Dict[Tuple[str, str], str] = {}
        counters: Dict[str, int] = {}
        for label, original in mapping.items():
            m = re.fullmatch(r"([A-Z_]+)_(\d+)", label)
            if not m:
                continue
            type_, n = m.group(1), int(m.group(2))
            keymap[(type_, _normalize(type_, original))] = label
            counters[type_] = max(counters.get(type_, 0), n)

        entities = self.detect(text)
        parts: List[str] = []
        pos = 0
        for e in entities:
            key = (e.type, _normalize(e.type, e.text))
            label = keymap.get(key)
            if label is None:
                counters[e.type] = counters.get(e.type, 0) + 1
                label = f"{e.type}_{counters[e.type]}"
                keymap[key] = label
                mapping[label] = e.text
            parts.append(text[pos : e.start])
            parts.append(f"[{label}]")
            pos = e.end
        parts.append(text[pos:])
        return AnonymizationResult("".join(parts), mapping, entities)


# Tolère une réponse d'IA qui a perdu les crochets ou changé la casse :
# « [PERSONNE_1] », « PERSONNE_1 », « [personne_1] ».
_LABEL = r"[A-Za-z]+(?:_[A-Za-z]+)*_\d+"
_LABEL_RE = re.compile(rf"\[\s*({_LABEL})\s*\]|(?<!\w)({_LABEL})(?!\w)")


def deanonymize(text: str, mapping: Dict[str, str]) -> DeanonymizationResult:
    unknown: List[str] = []

    def repl(m: "re.Match[str]") -> str:
        key = (m.group(1) or m.group(2)).upper()
        if key in mapping:
            return mapping[key]
        if key.rsplit("_", 1)[0] in PRIORITY and key not in unknown:
            unknown.append(key)  # ressemble à une de nos étiquettes mais inconnue
        return m.group(0)

    return DeanonymizationResult(_LABEL_RE.sub(repl, text), unknown)
