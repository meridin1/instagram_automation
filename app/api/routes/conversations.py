from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.security import get_client_id
from app.database.mongo import db
from app.models.schemas import HumanMessage, TestInbound
from app.services.conversation_service import list_conversations, process_inbound
from app.services.secret_service import account_access_token
from app.services.client_meta_config_service import get_client_meta_config
from app.services.usage_service import record_message

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("")
async def conversations(status: str | None = Query(default=None), client_id: str = Depends(get_client_id)):
    return await list_conversations(client_id, status)


@router.get("/{conversation_id}/messages")
async def messages(conversation_id: str, client_id: str = Depends(get_client_id)):
    try:
        oid = ObjectId(conversation_id)
    except Exception:
        raise HTTPException(400, "Invalid conversation id")
    convo = await db().conversations.find_one({"_id": oid, "client_id": client_id})
    if not convo:
        raise HTTPException(404, "Conversation not found")
    cursor = db().messages.find({"conversation_id": oid, "client_id": client_id}).sort("created_at", 1).limit(500)
    return [
        {
            "id": str(m["_id"]),
            "direction": m["direction"],
            "text": m["text"],
            "intent": m.get("intent"),
            "intent_source": m.get("intent_source"),
            "entities": m.get("entities", {}),
            "created_at": m.get("created_at"),
        }
        async for m in cursor
    ]


@router.post("/{conversation_id}/takeover")
async def takeover(conversation_id: str, client_id: str = Depends(get_client_id)):
    try:
        oid = ObjectId(conversation_id)
    except Exception:
        raise HTTPException(400, "Invalid conversation id")
    result = await db().conversations.update_one({"_id": oid, "client_id": client_id}, {"$set": {"automation_enabled": False, "status": "human"}})
    if result.matched_count == 0:
        raise HTTPException(404, "Conversation not found")
    return {"ok": True, "automation_enabled": False, "status": "human"}


@router.post("/{conversation_id}/resume")
async def resume(conversation_id: str, client_id: str = Depends(get_client_id)):
    try:
        oid = ObjectId(conversation_id)
    except Exception:
        raise HTTPException(400, "Invalid conversation id")
    result = await db().conversations.update_one({"_id": oid, "client_id": client_id}, {"$set": {"automation_enabled": True, "status": "active"}})
    if result.matched_count == 0:
        raise HTTPException(404, "Conversation not found")
    return {"ok": True, "automation_enabled": True, "status": "active"}


@router.post("/{conversation_id}/reply")
async def human_reply(conversation_id: str, payload: HumanMessage, client_id: str = Depends(get_client_id)):
    try:
        oid = ObjectId(conversation_id)
    except Exception:
        raise HTTPException(400, "Invalid conversation id")
    convo = await db().conversations.find_one({"_id": oid, "client_id": client_id})
    if not convo:
        raise HTTPException(404, "Conversation not found")
    account_query = {"client_id": client_id, "active": True}
    if convo.get("instagram_account_id"):
        account_query["_id"] = ObjectId(convo["instagram_account_id"])
    account = await db().instagram_accounts.find_one(account_query)
    if not account:
        raise HTTPException(400, "No active Instagram account")
    from app.services.instagram_service import InstagramService
    result = await InstagramService().send_text(account["instagram_user_id"], account_access_token(account), convo["sender_id"], payload.text, await get_client_meta_config(client_id))
    await db().messages.insert_one({
        "conversation_id": oid, "client_id": client_id, "direction": "outbound",
        "sender_id": "human", "text": payload.text, "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    })
    await record_message(client_id, "outbound", payload.text)
    return {"ok": True, "meta": result}
