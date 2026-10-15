import hashlib
import hmac
import secrets
from urllib.parse import urlencode
import httpx
from fastapi import HTTPException
from app.database.mongo import db
from app.services.secret_service import encrypt_secret, account_access_token


class InstagramService:
    def _url(self, path: str, config: dict) -> str:
        base = config["graph_base_url"].rstrip("/")
        return f"{base}/{config['graph_version']}/{path.lstrip('/')}"

    async def subscribe_messages(self, ig_user_id: str, access_token: str, config: dict | None = None):
        # Instagram API with Instagram Login subscribes the authorized account via /me.
        # ig_user_id is retained in the signature for callers and audit logs, but must not
        # be used as the subscription path for this auth flow.
        config = config or {}
        if not config.get("graph_base_url") or not config.get("graph_version"):
            raise HTTPException(503, "Customer Meta app configuration is missing")
        url = self._url("me/subscribed_apps", config)
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(url, data={"subscribed_fields": "messages,messaging_postbacks", "access_token": access_token})
            if response.status_code >= 400:
                raise HTTPException(502, f"Instagram webhook subscription failed: {response.text[:500]}")
            return response.json()

    async def send_text(self, ig_user_id: str, access_token: str, recipient_id: str, text: str, config: dict | None = None):
        # Meta's Instagram messaging endpoint can vary by API product/version.
        # This uses the current Graph-style /{ig-user_id}/messages shape.
        config = config or {}
        if not config.get("graph_base_url") or not config.get("graph_version"):
            raise HTTPException(503, "Customer Meta app configuration is missing")
        url = self._url(f"{ig_user_id}/messages", config)
        payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code >= 400:
                raise HTTPException(502, f"Instagram send failed: {response.text[:500]}")
            return response.json()

    def verify_signature(self, raw_body: bytes, signature: str | None, app_secret: str | None = None) -> bool:
        # Fail closed: a signature must match the configured secret for the target customer app.
        if not app_secret:
            return False
        if not signature or not signature.startswith("sha256="):
            return False
        expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature.split("=", 1)[1], expected)

    def oauth_state(self, client_id: str) -> str:
        return f"{client_id}.{secrets.token_urlsafe(24)}"

    def build_oauth_url(self, state: str, config: dict) -> str:
        params = {
            "client_id": config["oauth_client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "scope": ",".join(config["oauth_scopes"]),
            "state": state,
        }
        return f"{config['authorize_url']}?{urlencode(params)}"

    async def exchange_code(self, code: str, config: dict):
        data = {
            "client_id": config["oauth_client_id"],
            "client_secret": config["oauth_client_secret"],
            "grant_type": "authorization_code",
            "redirect_uri": config["redirect_uri"],
            "code": code,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(config["token_url"], data=data)
            if response.status_code >= 400:
                raise HTTPException(502, f"Instagram OAuth exchange failed: {response.text[:500]}")
            return response.json()

    async def exchange_long_lived_token(self, short_lived_token: str, config: dict):
        # Token exchange endpoints are unversioned even when Graph API calls are versioned.
        url = f"{config['graph_base_url'].rstrip('/')}/access_token"
        params = {
            "grant_type": "ig_exchange_token",
            "client_secret": config["oauth_client_secret"],
            "access_token": short_lived_token,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, params=params)
            if response.status_code >= 400:
                raise HTTPException(502, f"Instagram long-lived token exchange failed: {response.text[:500]}")
            data = response.json()
            if not data.get("access_token"):
                raise HTTPException(502, "Instagram token exchange did not return an access token")
            return data

    async def refresh_long_lived_token(self, access_token: str, config: dict | None = None):
        config = config or {}
        if not config.get("graph_base_url"):
            raise HTTPException(503, "Customer Meta app configuration is missing")
        url = f"{config['graph_base_url'].rstrip('/')}/refresh_access_token"
        params = {"grant_type": "ig_refresh_token", "access_token": access_token}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, params=params)
            if response.status_code >= 400:
                raise HTTPException(502, f"Instagram token refresh failed: {response.text[:500]}")
            data = response.json()
            if not data.get("access_token"):
                raise HTTPException(502, "Instagram token refresh did not return an access token")
            return data

    async def fetch_account(self, access_token: str, config: dict | None = None):
        config = config or {}
        if not config.get("graph_base_url") or not config.get("graph_version"):
            raise HTTPException(503, "Customer Meta app configuration is missing")
        fields = "user_id,username"
        url = f"{config['graph_base_url'].rstrip('/')}/{config['graph_version']}/me"
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, params={"fields": fields, "access_token": access_token})
            if response.status_code >= 400:
                raise HTTPException(502, f"Instagram account lookup failed: {response.text[:500]}")
            return response.json()

    async def save_account(self, client_id: str, account: dict, access_token: str, expires_at: float | None = None):
        from datetime import datetime, timezone
        existing = await db().instagram_accounts.find_one({"instagram_user_id": str(account["user_id"])})
        if existing and existing.get("client_id") != client_id:
            raise HTTPException(409, "This Instagram account is already connected to another Meridin workspace")
        await db().instagram_accounts.update_one(
            {"client_id": client_id, "instagram_user_id": str(account["user_id"])},
            {"$set": {
                "client_id": client_id,
                "instagram_user_id": str(account["user_id"]),
                "username": account.get("username", ""),
                "access_token_encrypted": encrypt_secret(access_token),
                "token_expires_at": expires_at,
                "active": True,
                "updated_at": datetime.now(timezone.utc),
            }, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
