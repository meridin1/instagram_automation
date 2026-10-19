"""Detect explicit feature phrases that the local Tier 1 extractor may have only partly captured.

This is deliberately a small, conservative gate: absence of a field alone is not a reason to
call the LLM. The message must contain an explicit feature cue that is not represented fully
in the Tier 1 entities.
"""
import re
from app.services.intent import normalize

# Compound shades: Tier 1 may capture the base colour ("blue") but miss its qualifier ("sky").
_COMPOUND_COLOUR = re.compile(
    r"\b(?:sky|navy|royal|baby|powder|light|dark|pastel|wine|bottle|olive|mustard|rust|teal|turquoise|magenta|coral|off[- ]white|two[- ]tone|midnight|ice|electric|steel|smoky|dusty)\s+"
    r"(?:blue|green|pink|purple|red|yellow|grey|gray|brown|white)\b",
    re.I,
)
# Explicit print/style vocabulary; values need not all be in the Tier 1 dictionary.
_STYLE_CUE = re.compile(
    r"\b(?:print(?:ed|ing)?|tie[- ]?dye|batik|boho|abstract|paisley|ikat|block[- ]print|digital[- ]print|ombre|ombr[eé]|gradient|animal[- ]print|leopard|zebra|camouflage|crochet|ruffle|pleated|smocked|cutwork|mirror[- ]work)\b",
    re.I,
)
_FEATURE_KEYS = {"PRODUCT", "CATEGORY", "BRAND", "COLOR", "SIZE", "PRICE", "MIN_PRICE", "MAX_PRICE", "PATTERN", "LOCATION", "QUANTITY", "occasion"}


def find_explicit_feature_gaps(text: str, entities: dict | None) -> list[str]:
    """Return entity types whose explicitly stated detail is missing or only partly captured."""
    text_n = normalize(text)
    entities = entities or {}
    gaps: list[str] = []

    compound_colour = _COMPOUND_COLOUR.search(text_n)
    if compound_colour:
        phrase = re.sub(r"\s+", " ", compound_colour.group(0).lower()).strip()
        current = str(entities.get("COLOR", "")).lower().strip()
        # "blue" is a partial capture of "sky blue"; call Tier 2 to recover the full shade.
        if phrase != current and (not current or current in phrase):
            gaps.append("COLOR")

    style_cue = _STYLE_CUE.search(text_n)
    current_pattern = str(entities.get("PATTERN", "")).lower().strip()
    if style_cue and not current_pattern:
        # A style cue such as "paisley design" is explicit, even when the local pattern
        # dictionary does not know the actual style name.
        gaps.append("PATTERN")
    elif style_cue and current_pattern:
        # Tier 1 may have captured only a generic word such as "printed" while missing
        # the more specific style phrase (e.g. "paisley printed").
        phrase = text_n[max(0, style_cue.start() - 30):min(len(text_n), style_cue.end() + 30)]
        if any(term in phrase for term in ("paisley", "boho", "ikat", "batik", "tie dye", "tie-dye", "animal print", "leopard", "zebra", "block print", "digital print", "abstract", "camouflage", "crochet", "ruffle", "pleated", "smocked", "cutwork", "mirror work")):
            if not any(term in current_pattern for term in ("paisley", "boho", "ikat", "batik", "tie dye", "tie-dye", "animal print", "leopard", "zebra", "block print", "digital print", "abstract", "camouflage", "crochet", "ruffle", "pleated", "smocked", "cutwork", "mirror work")):
                gaps.append("PATTERN")

    # Do not call for a null field alone. Only explicit feature cues above trigger this gate.
    return list(dict.fromkeys(key for key in gaps if key in _FEATURE_KEYS))


def merge_missing_entities(text: str, tier1_entities: dict | None, tier2_entities: dict | None, allowed_keys: list[str] | None = None) -> dict:
    """Merge only explicit, grounded Tier 2 features; preserve Tier 1 values except partial values."""
    merged = dict(tier1_entities or {})
    source = tier2_entities or {}
    allowed = set(allowed_keys or _FEATURE_KEYS)
    text_n = normalize(text)
    for key, value in source.items():
        if key not in allowed or value is None or value == "":
            continue
        value_text = normalize(str(value))
        # Feature-only enrichment must be grounded in the customer's words. Numeric values
        # may be formatted differently (e.g. 1,500 vs 1500), so compare digit sequences too.
        grounded = bool(value_text and value_text in text_n)
        if not grounded and key in {"PRICE", "MIN_PRICE", "MAX_PRICE", "QUANTITY"}:
            digits = re.sub(r"\D", "", str(value))
            grounded = bool(digits and digits in re.sub(r"\D", "", text_n))
        if not grounded:
            continue
        old = merged.get(key)
        if old is None or old == "":
            merged[key] = value
            continue
        old_text = normalize(str(old))
        # Allow a grounded, more-specific phrase to refine a base extraction such as
        # COLOR=blue -> COLOR=sky blue or PATTERN=printed -> PATTERN=paisley printed.
        if key in {"COLOR", "PATTERN"} and old_text in value_text and len(value_text) > len(old_text):
            merged[key] = value
    return merged
