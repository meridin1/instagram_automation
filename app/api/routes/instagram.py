import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.security import get_client_id
from app.database.mongo import db
from app.models.schemas import InstagramAccountCreate, ProductMappingCreate
from app.services.instagram_service import InstagramService
from app.services.secret_service import encrypt_secret, account_access_token
from app.services.client_meta_config_service import get_client_meta_config
from app.services.conversation_service import process_inbound

router = APIRouter(tags=["instagram"])


@router.post("/api/instagram/accounts")
async def create_account(payload: InstagramAccountCreate, client_id: str = Depends(get_client_id)):
    """Save manually supplied Instagram account ID, username and access token."""
    existing = await db().instagram_accounts.find_one({"client_id": client_id, "instagram_user_id": payload.instagram_user_id})
    owner = await db().instagram_accounts.find_one({"instagram_user_id": payload.instagram_user_id})
    if owner and owner.get("client_id") != client_id:
        raise HTTPException(409, "This Instagram account is already connected to another Meridin workspace")
    token = (payload.access_token or "").strip()
    if not token and not existing:
        raise HTTPException(422, "Instagram access token is required for the first connection")
    values = {
        "client_id": client_id,
        "instagram_user_id": payload.instagram_user_id.strip(),
        "username": payload.username.strip().lstrip("@"),
        "active": True,
        "updated_at": datetime.now(timezone.utc),
    }
    if token:
        values["access_token_encrypted"] = encrypt_secret(token)
    if payload.token_expires_at:
        values["token_expires_at"] = payload.token_expires_at
    await db().instagram_accounts.update_one(
        {"client_id": client_id, "instagram_user_id": payload.instagram_user_id.strip()},
        {"$set": values, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"ok": True, "username": payload.username.strip().lstrip("@"), "instagram_user_id": payload.instagram_user_id.strip(), "token_saved": True}


@router.post("/api/instagram/accounts/{account_id}/subscribe")
async def subscribe_account(account_id: str, client_id: str = Depends(get_client_id)):
    from bson import ObjectId
    try: oid=ObjectId(account_id)
    except Exception: raise HTTPException(400,"Invalid account id")
    account=await db().instagram_accounts.find_one({"_id":oid,"client_id":client_id,"active":True})
    if not account: raise HTTPException(404,"Instagram account not found")
    config = await get_client_meta_config(client_id)
    result=await InstagramService().subscribe_messages(account["instagram_user_id"],account_access_token(account),config)
    await db().instagram_accounts.update_one({"_id":oid},{"$set":{"webhook_subscribed":True,"webhook_subscribed_at":datetime.now(timezone.utc)}})
    return {"ok":True,"result":result}

@router.get("/api/instagram/accounts")
async def accounts(client_id: str = Depends(get_client_id)):
    cursor = db().instagram_accounts.find({"client_id": client_id}, {"access_token": 0, "access_token_encrypted": 0}).sort("updated_at", -1)
    return [
        {**{k: v for k, v in x.items() if k != "_id"}, "id": str(x["_id"])}
        async for x in cursor
    ]


@router.post("/api/instagram/mappings")
async def create_mapping(payload: ProductMappingCreate, client_id: str = Depends(get_client_id)):
    from bson import ObjectId
    try:
        product_oid = ObjectId(payload.product_id)
    except Exception:
        raise HTTPException(400, "Invalid product id")
    product = await db().products.find_one({"_id": product_oid, "client_id": client_id})
    if not product:
        raise HTTPException(404, "Product not found")
    result = await db().product_mappings.update_one(
        {"client_id": client_id, "instagram_media_id": payload.instagram_media_id},
        {"$set": {
            "client_id": client_id,
            "instagram_media_id": payload.instagram_media_id,
            "instagram_post_id": payload.instagram_post_id,
            "product_id": payload.product_id,
            "updated_at": datetime.now(timezone.utc),
        }, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    await db().products.update_one({"_id": product_oid, "client_id": client_id}, {"$set": {
        "instagram_post_id": payload.instagram_post_id,
        "instagram_media_id": payload.instagram_media_id,
        "updated_at": datetime.now(timezone.utc),
    }})
    return {"ok": True, "mapping_id": str(result.upserted_id or payload.instagram_media_id)}


@router.get("/webhooks/instagram/{client_id}")
async def verify_webhook(client_id: str, request: Request):
    config = await get_client_meta_config(client_id)
    params = request.query_params
    if not config.get("verify_token") or params.get("hub.verify_token") != config["verify_token"]:
        raise HTTPException(403, "Verification token mismatch for this customer app")
    return int(params.get("hub.challenge", "0"))


@router.post("/webhooks/instagram/{client_id}")
async def receive_webhook(client_id: str, request: Request):
    raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    config = await get_client_meta_config(client_id)
    service = InstagramService()
    # The configured app secrets may be distinct. Accept the signature only
    # when it matches one of this tenant's configured secrets; never try another tenant's keys.
    valid = service.verify_signature(raw, signature, config.get("app_secret")) or service.verify_signature(raw, signature, config.get("instagram_app_secret"))
    if not valid:
        raise HTTPException(403, "Invalid webhook signature for this customer app")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Invalid JSON")
    events = []
    for entry in payload.get("entry", []):
        for messaging in entry.get("messaging", []):
            message = messaging.get("message") or {}
            text = message.get("text")
            attachments = message.get("attachments") or []
            sender = (messaging.get("sender") or {}).get("id")
            recipient = (messaging.get("recipient") or {}).get("id")
            if not text and attachments:
                attachment_types = {str(item.get("type", "attachment")).lower() for item in attachments if isinstance(item, dict)}
                if "image" in attachment_types: text = "[instagram_attachment:image]"
                elif "audio" in attachment_types: text = "[instagram_attachment:audio]"
                elif "video" in attachment_types: text = "[instagram_attachment:video]"
                else: text = "[instagram_attachment:other]"
            if text and sender:
                events.append({"sender_id": sender, "recipient_id": recipient, "text": text, "message_id": message.get("mid"), "timestamp": messaging.get("timestamp")})
    results = []
    for event in events:
        account = await db().instagram_accounts.find_one({"instagram_user_id": event["recipient_id"], "client_id": client_id, "active": True})
        if not account:
            continue
        try:
            result = await process_inbound(client_id=client_id, instagram_account_id=str(account["_id"]), sender_id=event["sender_id"], text=event["text"], send_to_instagram=True, external_message_id=event["message_id"])
            results.append(result)
        except Exception as exc:
            results.append({"status": "error", "error": str(exc)[:300]})
    return {"ok": True, "processed": len(results)}


@router.get("/webhooks/instagram")
async def old_webhook_url_notice():
    raise HTTPException(400, "Use the customer-specific webhook URL shown in the Client Portal → Instagram integration settings.")


@router.post("/webhooks/instagram")
async def old_webhook_post_notice():
    raise HTTPException(400, "Use the customer-specific webhook URL shown in the Client Portal → Instagram integration settings.")
