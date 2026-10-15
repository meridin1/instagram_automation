"""Per-customer Instagram/Meta app settings. Secrets are encrypted at rest."""
from datetime import datetime, timezone
from bson import ObjectId
from app.core.config import settings
from app.database.mongo import db
from app.services.secret_service import encrypt_secret, decrypt_secret

DEFAULTS = {
    "graph_base_url": "https://graph.instagram.com",
    "graph_version": "v24.0",
    "authorize_url": "https://www.instagram.com/oauth/authorize",
    "token_url": "https://api.instagram.com/oauth/access_token",
    "oauth_scopes": ["instagram_business_basic", "instagram_business_manage_messages"],
}
SECRET_FIELDS = ("oauth_client_secret", "app_secret", "verify_token")

def callback_uri() -> str:
    return settings.public_base_url.rstrip("/") + "/api/instagram/oauth/callback"

def webhook_uri(client_id: str) -> str:
    return settings.public_base_url.rstrip("/") + f"/webhooks/instagram/{client_id}"

async def get_client_meta_config(client_id: str) -> dict:
    doc = await db().client_meta_configs.find_one({"_id": client_id}) or {}
    config = dict(DEFAULTS)
    config.update({k: doc[k] for k in DEFAULTS if k in doc})
    config["oauth_client_id"] = doc.get("oauth_client_id", "")
    config["redirect_uri"] = callback_uri()
    config["webhook_url"] = webhook_uri(client_id)
    config["client_id"] = client_id
    for field in SECRET_FIELDS:
        encrypted = doc.get(f"{field}_encrypted", "")
        config[field] = decrypt_secret(encrypted) if encrypted else ""
    return config

async def save_client_meta_config(client_id: str, values: dict) -> dict:
    if not await db().clients.find_one({"_id": ObjectId(client_id)}):
        from fastapi import HTTPException
        raise HTTPException(404, "Client workspace not found")
    current = await get_client_meta_config(client_id)
    oauth_client_id = str(values.get("oauth_client_id", "")).strip()
    if not oauth_client_id:
        from fastapi import HTTPException
        raise HTTPException(422, "Instagram App ID is required")
    # If the customer changes Meta apps, require the matching secrets for the new app.
    changing_app = bool(current.get("oauth_client_id") and current.get("oauth_client_id") != oauth_client_id)
    for field in SECRET_FIELDS:
        incoming = str(values.get(field, "") or "").strip()
        if (not current.get(field) or changing_app) and not incoming:
            from fastapi import HTTPException
            label = {"oauth_client_secret": "Instagram App Secret", "app_secret": "Meta App Secret", "verify_token": "Webhook Verify Token"}[field]
            raise HTTPException(422, f"{label} is required" + (" when changing Meta apps" if changing_app else ""))
    now = datetime.now(timezone.utc)
    doc = {k: values[k] for k in DEFAULTS if k in values}
    doc["oauth_client_id"] = oauth_client_id
    doc["updated_at"] = now
    for field in SECRET_FIELDS:
        value = values.get(field)
        if value is not None and str(value).strip():
            doc[f"{field}_encrypted"] = encrypt_secret(str(value).strip())
    await db().client_meta_configs.update_one(
        {"_id": client_id},
        {"$set": doc, "$setOnInsert": {"client_id": client_id, "created_at": now}},
        upsert=True,
    )
    return await public_client_meta_config(client_id)

async def public_client_meta_config(client_id: str) -> dict:
    c = await get_client_meta_config(client_id)
    return {
        "configured": bool(c.get("oauth_client_id") and c.get("oauth_client_secret") and c.get("app_secret") and c.get("verify_token")),
        "oauth_client_id": c.get("oauth_client_id", ""),
        "oauth_client_secret_set": bool(c.get("oauth_client_secret")),
        "app_secret_set": bool(c.get("app_secret")),
        "verify_token_set": bool(c.get("verify_token")),
        "graph_base_url": c["graph_base_url"],
        "graph_version": c["graph_version"],
        "redirect_uri": c["redirect_uri"],
        "webhook_url": c["webhook_url"],
        "authorize_url": c["authorize_url"],
        "token_url": c["token_url"],
        "oauth_scopes": c["oauth_scopes"],
        "updated_at": (await db().client_meta_configs.find_one({"_id": client_id}) or {}).get("updated_at"),
    }
