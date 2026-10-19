"""Tier 2 adapter for an OpenAI-compatible hosted instruction/fine-tuned model."""
from app.services.llm_service import llm_service


async def classify_tier2(text: str, context: dict | None = None, client_id: str | None = None):
    return await llm_service.classify(text, context, client_id=client_id)
