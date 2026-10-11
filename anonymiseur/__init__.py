"""Anonymiseur local : masque les données sensibles avant envoi à une IA cloud."""
from .core import (
    AnonymizationResult,
    Anonymizer,
    DeanonymizationResult,
    deanonymize,
    resolve_overlaps,
)
from .detectors import Entity

__all__ = [
    "Anonymizer",
    "AnonymizationResult",
    "DeanonymizationResult",
    "Entity",
    "deanonymize",
    "resolve_overlaps",
]
__version__ = "0.1.0"
