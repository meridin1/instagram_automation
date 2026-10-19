import pytest
from app.services.intent import detect, INTENTS, IntentResult
from app.services.llm_service import LLMService
from app.services.feature_gap import find_explicit_feature_gaps, merge_missing_entities
from app.services import intent_router


def test_shared_taxonomy_contains_required_faq_and_commerce_intents():
    required = {
        "product_availability", "product_inquiry", "product_price", "product_details",
        "product_alternatives", "product_size", "product_color", "product_link",
        "business_hours_query", "order_status", "cancel_order", "complaint",
        "discount_inquiry", "payment_query", "delivery_issue", "return_policy_query",
        "exchange_policy_query", "product_comparison", "media_product_identification", "unknown",
    }
    assert required.issubset(INTENTS)


def test_compound_manglish_availability_message():
    result = detect("hi blue ombre printed type kurti ningal vilkkunnundo?")
    assert result.intent == "product_availability"
    assert result.entities["COLOR"] == "blue"
    assert result.entities["CATEGORY"] == "kurti"
    assert result.entities["PATTERN"] == "ombre printed"
    assert "greeting" in result.secondary_intents


def test_working_hours_faq_routes_deterministically():
    assert detect("What are your working hours?").intent == "business_hours_query"
    assert detect("shop timing entha?").intent == "business_hours_query"


def test_order_late_is_delivery_issue_not_order_placement():
    assert detect("my order is late, where is it?").intent == "delivery_issue"


def test_llm_validation_supports_secondary_intents_and_new_entities():
    result = LLMService._validate({
        "intent": "product_availability", "secondary_intents": ["greeting"],
        "entities": {"CATEGORY": "kurti", "COLOR": "blue", "MAX_PRICE": 1500, "PATTERN": "ombre printed"},
        "language": "Manglish", "confidence": 0.91,
        "needs_context": False, "clarification_required": False,
    })
    assert result is not None
    assert result["intent"] == "product_availability"
    assert result["secondary_intents"] == ["greeting"]
    assert result["entities"]["MAX_PRICE"] == 1500.0


def test_feature_gap_only_when_explicit_phrase_is_partly_missed():
    assert "COLOR" in find_explicit_feature_gaps("sky blue kurti undo", {"COLOR": "blue", "CATEGORY": "kurti"})
    assert "PATTERN" in find_explicit_feature_gaps("paisley printed kurti undo", {"PATTERN": "printed"})
    assert find_explicit_feature_gaps("do you have this in XL?", {"SIZE": "XL"}) == []
    assert find_explicit_feature_gaps("kurti undo", {"CATEGORY": "kurti"}) == []


def test_feature_merge_preserves_tier1_and_requires_grounding():
    merged = merge_missing_entities(
        "sky blue paisley printed kurti", {"COLOR": "blue", "CATEGORY": "kurti", "PATTERN": "printed"},
        {"COLOR": "sky blue", "CATEGORY": "dress", "PATTERN": "paisley printed", "BRAND": "not mentioned"},
        allowed_keys=["COLOR", "PATTERN", "CATEGORY", "BRAND"],
    )
    assert merged["COLOR"] == "sky blue"
    assert merged["CATEGORY"] == "kurti"
    assert merged["PATTERN"] == "paisley printed"
    assert "BRAND" not in merged


@pytest.mark.asyncio
async def test_resolved_intent_calls_tier2_only_for_explicit_feature_gap(monkeypatch):
    calls = []
    async def fake_tier2(text, context, client_id=None):
        calls.append(text)
        return {"intent": "product_search", "entities": {"COLOR": "sky blue", "CATEGORY": "dress"}, "confidence": 0.99, "secondary_intents": [], "needs_context": False, "clarification_required": False}
    monkeypatch.setattr(intent_router, "classify_tier1", lambda text, product: IntentResult("product_availability", .99, "rules", {"COLOR": "blue", "CATEGORY": "kurti"}))
    monkeypatch.setattr(intent_router, "classify_tier2", fake_tier2)
    result = await intent_router.route_intent("sky blue kurti undo", None, {}, True, "client")
    assert calls == ["sky blue kurti undo"]
    assert result.intent == "product_availability"  # Tier 2 cannot replace a resolved Tier 1 intent.
    assert result.entities["COLOR"] == "sky blue"
    assert result.entities["CATEGORY"] == "kurti"  # Reliable Tier 1 value is preserved.


@pytest.mark.asyncio
async def test_resolved_intent_does_not_call_tier2_for_unmentioned_fields(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("Tier 2 should not run for absent optional features")
    monkeypatch.setattr(intent_router, "classify_tier1", lambda text, product: IntentResult("product_search", .99, "rules", {"CATEGORY": "kurti"}))
    monkeypatch.setattr(intent_router, "classify_tier2", fail_if_called)
    result = await intent_router.route_intent("show kurti", None, {}, True, "client")
    assert result.intent == "product_search"
    assert result.entities["CATEGORY"] == "kurti"


@pytest.mark.asyncio
async def test_unresolved_intent_uses_tier2_full_interpretation(monkeypatch):
    async def fake_tier2(text, context, client_id=None):
        return {"intent": "product_availability", "entities": {"CATEGORY": "kurti"}, "confidence": .95, "secondary_intents": [], "needs_context": False, "clarification_required": False}
    monkeypatch.setattr(intent_router, "classify_tier1", lambda text, product: IntentResult("unknown", 0, "unknown", {}))
    monkeypatch.setattr(intent_router, "classify_tier2", fake_tier2)
    result = await intent_router.route_intent("ningalk ith undo", None, {}, True, "client")
    assert result.intent == "product_availability"
    assert result.source == "tier2_llm"

