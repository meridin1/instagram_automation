import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from app.core.security import get_client_id
from app.database.mongo import db
from app.models.schemas import InstagramAccountCreate, ProductMappingCreate
from app.services.instagram_service import InstagramService
from app.services.secret_service import encrypt_secret, account_access_token
from app.services.platform_config_service import get_meta_config
from app.services.conversation_service import process_inbound

router = APIRouter(tags=["instagram"])


@router.post("/api/instagram/accounts")
async def create_account(payload: InstagramAccountCreate, client_id: str = Depends(get_client_id)):
    owner = await db().instagram_accounts.find_one({"instagram_user_id": payload.instagram_user_id})
    if owner and owner.get("client_id") != client_id:
        raise HTTPException(409, "This Instagram account is already connected to another Meridin workspace")
    await db().instagram_accounts.update_one(
        {"client_id": client_id, "instagram_user_id": payload.instagram_user_id},
        {"$set": {
            "client_id": client_id,
            "instagram_user_id": payload.instagram_user_id,
            "username": payload.username,
            "access_token_encrypted": encrypt_secret(payload.access_token),
            "token_expires_at": payload.token_expires_at,
            "active": True,
            "updated_at": datetime.now(timezone.utc),
        }, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"ok": True, "username": payload.username, "instagram_user_id": payload.instagram_user_id}


@router.post("/api/instagram/accounts/{account_id}/subscribe")
async def subscribe_account(account_id: str, client_id: str = Depends(get_client_id)):
    from bson import ObjectId
    try: oid=ObjectId(account_id)
    except Exception: raise HTTPException(400,"Invalid account id")
    account=await db().instagram_accounts.find_one({"_id":oid,"client_id":client_id,"active":True})
    if not account: raise HTTPException(404,"Instagram account not found")
    result=await InstagramService().subscribe_messages(account["instagram_user_id"],account_access_token(account))
    await db().instagram_accounts.update_one({"_id":oid},{"$set":{"webhook_subscribed":True,"webhook_subscribed_at":datetime.now(timezone.utc)}})
    return {"ok":True,"result":result}

@router.get("/api/instagram/accounts")
async def accounts(client_id: str = Depends(get_client_id)):
    cursor = db().instagram_accounts.find({"client_id": client_id}, {"access_token": 0, "access_token_encrypted": 0}).sort("updated_at", -1)
    return [
        {**{k: v for k, v in x.items() if k != "_id"}, "id": str(x["_id"])}
        async for x in cursor
    ]


@router.post("/api/instagram/connect")
async def connect(client_id: str = Depends(get_client_id)):
    config = await get_meta_config()
    if not config.get("oauth_client_id") or not config.get("oauth_client_secret"):
        raise HTTPException(503, "Instagram integration is not configured by the Meridin platform administrator")
    service = InstagramService()
    state = service.oauth_state(client_id)
    await db().oauth_states.insert_one({"state": state, "client_id": client_id, "created_at": datetime.now(timezone.utc)})
    return {"authorization_url": service.build_oauth_url(state, config)}


@router.get("/api/instagram/oauth/callback")
async def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    if error:
        detail = error_description or error
        raise HTTPException(400, f"Instagram authorization was not completed: {detail[:250]}")
    if not code or not state:
        raise HTTPException(400, "Instagram did not return the authorization code and state")
    state_doc = await db().oauth_states.find_one({"state": state})
    if not state_doc:
        raise HTTPException(400, "Invalid or expired OAuth state")
    created_at = state_doc.get("created_at")
    # PyMongo/Motor commonly returns BSON datetimes as naive UTC values.
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if not created_at or datetime.now(timezone.utc) - created_at > timedelta(minutes=10):
        await db().oauth_states.delete_one({"_id": state_doc["_id"]})
        raise HTTPException(400, "Instagram connection timed out. Please connect again from the dashboard.")
    # Consume state before exchanging the code so the same callback cannot be replayed.
    await db().oauth_states.delete_one({"_id": state_doc["_id"]})
    config = await get_meta_config()
    if not config.get("oauth_client_id") or not config.get("oauth_client_secret"):
        raise HTTPException(503, "Instagram integration is not configured by the Meridin platform administrator")
    service = InstagramService()
    short_lived_data = await service.exchange_code(code, config)
    short_lived_token = short_lived_data.get("access_token")
    if not short_lived_token:
        raise HTTPException(502, "OAuth response did not contain an access token")
    token_data = await service.exchange_long_lived_token(short_lived_token, config)
    access_token = token_data["access_token"]
    account = await service.fetch_account(access_token)
    expires_in = int(token_data.get("expires_in", 0) or 0)
    expires_at = datetime.now(timezone.utc).timestamp() + expires_in if expires_in else None
    await service.save_account(state_doc["client_id"], account, access_token, expires_at=expires_at)
    return RedirectResponse(url="/dashboard/?instagram=connected")


@router.post("/api/instagram/accounts/{account_id}/refresh-token")
async def refresh_account_token(account_id: str, client_id: str = Depends(get_client_id)):
    from bson import ObjectId
    try:
        oid = ObjectId(account_id)
    except Exception:
        raise HTTPException(400, "Invalid account id")
    account = await db().instagram_accounts.find_one({"_id": oid, "client_id": client_id, "active": True})
    if not account:
        raise HTTPException(404, "Instagram account not found")
    token_data = await InstagramService().refresh_long_lived_token(account_access_token(account))
    expires_in = int(token_data.get("expires_in", 0) or 0)
    expires_at = datetime.now(timezone.utc).timestamp() + expires_in if expires_in else account.get("token_expires_at")
    await db().instagram_accounts.update_one(
        {"_id": oid, "client_id": client_id},
        {"$set": {
            "access_token_encrypted": encrypt_secret(token_data["access_token"]),
            "token_expires_at": expires_at,
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    return {"ok": True, "token_expires_at": expires_at}


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


@router.get("/webhooks/instagram")
async def verify_webhook(request: Request):
    params = request.query_params
    config = await get_meta_config()
    if not config.get("verify_token") or params.get("hub.verify_token") != config["verify_token"]:
        raise HTTPException(403, "Verification token mismatch")
    return int(params.get("hub.challenge", "0"))


@router.post("/webhooks/instagram")
async def receive_webhook(request: Request):
    raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    config = await get_meta_config()
    if not InstagramService().verify_signature(raw, signature, config.get("app_secret")):
        raise HTTPException(403, "Invalid webhook signature")

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
                if "image" in attachment_types:
                    text = "[instagram_attachment:image]"
                elif "audio" in attachment_types:
                    text = "[instagram_attachment:audio]"
                elif "video" in attachment_types:
                    text = "[instagram_attachment:video]"
                else:
                    text = "[instagram_attachment:other]"
            if text and sender:
                events.append({
                    "sender_id": sender,
                    "recipient_id": recipient,
                    "text": text,
                    "message_id": message.get("mid"),
                    "timestamp": messaging.get("timestamp"),
                })

    # Return quickly to Meta after basic validation. Processing happens after payload parsing.
    # FastAPI keeps this request alive until the coroutine completes, so process only parsed events.
    results = []
    for event in events:
        account = await db().instagram_accounts.find_one({"instagram_user_id": event["recipient_id"], "active": True})
        if not account:
            continue
        try:
            result = await process_inbound(
                client_id=account["client_id"],
                instagram_account_id=str(account["_id"]),
                sender_id=event["sender_id"],
                text=event["text"],
                send_to_instagram=True,
                external_message_id=event["message_id"],
            )
            results.append(result)
        except Exception as exc:
            results.append({"status": "error", "error": str(exc)[:300]})
    return {"ok": True, "processed": len(results)}
