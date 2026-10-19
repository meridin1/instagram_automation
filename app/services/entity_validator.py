"""Validation and normalization shared by local and LLM predictions."""
from app.services.intent import canonical_intent

ALLOWED_ENTITY_KEYS = {
    "PRODUCT", "CATEGORY", "BRAND", "COLOR", "SIZE", "PRICE", "MIN_PRICE",
    "MAX_PRICE", "PATTERN", "ORDER_ID", "LOCATION", "QUANTITY", "occasion",
}


def validate_prediction(intent: str, entities: dict | None) -> tuple[str, dict] | None:
    if not isinstance(entities or {}, dict):
        return None
    canonical = canonical_intent(intent)
    if canonical == "unknown" and str(intent).strip().lower() != "unknown":
        return None
    cleaned = {}
    for key, value in (entities or {}).items():
        if key not in ALLOWED_ENTITY_KEYS or value is None or value == "":
            continue
        if key in {"PRICE", "MIN_PRICE", "MAX_PRICE"}:
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value < 0 or value > 100000000:
                continue
        elif key == "QUANTITY":
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
            if value < 1 or value > 10000:
                continue
        elif isinstance(value, str):
            value = value.strip()[:160]
            if not value:
                continue
        cleaned[key] = value
    if "MAX_PRICE" in cleaned and "PRICE" not in cleaned:
        cleaned["PRICE"] = cleaned["MAX_PRICE"]
    return canonical, cleaned
