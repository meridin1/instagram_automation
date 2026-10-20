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
    secondary_intents: list[str] = field(default_factory=list)
    needs_context: bool = False
    clarification_required: bool = False


# Shared taxonomy used by Tier 1, Tier 2, analytics, and response routing.
INTENTS = {
    "greeting", "thanks", "goodbye", "product_search", "product_availability",
    "product_inquiry", "product_price", "product_details", "product_alternatives",
    "product_size", "product_color", "product_link", "location_query", "delivery_query",
    "delivery_time_query", "business_hours_query", "order_status", "order_request",
    "cancel_order", "return_request", "exchange_request", "complaint", "human_handoff",
    "discount_inquiry", "payment_query", "delivery_issue", "return_policy_query",
    "exchange_policy_query", "product_comparison", "media_product_identification", "unknown",
}

# Backward-compatible names used by earlier training runs / integrations.
INTENT_ALIASES = {
    "size_availability": "product_size",
    "color_availability": "product_color",
    "order_link_request": "product_link",
    "human_handover_request": "human_handoff",
    "order_placement": "order_request",
    "product_inquiry_query": "product_inquiry",
}


def canonical_intent(label: str) -> str:
    label = str(label or "unknown").strip().lower()
    label = INTENT_ALIASES.get(label, label)
    return label if label in INTENTS else "unknown"


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
            return (canonical_intent(label), float(probabilities[idx]))
        if not vec_path:
            return None
        vectorizer = joblib.load(vec_path)
        X = vectorizer.transform([text])
        probabilities = model.predict_proba(X)[0]
        idx = int(np.argmax(probabilities))
        label = str(model.classes_[idx])
        return (canonical_intent(label), float(probabilities[idx]))
    except Exception:
        return None


def _extract_entities(text: str, product: dict | None = None) -> dict:
    lower = normalize(text)
    entities = {}
    colors = ["black", "white", "red", "blue", "green", "pink", "yellow", "brown", "beige", "maroon", "purple", "grey", "gray", "orange", "navy", "cream", "lavender", "peach"]
    found_colors = [c for c in colors if re.search(rf"\b{re.escape(c)}\b", lower)]
    if found_colors:
        entities["COLOR"] = found_colors[0]
    categories = ["kurti", "dress", "saree", "sari", "top", "shirt", "tshirt", "t-shirt", "jeans", "pants", "trousers", "leggings", "palazzo", "dupatta", "abaya", "gown", "skirt", "set", "co-ord", "co ord"]
    found_categories = [c for c in categories if re.search(rf"\b{re.escape(c)}\b", lower)]
    if found_categories:
        entities["CATEGORY"] = found_categories[0]

    size_match = re.search(r"\b(5xl|4xl|3xl|2xl|xxxl|xxl|xl|xs|s|m|l)\b", lower)
    if size_match:
        entities["SIZE"] = size_match.group(1).upper()

    price_patterns = [
        ("MAX_PRICE", r"(?:under|below|less than|upto|up to|max(?:imum)?|within)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)"),
        ("MIN_PRICE", r"(?:above|over|more than|at least)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)"),
        ("PRICE", r"(?:₹|rs\.?|inr)\s*([\d,]+)"),
    ]
    for key, pattern in price_patterns:
        match = re.search(pattern, lower)
        if match:
            entities[key] = float(match.group(1).replace(",", ""))
            if key == "MAX_PRICE":
                entities["PRICE"] = entities[key]
            break
    if "PRICE" not in entities and "MAX_PRICE" not in entities:
        # Avoid interpreting arbitrary numbers as prices unless price language is present.
        match = re.search(r"(?:price|cost|rate|ethra)\D{0,12}([\d,]{2,})", lower)
        if match:
            entities["PRICE"] = float(match.group(1).replace(",", ""))

    pattern_match = re.search(r"\b(ombre(?:[- ]printed)?|printed|floral|striped|plain|embroidered|checked|checkered|solid|embroidered|geometric|polka[- ]dot)\b", lower)
    if pattern_match:
        entities["PATTERN"] = pattern_match.group(1).replace("-", " ")

    quantity_match = re.search(r"\b(?:qty|quantity|take|need|want)\s*(?:of\s*)?(\d{1,2})\b", lower)
    if quantity_match:
        entities["QUANTITY"] = int(quantity_match.group(1))
    order_match = re.search(r"\b(?:order\s*(?:id|number|no\.?|#)\s*[:#-]?\s*)([a-z0-9-]{4,})\b|\border\s*#\s*([a-z0-9-]{4,})\b", lower)
    if order_match:
        entities["ORDER_ID"] = next((g for g in order_match.groups() if g), "")

    # Reuse the Phase 3 BIO entity model for PRODUCT/CATEGORY/BRAND extraction.
    # Rule-derived commerce values above remain authoritative.
    try:
        from app.ml.entity_extractor import extract_entities
        extracted = extract_entities(text, product)
        for key, values in (extracted.get("by_type") or {}).items():
            if not values:
                continue
            mapped_key = str(key).upper()
            if mapped_key in {"PRODUCT", "CATEGORY", "BRAND", "OCCASION"} and mapped_key not in entities:
                entities[mapped_key] = values[0]
    except Exception:
        # Entity model is an enhancement; regex extraction remains available if absent.
        pass
    return entities


def _rule_intent(text: str) -> str:
    t = normalize(text)
    # Human request and high-priority safety/support intents first.
    if any(x in t for x in ["talk to someone", "talk to a human", "human", "agent", "seller", "person", "connect me", "chechiye connect", "chettane connect", "real person"]):
        return "human_handoff"
    if any(x in t for x in ["wrong item", "wrong product", "damaged", "defective", "not what i ordered", "bad quality", "complaint", "refund not received"]):
        return "complaint"
    if any(x in t for x in ["delivery late", "order is late", "my order is late", "order late", "not received", "not delivered", "parcel missing", "courier issue", "delivery problem", "delivery delay", "hasn't arrived", "has not arrived", "package is late"]):
        return "delivery_issue"
    if any(x in t for x in ["cancel order", "cancel my order", "order cancel", "cancel cheyy"]):
        return "cancel_order"
    if any(x in t for x in ["where is my order", "order status", "track my order", "tracking", "order evide", "parcel evide"]):
        return "order_status"
    if re.fullmatch(r"(?:hi|hello|hey|hai|hii|halo|hlo|good morning|good evening|good afternoon|namaskaram|salam)[!.\s😊🙂]*", t):
        return "greeting"
    if any(x in t for x in ["thank you", "thanks", "thankyou", "nanni", "thx"]):
        return "thanks"
    if re.search(r"\b(bye|goodbye|see you|pinne kanam)\b", t):
        return "goodbye"
    if any(x in t for x in ["return policy", "return cheyyan pattumo", "can i return", "return this", "return rules"]):
        return "return_policy_query"
    if any(x in t for x in ["exchange policy", "exchange rules", "can i exchange", "exchange this"]):
        return "exchange_policy_query"
    if any(x in t for x in ["return", "thirich", "return cheyy"]):
        return "return_request"
    if any(x in t for x in ["exchange", "replace", "change cheyy"]):
        return "exchange_request"
    if any(x in t for x in ["discount", "offer", "less price", "bulk price", "wholesale rate", "bargain"]):
        return "discount_inquiry"
    if any(x in t for x in ["payment", "pay online", "cash on delivery", "cod", "upi", "payment method", "how can i pay"]):
        return "payment_query"
    if any(x in t for x in ["compare", "difference between", "which is better", "compare these"]):
        return "product_comparison"
    if any(x in t for x in ["what material", "which fabric", "fabric type", "cotton or", "is this cotton", "details of this", "product details"]):
        return "product_details"
    if any(x in t for x in ["working hours", "business hours", "opening hours", "opening time", "closing time", "what time do you open", "what time do you close", "when do you open", "when do you close", "when are you open", "when are you closed", "are you open today", "shop timing", "store timing", "shop time", "shop timings", "store hours", "open time", "close time"]):
        return "business_hours_query"
    if any(x in t for x in ["location", "where are you", "evideya", "evide aanu", "shop evide", "address"]):
        return "location_query"
    if any(x in t for x in ["how many days", "delivery time", "when will it arrive", "when will i receive", "how long for delivery", "ethra days"]):
        return "delivery_time_query"
    if any(x in t for x in ["delivery", "deliver", "shipping", "courier", "delivery undo", "delivery ethra"]):
        return "delivery_query"
    if any(x in t for x in ["other design", "other designs", "vere design", "vere model", "vere item", "matte design", "similar products", "another option"]):
        return "product_alternatives"
    if any(x in t for x in ["link", "url", "send link", "link ayakk", "link onnu"]):
        return "product_link"
    if any(x in t for x in ["place an order", "place order", "i want to order", "i want to buy", "want to buy", "buy this", "order this", "how do i order", "how to order", "vaangan", "edukkan", "book cheyy"]):
        return "order_request"
    has_availability_marker = any(x in t for x in ["available", "stock", " undo", "undo ", "kittumo", "vilkkunnundo", "sell cheyyarundo"])
    has_variant = bool(re.search(r"\b(black|white|red|blue|green|pink|yellow|brown|beige|maroon|purple|grey|gray|orange|navy|cream|lavender|peach)\b", t) or re.search(r"\b(5xl|4xl|3xl|2xl|xxxl|xxl|xl|xs|s|m|l)\b", t))
    if has_availability_marker and has_variant:
        return "product_availability"
    if any(x in t for x in ["available", "stock", "undo", "kittumo", "available ano", "vilkkunnundo", "sell cheyyarundo"]):
        return "product_availability"
    if any(x in t for x in ["price", "how much", "rate", "ethra", "cost", "₹", "rs."]):
        return "product_price"
    if any(x in t for x in ["colour", "color", "which colour", "which color", "available colours", "available colors"]):
        return "product_color"
    if any(x in t for x in ["size", "xl undo", "xxl undo", "large undo", "small undo", "medium undo", "size available"]):
        return "product_size"
    if any(x in t for x in ["show me", "looking for", "need something", "suggest", "recommend", "find me", "under ", "below "]):
        return "product_search"
    # Product-image-only marker is handled explicitly by response service.
    if "photo" in t or "picture" in t or "image" in t:
        return "media_product_identification"
    if re.search(r"\b(is this|this one|this product|ee item|ee dress|ee kurti)\b", t):
        return "product_inquiry"
    return "unknown"


def detect(text: str, product: dict | None = None) -> IntentResult:
    normalized = normalize(text)
    entities = _extract_entities(normalized, product)

    rule = _rule_intent(normalized)
    # Explicit rule patterns take precedence for deterministic business flows.
    if rule != "unknown":
        secondary = []
        if re.match(r"^(hi|hello|hey|hai|hii|halo|hlo)\b", normalized) and rule != "greeting":
            secondary.append("greeting")
        if rule == "product_availability" and any(x in normalized for x in ["price", "how much", "rate", "ethra", "cost", "₹", "rs."]):
            secondary.append("product_price")
        return IntentResult(
            intent=rule,
            confidence=0.99,
            source="rules",
            entities=entities,
            max_price=entities.get("MAX_PRICE", entities.get("PRICE")),
            secondary_intents=secondary,
        )

    prediction = _ml_predict(normalized)
    if prediction:
        label, confidence = prediction
        return IntentResult(
            intent=canonical_intent(label),
            confidence=confidence,
            source="ml",
            entities=entities,
            max_price=entities.get("PRICE"),
        )

    if product:
        product_text = " ".join([product.get("name", ""), product.get("category", ""), product.get("subcategory", ""), product.get("product_type", ""), product.get("department", ""), product.get("brand", "")]).lower()
        if any(token in normalized for token in product_text.split() if len(token) > 2):
            return IntentResult("product_search", 0.60, "context", entities, entities.get("PRICE"))

    return IntentResult("unknown", 0.0, "unknown", entities, entities.get("PRICE"))
