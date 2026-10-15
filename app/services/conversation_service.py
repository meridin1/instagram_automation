from datetime import datetime, timezone
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
    context_product_id = product_id or context.get("product_id") or (str(source_product["_id"]) if source_product else None)
    product = await get_product(client_id, context_product_id)

    automation = await database.automation_settings.find_one({"client_id": client_id}) or {}
    intent = await understand(text, product, context, bool(automation.get("llm_enabled", False)), client_id=client_id)

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
        "created_at": now(),
    }
    try:
        await database.messages.insert_one(inbound_doc)
    except Exception:
        if external_message_id:
            return {"status": "duplicate", "reply": None}
        raise

    reply, status = await build_response(client_id, intent, product, text)

    context["product_id"] = context_product_id
    context["language"] = "Manglish" if intent.source == "llm" and intent.entities.get("language") == "Manglish" else context.get("language")
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
        "conversation_id": str(convo["_id"]),
    }

    if send_to_instagram and status != "human":
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
