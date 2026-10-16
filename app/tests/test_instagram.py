import hashlib
import hmac
import pytest
from app.services.instagram_service import InstagramService
from app.models.schemas import InstagramAccountCreate

CONFIG = {
    "app_id": "test-app-id",
    "instagram_app_secret": "test-instagram-secret",
    "app_secret": "test-meta-secret",
    "verify_token": "test-verify",
    "graph_base_url": "https://graph.instagram.com",
    "graph_version": "v24.0",
}

def test_signature_rejected_without_secret():
    service = InstagramService()
    assert not service.verify_signature(b"abc", None, None)
    assert not service.verify_signature(b"abc", "sha256=invalid", None)

def test_valid_signature_accepted():
    secret = "test-meta-secret"
    body = b'{"hello":"world"}'
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    service = InstagramService()
    assert service.verify_signature(body, signature, secret)
    assert not service.verify_signature(body, "sha256=" + "0" * 64, secret)

def test_manual_account_payload_accepts_supplied_token():
    payload = InstagramAccountCreate(instagram_user_id="123", username="brand", access_token="manual-token")
    assert payload.instagram_user_id == "123"
    assert payload.access_token == "manual-token"

def test_existing_account_can_submit_blank_token_to_keep_saved_token():
    payload = InstagramAccountCreate(instagram_user_id="123", username="brand", access_token=None)
    assert payload.access_token is None

class _FakeResponse:
    status_code = 200
    text = ""
    def __init__(self, data): self._data = data
    def json(self): return self._data

class _FakeAsyncClient:
    last_request = None
    def __init__(self, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc, tb): return False
    async def post(self, url, **kwargs):
        _FakeAsyncClient.last_request = ("POST", url, kwargs)
        return _FakeResponse({"success": True})

@pytest.mark.asyncio
async def test_manual_token_subscription_uses_me_endpoint(monkeypatch):
    monkeypatch.setattr("app.services.instagram_service.httpx.AsyncClient", _FakeAsyncClient)
    result = await InstagramService().subscribe_messages("ig-user-123", "manual-token", CONFIG)
    method, url, kwargs = _FakeAsyncClient.last_request
    assert method == "POST"
    assert url == "https://graph.instagram.com/v24.0/me/subscribed_apps"
    assert kwargs["data"]["access_token"] == "manual-token"
    assert result["success"] is True

@pytest.mark.asyncio
async def test_send_text_uses_manual_account_token(monkeypatch):
    monkeypatch.setattr("app.services.instagram_service.httpx.AsyncClient", _FakeAsyncClient)
    await InstagramService().send_text("ig-user-123", "manual-token", "recipient-1", "hello", CONFIG)
    method, url, kwargs = _FakeAsyncClient.last_request
    assert method == "POST"
    assert url == "https://graph.instagram.com/v24.0/ig-user-123/messages"
    assert kwargs["json"]["recipient"]["id"] == "recipient-1"
