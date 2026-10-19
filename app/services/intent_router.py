"""Three-tier cascade: local interpretation -> targeted LLM enrichment -> safe fallback."""
from app.services.intent import IntentResult
from app.services.tier1_classifier import classify_tier1
from app.services.tier2_llm_classifier import classify_tier2
from app.services.confidence_policy import tier1_is_accepted, tier2_is_accepted
from app.services.entity_validator import validate_prediction
from app.services.feature_gap import find_explicit_feature_gaps, merge_missing_entities


async def route_intent(text: str, product: dict | None, context: dict | None, llm_enabled: bool, client_id: str | None = None) -> IntentResult:
    # Media placeholders cannot be interpreted as ordinary text; preserve safe context handling.
    if text.startswith("[instagram_attachment:"):
        return IntentResult(intent="unknown", confidence=1.0, source="rules", entities={})

    local = classify_tier1(text, product)
    local_valid = validate_prediction(local.intent, local.entities)
    if local_valid:
        local.intent, local.entities = local_valid
    accepted_local = tier1_is_accepted(local.intent, local.confidence)

    # Tier 1 is sufficient unless intent is unresolved OR an explicitly mentioned feature was
    # detected only partially/missed. A merely-null field (e.g. no size mentioned) never triggers LLM.
    feature_gaps = find_explicit_feature_gaps(text, local.entities) if accepted_local else []
    if accepted_local and not feature_gaps:
        return local
    if not llm_enabled:
        return local

    # Unknown/low-confidence intent: one full Tier 2 interpretation call.
    # Resolved intent + explicit feature gap: the same structured call is used as a feature extractor,
    # but the Tier 1 primary intent is retained and only grounded, missing/partial features are merged.
    result = await classify_tier2(text, context, client_id=client_id)
    if not result:
        return local

    validated = validate_prediction(result.get("intent", "unknown"), result.get("entities", {}))
    if not validated:
        return local if accepted_local else IntentResult(intent="unknown", confidence=0.0, source="tier2_invalid", entities={})
    tier2_intent, tier2_entities = validated

    if accepted_local:
        merged = merge_missing_entities(text, local.entities, tier2_entities, allowed_keys=feature_gaps)
        # If the model did not return any grounded feature that was missed, do not change the
        # accepted local intent or manufacture an intent uncertainty.
        local.entities = merged
        local.max_price = merged.get("MAX_PRICE", merged.get("PRICE", local.max_price))
        local.source = "tier1+tier2_features" if any(merged.get(k) != (local_valid[1].get(k) if local_valid else None) for k in feature_gaps) else local.source
        return local

    confidence = float(result.get("confidence", 0.0))
    clarification = bool(result.get("clarification_required", False))
    accepted = tier2_is_accepted(tier2_intent, confidence, clarification)
    if not accepted:
        # Preserve useful, explicitly grounded entities for a clarification, but do not execute a guess.
        grounded = merge_missing_entities(text, {}, tier2_entities)
        return IntentResult(
            intent="unknown", confidence=confidence, source="tier2_low_confidence", entities=grounded,
            secondary_intents=result.get("secondary_intents", []),
            needs_context=bool(result.get("needs_context", False)), clarification_required=True,
        )
    return IntentResult(
        intent=tier2_intent, confidence=confidence, source="tier2_llm", entities=tier2_entities,
        max_price=tier2_entities.get("MAX_PRICE", tier2_entities.get("PRICE")),
        secondary_intents=result.get("secondary_intents", []),
        needs_context=bool(result.get("needs_context", False)), clarification_required=clarification,
    )
