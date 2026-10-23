from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from bson import ObjectId
from pydantic import BaseModel
from app.core.security import get_client_id
from app.database.mongo import db
from app.services.usage_service import get_client_usage

router = APIRouter(prefix="/api/ai", tags=["AI quality and usage"])

@router.get("/analytics")
async def analytics(days: int = Query(default=30, ge=1, le=90), client_id: str = Depends(get_client_id)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    events = db().ai_evaluation_events
    match = {"client_id": client_id, "created_at": {"$gte": since}}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$event", "count": {"$sum": 1},
                    "avg_inference_latency_ms": {"$avg": "$inference_latency_ms"},
                    "avg_response_latency_ms": {"$avg": "$response_latency_ms"},
                    "avg_confidence": {"$avg": "$intent_confidence"}}},
    ]
    summary = {row["_id"]: {k: round(v, 2) if isinstance(v, float) else v for k, v in row.items() if k != "_id"} async for row in events.aggregate(pipeline)}
    intent_pipeline = [{"$match": {**match, "event": "message_processed"}}, {"$group": {"_id": "$intent", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
    intents = [{"intent": x.get("_id"), "count": x.get("count", 0)} async for x in events.aggregate(intent_pipeline)]
    outcomes = [{"status": x.get("_id"), "count": x.get("count", 0)} async for x in events.aggregate([{"$match": {**match, "event": "message_processed"}}, {"$group": {"_id": "$outcome", "count": {"$sum": 1}}}])]
    reviewed_pipeline = [{"$match": {**match, "event": "message_processed"}},
                         {"$group": {"_id": None, "reviewed": {"$sum": {"$cond": [{"$eq": [{"$type": "$intent_correct"}, "bool"]}, 1, 0]}}, "intent_correct": {"$sum": {"$cond": [{"$eq": ["$intent_correct", True]}, 1, 0]}},
                                     "catalogue_reviewed": {"$sum": {"$cond": [{"$eq": [{"$type": "$catalogue_correct"}, "bool"]}, 1, 0]}},
                                     "catalogue_correct": {"$sum": {"$cond": [{"$eq": ["$catalogue_correct", True]}, 1, 0]}},
                                     "grounded_reviewed": {"$sum": {"$cond": [{"$eq": [{"$type": "$reply_grounded"}, "bool"]}, 1, 0]}},
                                     "grounded_correct": {"$sum": {"$cond": [{"$eq": ["$reply_grounded", True]}, 1, 0]}}}}]
    reviewed_rows = [row async for row in events.aggregate(reviewed_pipeline)]
    quality = reviewed_rows[0] if reviewed_rows else {"reviewed": 0, "intent_correct": 0, "catalogue_reviewed": 0, "catalogue_correct": 0, "grounded_reviewed": 0, "grounded_correct": 0}
    for key, numerator, denominator in [("intent_accuracy", "intent_correct", "reviewed"), ("catalogue_accuracy", "catalogue_correct", "catalogue_reviewed"), ("grounded_reply_rate", "grounded_correct", "grounded_reviewed")]:
        quality[key] = round(quality[numerator] / quality[denominator], 4) if quality[denominator] else None
    quality.pop("_id", None)
    return {"period_days": days, "summary": summary, "intents": intents, "outcomes": outcomes, "reviewed_quality": quality, "usage": await get_client_usage(client_id),
            "note": "Reviewed accuracy metrics only become meaningful after a human labels evaluation events; model confidence is not a correctness guarantee."}


class ReviewInput(BaseModel):
    intent_correct: bool | None = None
    catalogue_correct: bool | None = None
    reply_grounded: bool | None = None
    notes: str = ""

@router.get("/evaluations")
async def list_evaluations(days: int = Query(default=7, ge=1, le=90), limit: int = Query(default=50, ge=1, le=100), client_id: str = Depends(get_client_id)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = db().ai_evaluation_events.find({"client_id": client_id, "event": "message_processed", "created_at": {"$gte": since}}).sort("created_at", -1).limit(limit)
    rows = []
    async for item in cursor:
        rows.append({"id": str(item["_id"]), "customer_text": item.get("customer_text", ""), "reply_text": item.get("reply_text", ""),
                     "intent": item.get("intent", "unknown"), "intent_source": item.get("intent_source", ""),
                     "confidence": item.get("intent_confidence", 0), "outcome": item.get("outcome", ""),
                     "intent_correct": item.get("intent_correct"), "catalogue_correct": item.get("catalogue_correct"),
                     "reply_grounded": item.get("reply_grounded"), "created_at": item.get("created_at")})
    return rows

@router.post("/evaluations/{event_id}/review")
async def review_event(event_id: str, payload: ReviewInput, client_id: str = Depends(get_client_id)):
    try: oid = ObjectId(event_id)
    except Exception: raise HTTPException(400, "Invalid evaluation event id")
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["reviewed_at"] = datetime.now(timezone.utc)
    result = await db().ai_evaluation_events.update_one({"_id": oid, "client_id": client_id, "event": "message_processed"}, {"$set": updates})
    if not result.matched_count: raise HTTPException(404, "Evaluation event not found")
    return {"ok": True, "reviewed": True}
