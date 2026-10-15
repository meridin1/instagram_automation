"""Platform-wide Meta/Instagram configuration stored in MongoDB.

The Meta app belongs to Meridin as a platform, not to an individual tenant.
Sensitive values are encrypted before they are written to platform_settings.
"""
from datetime import datetime, timezone
from app.database.mongo import db
from app.services.secret_service import encrypt_secret, decrypt_secret

META_DEFAULTS = {
    "graph_base_url": "https://graph.instagram.com",
    "graph_version": "v24.0",
    "redirect_uri": "http://localhost:8000/api/instagram/oauth/callback",
    "authorize_url": "https://www.instagram.com/oauth/authorize",
    "token_url": "https://api.instagram.com/oauth/access_token",
    "oauth_scopes": ["instagram_business_basic", "instagram_business_manage_messages"],
}
SECRET_FIELDS = {"oauth_client_secret", "app_secret", "verify_token"}

async def get_meta_config() -> dict:
    doc = await db().platform_settings.find_one({"_id": "meta_instagram"}) or {}
    config = dict(META_DEFAULTS)
    config.update({k: doc[k] for k in META_DEFAULTS if k in doc})
    config["oauth_client_id"] = doc.get("oauth_client_id", "")
    for field in SECRET_FIELDS:
        encrypted = doc.get(f"{field}_encrypted", "")
        config[field] = decrypt_secret(encrypted) if encrypted else ""
    return config

async def save_meta_config(values: dict) -> dict:
    now = datetime.now(timezone.utc)
    doc = {k: values[k] for k in META_DEFAULTS if k in values}
    doc["oauth_client_id"] = values.get("oauth_client_id", "").strip()
    for field in SECRET_FIELDS:
        value = values.get(field)
        if value is not None and value.strip():
            doc[f"{field}_encrypted"] = encrypt_secret(value.strip())
    doc["updated_at"] = now
    await db().platform_settings.update_one(
        {"_id": "meta_instagram"},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return await get_meta_config()

async def public_meta_config() -> dict:
    config = await get_meta_config()
    return {
        "configured": bool(config.get("oauth_client_id") and config.get("oauth_client_secret") and config.get("app_secret") and config.get("verify_token")),
        "oauth_client_id": config.get("oauth_client_id", ""),
        "oauth_client_secret_set": bool(config.get("oauth_client_secret")),
        "app_secret_set": bool(config.get("app_secret")),
        "verify_token_set": bool(config.get("verify_token")),
        "graph_base_url": config["graph_base_url"],
        "graph_version": config["graph_version"],
        "redirect_uri": config["redirect_uri"],
        "authorize_url": config["authorize_url"],
        "token_url": config["token_url"],
        "oauth_scopes": config["oauth_scopes"],
        "updated_at": (await db().platform_settings.find_one({"_id": "meta_instagram"}) or {}).get("updated_at"),
    }
