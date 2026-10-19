"""Backward-compatible entry point for the three-tier intent pipeline."""
from app.services.intent_router import route_intent
# Kept imported for backwards-compatible monkeypatching in existing tests/integrations.
from app.services.llm_service import llm_service


async def understand(text: str, product: dict | None, context: dict | None, llm_enabled: bool, client_id: str | None = None):
    return await route_intent(text, product, context, llm_enabled, client_id=client_id)
