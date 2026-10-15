import hashlib
import hmac
import pytest
from app.services.instagram_service import InstagramService

CONFIG = {
    "oauth_client_id": "test-app-id",
    "oauth_client_secret": "test-app-secret",
    "app_secret": "test-app-secret",
    "verify_token": "test-verify",
    "graph_base_url": "https://graph.instagram.com",
    "graph_version": "v24.0",
    "redirect_uri": "https://example.test/api/instagram/oauth/callback",
    "authorize_url": "https://www.instagram.com/oauth/authorize",
    "token_url": "https://api.instagram.com/oauth/access_token",
    "oauth_scopes": ["instagram_business_basic", "instagram_business_manage_messages"],
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


def test_oauth_url_contains_state_and_scopes():
    url = InstagramService().build_oauth_url("state-value", CONFIG)
    assert "state=state-value" in url
    assert "redirect_uri=" in url
    assert "instagram_business_basic" in url
    assert "instagram_business_manage_messages" in url


class _FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _FakeAsyncClient:
    last_request = None

    def __init__(self, **kwargs):
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.request = ("POST", url, kwargs)
        _FakeAsyncClient.last_request = self.request
        return _FakeResponse({"access_token": "test-token", "expires_in": 3600, "success": True})

    async def get(self, url, **kwargs):
        self.request = ("GET", url, kwargs)
        _FakeAsyncClient.last_request = self.request
        return _FakeResponse({"access_token": "long-lived-test-token", "expires_in": 5184000})


@pytest.mark.asyncio
async def test_oauth_code_exchange_uses_database_config(monkeypatch):
    monkeypatch.setattr("app.services.instagram_service.httpx.AsyncClient", _FakeAsyncClient)
    result = await InstagramService().exchange_code("one-time-code", CONFIG)
    method, url, kwargs = _FakeAsyncClient.last_request
    assert method == "POST"
    assert url == "https://api.instagram.com/oauth/access_token"
    assert kwargs["data"]["grant_type"] == "authorization_code"
    assert kwargs["data"]["client_id"] == "test-app-id"
    assert kwargs["data"]["client_secret"] == "test-app-secret"
    assert result["access_token"] == "test-token"


@pytest.mark.asyncio
async def test_instagram_login_subscribes_using_me_endpoint(monkeypatch):
    async def fake_config():
        return CONFIG
    monkeypatch.setattr("app.services.instagram_service.get_meta_config", fake_config)
    monkeypatch.setattr("app.services.instagram_service.httpx.AsyncClient", _FakeAsyncClient)
    result = await InstagramService().subscribe_messages("ig-user-123", "test-token")
    method, url, kwargs = _FakeAsyncClient.last_request
    assert method == "POST"
    assert url == "https://graph.instagram.com/v24.0/me/subscribed_apps"
    assert "messages" in kwargs["data"]["subscribed_fields"]
    assert result["success"] is True


@pytest.mark.asyncio
async def test_send_text_uses_database_graph_config(monkeypatch):
    async def fake_config():
        return CONFIG
    monkeypatch.setattr("app.services.instagram_service.get_meta_config", fake_config)
    monkeypatch.setattr("app.services.instagram_service.httpx.AsyncClient", _FakeAsyncClient)
    await InstagramService().send_text("ig-user-123", "token", "recipient-1", "hello")
    method, url, kwargs = _FakeAsyncClient.last_request
    assert method == "POST"
    assert url == "https://graph.instagram.com/v24.0/ig-user-123/messages"
    assert kwargs["json"]["recipient"]["id"] == "recipient-1"
