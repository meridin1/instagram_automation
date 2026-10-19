"""Hybrid entity extraction for Meridin Phase 3.

Rules handle commerce-critical values (size, colour, price). A lightweight
BIO token classifier handles learned CATEGORY/BRAND/PRODUCT patterns. Dynamic
product names are additionally matched against the tenant's catalog.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "entity_models" / "entity_tagger.joblib"
VECTORIZER_PATH = BASE_DIR / "entity_models" / "entity_vectorizer.joblib"

COLORS = {
    "black", "white", "red", "blue", "green", "pink", "yellow", "brown",
    "maroon", "beige", "purple", "orange", "grey", "gray", "cream", "peach",
    "navy", "wine", "mustard", "magenta", "lavender", "teal", "olive", "rust",
}
SIZES = ("XXXL", "3XL", "XXL", "2XL", "XL", "XS", "S", "M", "L")
TOKEN_RE = re.compile(r"₹\s*[\d,]+|\b(?:rs\.?|inr)\s*[\d,]+|[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*|\d+(?:\.\d+)?")


def tokenize(text: str):
    return [(m.group(0), m.start(), m.end()) for m in TOKEN_RE.finditer(text or "")]


def _price_value(text: str) -> float | None:
    m = re.search(r"(?:under|below|less than|upto|up to)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)", text.lower())
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _add(entities, typ, value, source, confidence=1.0, start=None, end=None):
    key = (typ, str(value).strip().lower())
    if any((e["type"], str(e["value"]).strip().lower()) == key for e in entities):
        return
    item = {"type": typ, "value": value, "source": source, "confidence": round(float(confidence), 4)}
    if start is not None:
        item["start"] = start
        item["end"] = end
    entities.append(item)


def _rule_entities(text: str, entities: list[dict]):
    lower = text.lower()
    for color in sorted(COLORS, key=len, reverse=True):
        m = re.search(rf"\b{re.escape(color)}\b", lower)
        if m:
            _add(entities, "COLOR", color, "rule", 1.0, m.start(), m.end())
            break

    for size in SIZES:
        m = re.search(rf"\b{re.escape(size.lower())}\b", lower)
        if m:
            _add(entities, "SIZE", size.upper(), "rule", 1.0, m.start(), m.end())
            break

    value = _price_value(text)
    if value is not None:
        m = re.search(r"(?:under|below|less than|upto|up to)\s*(?:₹|rs\.?|inr)?\s*[\d,]+", lower)
        _add(entities, "PRICE", value, "rule", 1.0, m.start() if m else None, m.end() if m else None)


def _catalog_entities(text: str, product: dict | None, entities: list[dict]):
    if not product:
        return
    lower = text.lower()
    for field, typ in (("name", "PRODUCT"), ("category", "CATEGORY"), ("brand", "BRAND")):
        value = product.get(field)
        if not value:
            continue
        value = str(value).strip()
        if value and value.lower() in lower:
            start = lower.index(value.lower())
            _add(entities, typ, value, "catalog", 1.0, start, start + len(value))


@lru_cache(maxsize=1)
def _load_entity_models():
    if not MODEL_PATH.exists() or not VECTORIZER_PATH.exists():
        return None, None
    try:
        return joblib.load(MODEL_PATH), joblib.load(VECTORIZER_PATH)
    except Exception:
        return None, None


def _ml_entities(text: str, entities: list[dict]):
    model, vectorizer = _load_entity_models()
    if model is None or vectorizer is None:
        return

    toks = tokenize(text)
    if not toks:
        return
    features = [_token_features(toks, i) for i in range(len(toks))]
    X = vectorizer.transform(features)
    labels = model.predict(X)
    probabilities = model.predict_proba(X) if hasattr(model, "predict_proba") else None

    current_type = None
    current_start = None
    current_end = None
    current_tokens = []
    current_conf = []

    def flush():
        nonlocal current_type, current_start, current_end, current_tokens, current_conf
        if current_type:
            value = " ".join(current_tokens)
            _add(entities, current_type, value, "ml", sum(current_conf) / len(current_conf), current_start, current_end)
        current_type = None
        current_start = None
        current_end = None
        current_tokens = []
        current_conf = []

    for i, (tok, start, end) in enumerate(toks):
        label = str(labels[i])
        conf = float(max(probabilities[i])) if probabilities is not None else 0.75
        if label == "O":
            flush()
            continue
        prefix, _, typ = label.partition("-")
        if prefix == "B" or current_type != typ:
            flush()
            current_type = typ
            current_start = start
        current_end = end
        current_tokens.append(tok)
        current_conf.append(conf)
    flush()


def _token_features(tokens, i):
    word, _, _ = tokens[i]
    lower = word.lower()
    prev = tokens[i - 1][0].lower() if i else "<START>"
    nxt = tokens[i + 1][0].lower() if i + 1 < len(tokens) else "<END>"
    return {
        "word": lower,
        "word_upper": word.isupper(),
        "word_title": word.istitle(),
        "word_digit": word.isdigit(),
        "prefix1": lower[:1],
        "prefix2": lower[:2],
        "prefix3": lower[:3],
        "suffix1": lower[-1:],
        "suffix2": lower[-2:],
        "suffix3": lower[-3:],
        "prev": prev,
        "next": nxt,
        "prev2": tokens[i - 2][0].lower() if i > 1 else "<START2>",
        "next2": tokens[i + 2][0].lower() if i + 2 < len(tokens) else "<END2>",
    }


def extract_entities(text: str, product: dict | None = None) -> dict[str, Any]:
    entities: list[dict] = []
    _rule_entities(text or "", entities)
    _catalog_entities(text or "", product, entities)
    _ml_entities(text or "", entities)

    # Prefer deterministic commerce entities over learned duplicates.
    priority = {"rule": 3, "catalog": 2, "ml": 1}
    final = []
    for entity in sorted(entities, key=lambda e: (e.get("start", 10**9), -priority.get(e["source"], 0))):
        duplicate = False
        for existing in final:
            if existing["type"] == entity["type"] and str(existing["value"]).lower() == str(entity["value"]).lower():
                duplicate = True
                break
        if not duplicate:
            final.append(entity)

    by_type = {}
    for e in final:
        by_type.setdefault(e["type"], []).append(e["value"])

    size = next((e["value"] for e in final if e["type"] == "SIZE"), None)
    color = next((e["value"] for e in final if e["type"] == "COLOR"), None)
    price = next((e["value"] for e in final if e["type"] == "PRICE"), None)
    return {"entities": final, "by_type": by_type, "size": size, "color": color, "max_price": price}
