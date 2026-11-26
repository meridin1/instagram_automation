import pytest
from app.services.intent import IntentResult
from app.services.response_service import build_response
from app.services.ai_orchestrator import understand


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        ("[instagram_attachment:image]", "I received your photo"),
        ("[instagram_attachment:audio]", "I received your voice message"),
        ("[instagram_attachment:video]", "I received your video"),
        ("[instagram_attachment:other]", "I received your attachment"),
    ],
)
async def test_attachment_only_dm_gets_safe_reply(marker, expected):
    intent = IntentResult(intent="unknown", confidence=1.0, source="rules", entities={})
    reply, status = await build_response("unused-client", intent, None, marker)
    assert expected in reply
    assert status == "automated"


@pytest.mark.asyncio
async def test_attachment_marker_does_not_call_llm(monkeypatch):
    async def unexpected_call(*args, **kwargs):
        raise AssertionError("LLM should not be called for an internal attachment marker")

    monkeypatch.setattr("app.services.ai_orchestrator.llm_service.classify", unexpected_call)
    result = await understand("[instagram_attachment:image]", None, {}, True, "unused-client")
    assert result.intent == "unknown"
    assert result.source == "rules"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("marker", "source_label"),
    [
        ("[instagram_attachment:post]", "post"),
        ("[instagram_attachment:story_reply]", "story"),
    ],
)
async def test_mapped_post_or_story_attachment_uses_catalogue_facts(marker, source_label):
    intent = IntentResult(intent="unknown", confidence=1.0, source="rules", entities={})
    product = {
        "_id": "product-123",
        "name": "Floral Kurti",
        "price": 1299,
        "sizes": ["S", "M", "L"],
        "colors": ["Pink", "Black"],
    }

    reply, status = await build_response(
        "unused-client",
        intent,
        product,
        marker,
        context={},
    )

    assert status == "automated"
    assert source_label in reply
    assert "Floral Kurti" in reply
    assert "₹1299" in reply
    assert "S, M, L" in reply
    assert "Pink, Black" in reply


@pytest.mark.asyncio
async def test_unmapped_post_attachment_does_not_guess_a_product():
    intent = IntentResult(intent="unknown", confidence=1.0, source="rules", entities={})

    reply, status = await build_response(
        "unused-client",
        intent,
        None,
        "[instagram_attachment:post]",
        context={},
    )

    assert status == "automated"
    assert "product name" in reply
    assert "catalogue" in reply
