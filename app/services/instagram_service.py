import hashlib
import hmac
import httpx
from fastapi import HTTPException


class InstagramService:
    def _url(self, path: str, config: dict) -> str:
        base = config["graph_base_url"].rstrip("/")
        return f"{base}/{config['graph_version']}/{path.lstrip('/')}"

    async def subscribe_messages(self, ig_user_id: str, access_token: str, config: dict | None = None):
        # Instagram API with Instagram Login subscribes the authorized account via /me.
        # ig_user_id is retained in the signature for callers and audit logs, but must not
        # be used as the subscription path for this API flow.
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
