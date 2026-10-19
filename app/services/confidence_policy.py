"""Conservative tier routing policy; thresholds are configurable and must be calibrated."""
from app.core.config import settings


def tier1_is_accepted(intent, confidence: float) -> bool:
    return intent != "unknown" and confidence >= settings.tier1_confidence_threshold


def tier2_is_accepted(intent, confidence: float, clarification_required: bool = False) -> bool:
    return intent != "unknown" and confidence >= settings.tier2_confidence_threshold and not clarification_required
