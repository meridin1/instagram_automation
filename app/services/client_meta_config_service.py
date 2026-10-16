"""Per-customer Instagram app settings for manual-token connection. Secrets are encrypted at rest."""
from datetime import datetime, timezone
from bson import ObjectId
from app.core.config import settings
from app.database.mongo import db
from app.services.secret_service import encrypt_secret, decrypt_secret

DEFAULTS = {
    "graph_base_url": "https://graph.instagram.com",
    "graph_version": "v24.0",
}
SECRET_FIELDS = ("instagram_app_secret", "app_secret", "verify_token")


def webhook_uri(client_id: str) -> str:
    return settings.public_base_url.rstrip("/") + f"/webhooks/instagram/{client_id}"


async def get_client_meta_config(client_id: str) -> dict:
    doc = await db().client_meta_configs.find_one({"_id": client_id}) or {}
    config = dict(DEFAULTS)
    config.update({k: doc[k] for k in DEFAULTS if k in doc})
    # Read legacy OAuth-named fields so existing workspaces remain compatible.
    config["app_id"] = doc.get("app_id", doc.get("oauth_client_id", ""))
    config["webhook_url"] = webhook_uri(client_id)
    config["client_id"] = client_id
    for field in SECRET_FIELDS:
        encrypted = doc.get(f"{field}_encrypted", "")
        if field == "instagram_app_secret" and not encrypted:
            encrypted = doc.get("oauth_client_secret_encrypted", "")
        config[field] = decrypt_secret(encrypted) if encrypted else ""
    return config


async def save_client_meta_config(client_id: str, values: dict) -> dict:
    if not await db().clients.find_one({"_id": ObjectId(client_id)}):
        from fastapi import HTTPException
        raise HTTPException(404, "Client workspace not found")
    current = await get_client_meta_config(client_id)
    app_id = str(values.get("app_id", values.get("oauth_client_id", "")) or "").strip()
    if not app_id:
        from fastapi import HTTPException
        raise HTTPException(422, "Instagram App ID is required")
    changing_app = bool(current.get("app_id") and current.get("app_id") != app_id)
    if (not current.get("app_secret") or changing_app) and not str(values.get("app_secret", "") or "").strip():
        from fastapi import HTTPException
        raise HTTPException(422, "Meta App Secret is required for webhook signature verification" + (" when changing the app ID" if changing_app else ""))
    if not current.get("verify_token") and not str(values.get("verify_token", "") or "").strip():
        from fastapi import HTTPException
        raise HTTPException(422, "Webhook Verify Token is required")
    now = datetime.now(timezone.utc)
    doc = {k: values[k] for k in DEFAULTS if k in values}
    doc["app_id"] = app_id
    doc["updated_at"] = now
    for field in SECRET_FIELDS:
        value = values.get(field)
        # Accept old frontend/client field names during migration.
        if field == "instagram_app_secret" and value is None:
            value = values.get("oauth_client_secret")
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
    doc = await db().client_meta_configs.find_one({"_id": client_id}) or {}
    return {
        "configured": bool(c.get("app_id") and c.get("app_secret") and c.get("verify_token")),
        "app_id": c.get("app_id", ""),
        "instagram_app_secret_set": bool(c.get("instagram_app_secret")),
        "app_secret_set": bool(c.get("app_secret")),
        "verify_token_set": bool(c.get("verify_token")),
        "graph_base_url": c["graph_base_url"],
        "graph_version": c["graph_version"],
        "webhook_url": c["webhook_url"],
        "updated_at": doc.get("updated_at"),
    }
