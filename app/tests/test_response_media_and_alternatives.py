import pytest

from app.services.intent import IntentResult, detect
from app.services import response_service
from app.services.conversation_service import _should_send_product_image


@pytest.mark.parametrize("message", ["Hi", "Ningal jeans vilkkunundo", "Price thraya?", "Vere design undo"])
def test_customer_examples_have_expected_intents(message):
    result = detect(message)
    expected = {
        "Hi": "greeting",
        "Ningal jeans vilkkunundo": "product_availability",
        "Price thraya?": "product_price",
        "Vere design undo": "product_alternatives",
    }
    assert result.intent == expected[message]


def test_product_image_is_not_sent_for_greeting_price_or_availability():
    product = {"image_url": "https://cdn.example/jeans.jpg"}
    for intent_name in ("greeting", "product_price", "product_availability", "product_alternatives"):
        intent = IntentResult(intent=intent_name, confidence=0.99, source="rules")
        assert not _should_send_product_image(intent, "Any reply", product)


def test_product_image_is_sent_only_after_explicit_photo_request():
    product = {"image_url": "https://cdn.example/jeans.jpg"}
    intent = IntentResult(intent="media_product_identification", confidence=0.99, source="rules")
    assert _should_send_product_image(intent, "Sure 😊 I'll send you the photo now.", product)
    assert not _should_send_product_image(intent, "I don't have an image listed.", product)


@pytest.mark.asyncio
async def test_alternative_search_infers_category_from_product_name(monkeypatch):
    async def fake_business_settings(_client_id):
        return {}

    async def fake_automation_settings(_client_id):
        return {"human_handoff_on_unknown": True}

    calls = []
    async def fake_search(client_id, query, entities=None, limit=5, exclude_product_id=None, offset=0):
        calls.append((query, exclude_product_id))
        if "jeans" in query.casefold():
            return [{"_id": "other-jeans", "name": "Black Straight Fit Jeans", "price": 1800}]
        return []

    monkeypatch.setattr(response_service, "business_settings", fake_business_settings)
    monkeypatch.setattr(response_service, "automation_settings", fake_automation_settings)
    monkeypatch.setattr(response_service, "search_products", fake_search)

    current = {"_id": "current-jeans", "name": "Unisex Washed Grey Ultra-Wide Leg Baggy Jeans", "image_url": "https://cdn.example/current.jpg"}
    intent = IntentResult(intent="product_alternatives", confidence=0.99, source="rules", entities={})
    reply, status = await response_service.build_response(
        "tenant-1", intent, current, "Vere design undo", context={"product_id": "current-jeans"}
    )

    assert status == "automated"
    assert "Black Straight Fit Jeans" in reply
    assert all(excluded == "current-jeans" for _, excluded in calls)
    assert any(query == "jeans" for query, _ in calls)
