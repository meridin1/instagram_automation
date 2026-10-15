from app.services.intent import IntentResult, detect
from app.services.llm_service import llm_service
from app.core.config import settings


async def understand(text: str, product: dict | None, context: dict | None, llm_enabled: bool, client_id: str | None = None) -> IntentResult:
    # Attachment-only DMs use explicit safe responses in response_service. Do not
    # waste an LLM call trying to interpret our internal attachment marker.
    if text.startswith("[instagram_attachment:"):
        return IntentResult(intent="unknown", confidence=1.0, source="rules", entities={})

    local = detect(text, product)
    if local.intent != "unknown" and local.confidence >= 0.55:
        return local

    if not llm_enabled:
        return local

    llm = await llm_service.classify(text, context, client_id=client_id)
    if not llm:
        return local

    entities = dict(llm["entities"])
    if llm.get("tool") and llm["tool"] != "none":
        entities["_tool"] = llm["tool"]
        entities["_tool_args"] = llm.get("tool_args", {})

    return IntentResult(
        intent=llm["intent"],
        confidence=llm["confidence"],
        source="llm",
        entities=entities,
        max_price=entities.get("PRICE"),
    )
