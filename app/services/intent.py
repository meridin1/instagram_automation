from dataclasses import dataclass, field
import re
from pathlib import Path
import joblib
import numpy as np

BASE = Path(__file__).resolve().parents[1] / "ml"
MODEL_PATH = BASE / "ml" / "models" / "intent_model.joblib"
VECTORIZER_PATH = BASE / "ml" / "ml" / "models" / "tfidf_vectorizer.joblib"

# Support both legacy model locations and the locations produced by the training script.
MODEL_CANDIDATES = [
    BASE / "models" / "intent_model.joblib",
    BASE / "models" / "intent_classifier.joblib",
    BASE / "ml" / "models" / "intent_model.joblib",
    BASE / "models" / "intent_model.pkl",
]
VECTORIZER_CANDIDATES = [
    BASE / "models" / "tfidf_vectorizer.joblib",
    BASE / "ml" / "models" / "tfidf_vectorizer.joblib",
    BASE / "models" / "tfidf_vectorizer.pkl",
]


@dataclass
class IntentResult:
    intent: str
    confidence: float
    source: str
    entities: dict = field(default_factory=dict)
    max_price: float | None = None


INTENTS = {
    "greeting", "thanks", "product_price", "product_availability",
    "product_size", "product_color", "product_link", "product_alternatives",
    "product_search", "location_query", "delivery_query", "order_request",
    "return_request", "exchange_request", "human_handoff", "unknown",
}


def normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _find_model(paths):
    for p in paths:
        if p.exists():
            return p
    return None


def _ml_predict(text: str):
    model_path = _find_model(MODEL_CANDIDATES)
    vec_path = _find_model(VECTORIZER_CANDIDATES)
    if not model_path:
        return None
    try:
        model = joblib.load(model_path)
        # The original Phase 2 trainer saves a single sklearn Pipeline.
        if hasattr(model, "predict_proba") and hasattr(model, "classes_") and hasattr(model, "steps"):
            probabilities = model.predict_proba([text])[0]
            idx = int(np.argmax(probabilities))
            label = str(model.classes_[idx])
            return (label if label in INTENTS else None, float(probabilities[idx]))
        if not vec_path:
            return None
        vectorizer = joblib.load(vec_path)
        X = vectorizer.transform([text])
        probabilities = model.predict_proba(X)[0]
        idx = int(np.argmax(probabilities))
        label = str(model.classes_[idx])
        return (label if label in INTENTS else None, float(probabilities[idx]))
    except Exception:
        return None


def _extract_entities(text: str) -> dict:
    lower = normalize(text)
    entities = {}
    colors = ["black", "white", "red", "blue", "green", "pink", "yellow", "brown", "beige", "maroon", "purple", "grey", "gray", "orange"]
    found_colors = [c for c in colors if re.search(rf"\b{re.escape(c)}\b", lower)]
    if found_colors:
        entities["COLOR"] = found_colors[0]

    size_match = re.search(r"\b(3xl|2xl|xxxl|xxl|xl|xs|s|m|l)\b", lower)
    if size_match:
        entities["SIZE"] = size_match.group(1).upper()

    price_patterns = [
        r"(?:under|below|less than|upto|up to|max(?:imum)?|within)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)",
        r"(?:₹|rs\.?|inr)\s*([\d,]+)",
    ]
    for pattern in price_patterns:
        match = re.search(pattern, lower)
        if match:
            entities["PRICE"] = float(match.group(1).replace(",", ""))
            break

    return entities


def _rule_intent(text: str) -> str:
    t = normalize(text)
    # Manglish/Malayalam transliteration and English.
    if re.search(r"\b(hi|hello|hey|hai|hii|halo)\b", t) or t in {"namaskaram", "salam"}:
        return "greeting"
    if any(x in t for x in ["thank you", "thanks", "thankyou", "nanni"]):
        return "thanks"
    if any(x in t for x in ["talk to someone", "human", "agent", "seller", "person", "connect me", "chechiye connect", "chettane connect"]):
        return "human_handoff"
    if any(x in t for x in ["return", "thirich", "return cheyy"]):
        return "return_request"
    if any(x in t for x in ["exchange", "replace", "change cheyy"]):
        return "exchange_request"
    if any(x in t for x in ["order", "buy", "vaangan", "edukkan", "book cheyy"]):
        return "order_request"
    if any(x in t for x in ["location", "where are you", "evideya", "evide aanu", "shop evide"]):
        return "location_query"
    if any(x in t for x in ["delivery", "deliver", "shipping", "courier", "delivery undo", "delivery ethra"]):
        return "delivery_query"
    if any(x in t for x in ["link", "url", "send link", "link ayakk", "link onnu"]):
        return "product_link"
    if any(x in t for x in ["other design", "other designs", "vere design", "vere model", "vere item", "matte design"]):
        return "product_alternatives"
    # If the customer names a colour/size and asks whether it is available,
    # treat the message as an availability question rather than only a colour question.
    has_availability_marker = any(x in t for x in ["available", "stock", " undo", "undo ", "kittumo"])
    has_variant = bool(
        re.search(r"\b(black|white|red|blue|green|pink|yellow|brown|beige|maroon|purple|grey|gray|orange)\b", t)
        or re.search(r"\b(3xl|2xl|xxxl|xxl|xl|xs|s|m|l)\b", t)
    )
    if has_availability_marker and has_variant:
        return "product_availability"
    if any(x in t for x in ["colour", "color", "which colour"]):
        return "product_color"
    if any(x in t for x in ["size", "xl undo", "xxl undo", "large undo", "small undo", "medium undo", "size available"]):
        return "product_size"
    if any(x in t for x in ["available", "stock", "undo", "kittumo", "available ano"]):
        return "product_availability"
    if any(x in t for x in ["price", "how much", "rate", "ethra", "cost", "₹", "rs."]):
        return "product_price"
    if any(x in t for x in ["show me", "looking for", "need something", "suggest", "recommend", "find me", "under ", "below "]):
        return "product_search"
    return "unknown"


def detect(text: str, product: dict | None = None) -> IntentResult:
    normalized = normalize(text)
    entities = _extract_entities(normalized)

    rule = _rule_intent(normalized)
    # Explicit rule patterns take precedence for deterministic business flows.
    if rule != "unknown":
        return IntentResult(
            intent=rule,
            confidence=0.99,
            source="rules",
            entities=entities,
            max_price=entities.get("PRICE"),
        )

    prediction = _ml_predict(normalized)
    if prediction:
        label, confidence = prediction
        return IntentResult(
            intent=label,
            confidence=confidence,
            source="ml",
            entities=entities,
            max_price=entities.get("PRICE"),
        )

    if product:
        product_text = " ".join([product.get("name", ""), product.get("category", ""), product.get("brand", "")]).lower()
        if any(token in normalized for token in product_text.split() if len(token) > 2):
            return IntentResult("product_search", 0.60, "context", entities, entities.get("PRICE"))

    return IntentResult("unknown", 0.0, "unknown", entities, entities.get("PRICE"))
