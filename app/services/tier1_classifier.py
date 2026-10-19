"""Tier 1: deterministic rules and the existing local TF-IDF classifier."""
from app.services.intent import IntentResult, detect


def classify_tier1(text: str, product: dict | None = None) -> IntentResult:
    return detect(text, product)
