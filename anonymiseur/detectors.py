"""Détection de données sensibles par règles (regex + validations).

Principe de conception : pour un outil de confidentialité, un faux positif
(on masque trop) est moins grave qu'un faux négatif (une donnée fuit).
Les validations sont donc volontairement tolérantes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional


@dataclass(frozen=True)
class Entity:
    start: int
    end: int
    type: str
    text: str

    @property
    def length(self) -> int:
        return self.end - self.start


# Si deux détections se chevauchent avec la même longueur, le type avec la
# priorité la plus basse l'emporte. Sert aussi à lister les types connus.
PRIORITY = {
    "EMAIL": 0,
    "IBAN": 1,
    "NUM_SECU": 2,
    "TELEPHONE": 3,
    "CARTE": 4,
    "TERME": 5,
    "ADRESSE": 6,
    "PERSONNE": 7,
    "ORGANISATION": 8,
    "LIEU": 9,
}

# --------------------------------------------------------------------------
# Expressions régulières
# --------------------------------------------------------------------------

EMAIL = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}"
)

IBAN = re.compile(
    r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?:[ \u00a0]?[A-Z0-9]{4}){2,7}"
    r"(?:[ \u00a0]?[A-Z0-9]{1,3})?(?![A-Za-z0-9])"
)

PHONE_FR = re.compile(
    r"(?<![\w+])(?:(?:\+|00)33[ \u00a0.\-]?(?:\(0\)[ \u00a0.\-]?)?|0)"
    r"[1-9](?:[ \u00a0.\-]?\d{2}){4}(?!\d)"
)

PHONE_INTL = re.compile(r"(?<![\w+])\+\d[\d ()\u00a0.\-]{7,17}\d(?!\d)")

# Numéro de sécurité sociale : 13 chiffres (+ clé de 2 chiffres).
# Pas de validation de la clé : une clé fausse reste une donnée sensible.
NIR = re.compile(
    r"(?<!\d)[12][ \u00a0.]?\d{2}[ \u00a0.]?(?:0[1-9]|1[0-2]|[2-9]\d)[ \u00a0.]?"
    r"(?:\d{2}|2[ABab])[ \u00a0.]?\d{3}[ \u00a0.]?\d{3}(?:[ \u00a0.]?\d{2})?(?!\d)"
)

CARD = re.compile(r"(?<!\d)(?:\d[ \-]?){12,18}\d(?!\d)")

# Adresses postales françaises. Les types de voie ambigus (« place », « route »)
# exigent une particule ou une majuscule derrière pour éviter « 3 place disponible ».
_STREET_STRONG = (
    r"rue|avenue|av\.?|boulevard|bd|chemin|impasse|all[ée]e|quai|passage|"
    r"square|r[ée]sidence|lotissement"
)
_STREET_WEAK = r"place|route"
_CITY = r"\d{5}[ \u00a0]+[A-ZÀ-Ý][\w'’\-]+(?:[ \-][A-ZÀ-Ý][\w'’\-]+){0,3}"
ADDRESS = re.compile(
    r"\b\d{1,4}(?:[ ]?(?:bis|ter))?[,\s]+"
    r"(?:"
    rf"(?i:{_STREET_STRONG})\s+[^\n,;]{{2,50}}?"
    r"|"
    rf"(?i:{_STREET_WEAK})\s+(?:(?i:de|du|des|la|le|les)\s+|(?i:d|l)['’]|(?=[A-ZÀ-Ý]))"
    r"[^\n,;]{2,50}?"
    r")"
    r"(?=\s*(?:[,;\n]|\.(?:\s|$)|$)|\s+\d{5}\b)"
    rf"(?:[,\s]+{_CITY})?"
)

# Personne introduite par une civilité (« Mme Dupont », « M. Jean Martin »).
_TITLES = (
    r"(?:M\.|Mme|Mlle|Monsieur|Madame|Mademoiselle|Ma[iî]tre|Me|"
    r"Dr\.?|Docteur|Pr\.?|Professeur)"
)
_NAME_WORD = r"[A-ZÀ-Ý][\w'’\-]+"
PERSON_TITLE = re.compile(rf"(?<!\w){_TITLES}\s+{_NAME_WORD}(?:\s+{_NAME_WORD}){{0,2}}")

# --------------------------------------------------------------------------
# Validations
# --------------------------------------------------------------------------

_IBAN_COUNTRIES = {
    "FR", "DE", "BE", "ES", "IT", "GB", "CH", "LU", "NL", "PT", "IE", "AT",
    "MC", "DK", "SE", "NO", "FI", "PL",
}


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _card_ok(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    return 13 <= len(digits) <= 19 and _luhn_ok(digits)


def _iban_ok(raw: str) -> bool:
    s = re.sub(r"\s", "", raw).upper()
    if not 15 <= len(s) <= 34:
        return False
    rearranged = s[4:] + s[:4]
    number = "".join(str(int(c, 36)) for c in rearranged)
    if int(number) % 97 == 1:
        return True
    # Clé invalide (faute de frappe ?) : on masque quand même si le pays est connu.
    return s[:2] in _IBAN_COUNTRIES


def _intl_phone_ok(raw: str) -> bool:
    return 9 <= len(re.sub(r"\D", "", raw)) <= 15


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


def detect_rules(text: str, extra_terms: Iterable[str] = ()) -> List[Entity]:
    """Détecte les données sensibles par règles. Les chevauchements ne sont
    pas résolus ici (voir `core.resolve_overlaps`)."""
    found: List[Entity] = []

    def add(rx: "re.Pattern[str]", typ: str, validate: Optional[Callable[[str], bool]] = None):
        for m in rx.finditer(text):
            if validate and not validate(m.group()):
                continue
            found.append(Entity(m.start(), m.end(), typ, m.group()))

    add(EMAIL, "EMAIL")
    add(IBAN, "IBAN", _iban_ok)
    add(NIR, "NUM_SECU")
    add(PHONE_FR, "TELEPHONE")
    add(PHONE_INTL, "TELEPHONE", _intl_phone_ok)
    add(CARD, "CARTE", _card_ok)
    add(ADDRESS, "ADRESSE")
    add(PERSON_TITLE, "PERSONNE")

    for term in extra_terms:
        term = term.strip()
        if not term:
            continue
        rx = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
        add(rx, "TERME")

    return found
