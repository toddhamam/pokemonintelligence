"""Parse raw eBay titles into structured tokens.

We don't rely on NLP here — Pokemon titles follow a handful of visible patterns
(set code + card number, grade prefixes like PSA 10 / BGS 9.5, variant markers like
"reverse holo" / "alt art"). The tokenizer extracts what it can; downstream rules
decide whether any candidate entity matches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Detect grade mentions up front — false-positive matching a raw listing against a
# graded rule (or vice versa) is one of the most common errors.
_GRADE_COMPANIES = {
    "psa": "PSA",
    "bgs": "BGS",
    "cgc": "CGC",
    "sgc": "SGC",
    "beckett": "BGS",
}
_GRADE_RX = re.compile(
    r"\b(psa|bgs|cgc|sgc|beckett)\s*(10|9\.5|9|8\.5|8|7|6|5|4|3|2|1|gem ?mint|gem)\b",
    re.IGNORECASE,
)

# Common Pokemon card-number patterns: `071/197`, `#71`, `071`, `SV01-EN-071`.
_CARD_NUMBER_RX = re.compile(
    r"(?:#\s*)?(\d{1,3})\s*/\s*(\d{1,3})|#\s*(\d{1,3})\b",
)

# Variant markers — additive, not mutually exclusive.
_VARIANT_TERMS = {
    "reverse holo": "reverse_holo",
    "reverse-holo": "reverse_holo",
    "rev holo": "reverse_holo",
    "holo": "holo",
    "holographic": "holo",
    "full art": "full_art",
    "fa": "full_art",
    "alt art": "alt_art",
    "alternate art": "alt_art",
    "alt-art": "alt_art",
    "secret rare": "secret_rare",
    "sir": "secret_rare",
    "special illustration": "special_illustration",
    "sar": "special_illustration",
    "gold": "gold",
    "rainbow": "rainbow",
}

# Japanese indicators — even a single one flips the listing out of the English universe.
_JAPANESE_MARKERS = ("japanese", "japan", "jpn", "日本語")


@dataclass(slots=True)
class TitleTokens:
    raw_title: str
    normalized: str
    tokens: set[str] = field(default_factory=set)
    detected_grade_company: str | None = None
    detected_grade: str | None = None
    detected_card_number: str | None = None
    detected_card_set_size: str | None = None
    detected_variant: set[str] = field(default_factory=set)
    likely_japanese: bool = False

    def to_features_dict(self) -> dict[str, object]:
        return {
            "raw_title": self.raw_title,
            "normalized": self.normalized,
            "tokens_sample": sorted(self.tokens)[:40],
            "detected_grade_company": self.detected_grade_company,
            "detected_grade": self.detected_grade,
            "detected_card_number": self.detected_card_number,
            "detected_card_set_size": self.detected_card_set_size,
            "detected_variant": sorted(self.detected_variant),
            "likely_japanese": self.likely_japanese,
        }


def tokenize_title(raw_title: str) -> TitleTokens:
    normalized = raw_title.lower().strip()
    # Collapse punctuation to spaces so word-boundary matches work.
    flat = re.sub(r"[^a-z0-9/.#\s]+", " ", normalized)
    flat = re.sub(r"\s+", " ", flat).strip()

    tokens = set(flat.split())

    grade_company: str | None = None
    grade: str | None = None
    m = _GRADE_RX.search(normalized)
    if m:
        grade_company = _GRADE_COMPANIES.get(m.group(1).lower())
        raw_grade = m.group(2).lower()
        grade = (
            "10"
            if raw_grade in {"10", "gem mint", "gem"}
            else raw_grade.upper()
            if grade_company == "BGS"
            else raw_grade
        )

    card_number: str | None = None
    card_set_size: str | None = None
    m2 = _CARD_NUMBER_RX.search(normalized)
    if m2:
        # Pattern 1: NNN/MMM
        if m2.group(1) and m2.group(2):
            card_number = m2.group(1).lstrip("0") or "0"
            card_set_size = m2.group(2)
        # Pattern 2: #NNN
        elif m2.group(3):
            card_number = m2.group(3).lstrip("0") or "0"

    variants: set[str] = set()
    for phrase, tag in _VARIANT_TERMS.items():
        if phrase in normalized:
            variants.add(tag)

    likely_japanese = any(marker in normalized for marker in _JAPANESE_MARKERS)

    return TitleTokens(
        raw_title=raw_title,
        normalized=normalized,
        tokens=tokens,
        detected_grade_company=grade_company,
        detected_grade=grade,
        detected_card_number=card_number,
        detected_card_set_size=card_set_size,
        detected_variant=variants,
        likely_japanese=likely_japanese,
    )
