from datetime import datetime, timezone
import asyncio
import time
from bson import ObjectId
from app.database.mongo import db
from app.services.product_service import get_product
from app.services.ai_orchestrator import understand
from app.services.response_service import build_response
from app.services.instagram_service import InstagramService
from app.services.secret_service import account_access_token
from app.services.client_meta_config_service import get_client_meta_config
from app.services.usage_service import record_message, reserve_message_rate, data_limit_reached


def now():
    return datetime.now(timezone.utc)


async def get_or_create_conversation(client_id, sender_id, product_id=None, instagram_account_id=None):
    database = db()
    convo = await database.conversations.find_one({"client_id": client_id, "sender_id": sender_id})
    if convo:
        updates = {"updated_at": now()}
        context = dict(convo.get("context", {}))
        if product_id:
            context["product_id"] = product_id
        updates["context"] = context
        if instagram_account_id:
            updates["instagram_account_id"] = instagram_account_id
        await database.conversations.update_one({"_id": convo["_id"], "client_id": client_id}, {"$set": updates})
        return await database.conversations.find_one({"_id": convo["_id"], "client_id": client_id})

    doc = {
        "client_id": client_id,
        "sender_id": sender_id,
        "instagram_account_id": instagram_account_id,
        "status": "active",
        "automation_enabled": True,
        "context": {"product_id": product_id, "last_products": [], "language": None},
        "created_at": now(),
        "updated_at": now(),
    }
    result = await database.conversations.insert_one(doc)
    return await database.conversations.find_one({"_id": result.inserted_id, "client_id": client_id})


async def _resolve_source_product(client_id: str, source_id: str | None):
    if not source_id:
        return None
    mapping = await db().product_mappings.find_one({"client_id": client_id, "instagram_media_id": source_id})
    if not mapping:
        return None
    return await get_product(client_id, mapping["product_id"])


async def process_inbound(
    client_id: str,
    sender_id: str,
    text: str,
    instagram_account_id: str | None = None,
    product_id: str | None = None,
    source_type: str = "dm",
    source_id: str | None = None,
    send_to_instagram: bool = False,
    external_message_id: str | None = None,
    image_url: str | None = None,
):
    database = db()
    client_doc = await database.clients.find_one({"_id": ObjectId(client_id)})
    if not client_doc or client_doc.get("active") is False:
        return {"status": "client_disabled", "reply": None}

    if external_message_id:
        existing = await database.messages.find_one({"client_id": client_id, "external_message_id": external_message_id})
        if existing:
            return {"status": "duplicate", "reply": None}

    rate = int(client_doc.get("rate_limit_per_minute", 60) or 60)
    if not await reserve_message_rate(client_id, rate):
        return {"status": "rate_limited", "reply": None}
    if await data_limit_reached(client_id, client_doc):
        return {"status": "data_limit_reached", "reply": None}

    await record_message(client_id, "inbound", text)
    source_product = await _resolve_source_product(client_id, source_id)
    convo = await get_or_create_conversation(client_id, sender_id, product_id or (str(source_product["_id"]) if source_product else None), instagram_account_id=instagram_account_id)

    if not convo.get("automation_enabled", True) or not client_doc.get("automation_enabled", True):
        await database.conversations.update_one({"_id": convo["_id"], "client_id": client_id}, {"$set": {"status": "human", "automation_enabled": False, "updated_at": now()}})
        await database.messages.insert_one({
            "conversation_id": convo["_id"], "client_id": client_id, "direction": "inbound",
            "sender_id": sender_id, "text": text, "source_type": source_type, "source_id": source_id,
            "external_message_id": external_message_id, "intent": "human_handoff", "intent_source": "rules", "created_at": now(),
        })
        return {"status": "human", "reply": None, "intent": "human_handoff", "conversation_id": str(convo["_id"])}

    context = dict(convo.get("context", {}))
    # Add a short, tenant/conversation-scoped window so follow-ups like "what about blue?"
    # can be interpreted without sending an unbounded conversation transcript.
    history_cursor = database.messages.find(
        {"client_id": client_id, "conversation_id": convo["_id"]},
        {"direction": 1, "text": 1, "intent": 1, "created_at": 1},
    ).sort("created_at", -1).limit(8)
    history = [m async for m in history_cursor]
    history.reverse()
    context["recent_messages"] = [
        {"role": "customer" if m.get("direction") == "inbound" else "shop", "text": str(m.get("text", ""))[:500], "intent": m.get("intent")}
        for m in history
    ]
    context_product_id = product_id or context.get("product_id") or (str(source_product["_id"]) if source_product else None)
    product = await get_product(client_id, context_product_id)

    automation = await database.automation_settings.find_one({"client_id": client_id}) or {}

    # Text understanding and image embedding run concurrently. The visual path is
    # CLIP similarity retrieval only; it does not ask an LLM to describe the image.
    visual_vector_task = None
    if image_url:
        from app.services.visual_search_service import image_url_embedding
        visual_vector_task = image_url_embedding(image_url, meta_only=True)

    inference_started = time.monotonic()
    if visual_vector_task is not None:
        intent, visual_vector = await asyncio.gather(
            understand(text, product, context, bool(automation.get("llm_enabled", False)), client_id=client_id),
            visual_vector_task,
        )
    else:
        intent = await understand(text, product, context, bool(automation.get("llm_enabled", False)), client_id=client_id)
        visual_vector = None
    inference_latency_ms = int((time.monotonic() - inference_started) * 1000)

    visual_candidates = []
    visual_filtered_candidates = []
    if visual_vector:
        from app.services.visual_search_service import search_by_embedding
        from app.services.semantic_search_service import _passes_filters
        # First retrieve visually similar designs, then apply text attributes such as
        # colour/size/budget. This supports "ithinte blue color undo?" correctly.
        visual_candidates = await search_by_embedding(client_id, visual_vector, {}, limit=8)
        visual_filtered_candidates = [
            item for item in visual_candidates if _passes_filters(item, intent.entities)
        ]

    inbound_doc = {
        "conversation_id": convo["_id"],
        "client_id": client_id,
        "direction": "inbound",
        "sender_id": sender_id,
        "text": text,
        "source_type": source_type,
        "source_id": source_id,
        "external_message_id": external_message_id,
        "intent": intent.intent,
        "intent_confidence": intent.confidence,
        "intent_source": intent.source,
        "entities": intent.entities,
        "has_image": bool(image_url),
        "visual_match_count": len(visual_filtered_candidates),
        "secondary_intents": intent.secondary_intents,
        "needs_context": intent.needs_context,
        "clarification_required": intent.clarification_required,
        "created_at": now(),
    }
    try:
        await database.messages.insert_one(inbound_doc)
    except Exception:
        if external_message_id:
            return {"status": "duplicate", "reply": None}
        raise

    response_started = time.monotonic()
    reply, status = await build_response(
        client_id, intent, product, text,
        visual_candidates=visual_candidates,
        visual_filtered_candidates=visual_filtered_candidates,
        has_image=bool(image_url),
        context=context,
    )
    response_latency_ms = int((time.monotonic() - response_started) * 1000)
    try:
        await database.ai_evaluation_events.insert_one({
            "client_id": client_id, "conversation_id": convo["_id"], "event": "message_processed",
            "intent": intent.intent, "intent_source": intent.source, "intent_confidence": float(intent.confidence),
            "has_image": bool(image_url), "outcome": status,
            "catalogue_match_count": len(visual_filtered_candidates),
            "inference_latency_ms": inference_latency_ms, "response_latency_ms": response_latency_ms,
            "reply_length": len(reply or ""), "customer_text": str(text or "")[:500], "reply_text": str(reply or "")[:1000], "created_at": now(),
        })
    except Exception:
        # Telemetry must never prevent a valid customer reply from being sent.
        pass

    context["product_id"] = context_product_id
    context["last_intent"] = intent.intent
    context["last_entities"] = intent.entities
    context["last_customer_message"] = text[:500]
    context["language"] = "Manglish" if intent.source in {"llm", "tier2_llm"} and intent.entities.get("language") == "Manglish" else context.get("language")
    if product:
        context["last_products"] = [str(product["_id"])] + [x for x in context.get("last_products", []) if x != str(product["_id"])][:4]

    await database.messages.insert_one({
        "conversation_id": convo["_id"],
        "client_id": client_id,
        "direction": "outbound",
        "sender_id": "meridin",
        "text": reply,
        "created_at": now(),
    })
    await record_message(client_id, "outbound", reply)

    await database.conversations.update_one(
        {"_id": convo["_id"], "client_id": client_id},
        {"$set": {
            "updated_at": now(),
            "status": "human" if status == "human" else "active",
            "automation_enabled": status != "human",
            "context": context,
        }},
    )

    result = {
        "status": status,
        "reply": reply,
        "intent": intent.intent,
        "intent_confidence": intent.confidence,
        "intent_source": intent.source,
        "entities": intent.entities,
        "has_image": bool(image_url),
        "visual_matches": [
            {"product_id": str(item.get("_id")), "similarity": item.get("visual_similarity")}
            for item in visual_filtered_candidates[:5]
        ],
        "secondary_intents": intent.secondary_intents,
        "needs_context": intent.needs_context,
        "clarification_required": intent.clarification_required,
        "conversation_id": str(convo["_id"]),
    }

    # Send the acknowledgement even when this reply triggers human handover.
    # The conversation remains marked as human, but the customer still receives the message.
    if send_to_instagram:
        account_query = {"client_id": client_id, "active": True}
        if instagram_account_id:
            try:
                account_query["_id"] = ObjectId(instagram_account_id)
            except Exception:
                account_query["_id"] = None
        account = await database.instagram_accounts.find_one(account_query)
        if account:
            meta = await InstagramService().send_text(
                account["instagram_user_id"],
                account_access_token(account),
                sender_id,
                reply,
                await get_client_meta_config(client_id),
            )
            result["meta"] = meta

    return result


async def list_conversations(client_id: str, status: str | None = None):
    query = {"client_id": client_id}
    if status:
        query["status"] = status
    cursor = db().conversations.find(query).sort("updated_at", -1).limit(100)
    return [serialize_conversation(x) async for x in cursor]


def serialize_conversation(doc):
    return {
        "id": str(doc["_id"]),
        "sender_id": doc["sender_id"],
        "status": doc.get("status", "active"),
        "automation_enabled": doc.get("automation_enabled", True),
        "context": doc.get("context", {}),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }
