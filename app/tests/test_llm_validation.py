import pytest
from app.services.llm_service import LLMService


def test_llm_validation_rejects_unknown_intent():
    assert LLMService._validate({"intent": "make_magic", "entities": {}}) is None


def test_llm_validation_accepts_structured_result():
    result = LLMService._validate({
        "intent": "product_search",
        "entities": {"CATEGORY": "kurti", "PRICE": 1500},
        "language": "Manglish",
        "confidence": 0.91,
    })
    assert result["intent"] == "product_search"
    assert result["entities"]["CATEGORY"] == "kurti"
