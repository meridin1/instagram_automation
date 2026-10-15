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
