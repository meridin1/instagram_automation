"""Encrypt sensitive third-party tokens before storing them in MongoDB."""
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings


def _fernet():
    configured = (settings.token_encryption_key or "").strip()
    if configured:
        key = configured.encode()
        try:
            Fernet(key)
            return Fernet(key)
        except Exception as exc:
            raise RuntimeError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc
    # Convenient for local development. Production deployments should set a dedicated key.
    derived = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode()).digest())
    return Fernet(derived)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        # Legacy plaintext tokens do not use Fernet's gAAAA prefix. Never silently
        # treat an encrypted token as plaintext if the configured key was changed.
        if value.startswith("gAAAA"):
            raise RuntimeError("Cannot decrypt stored Meta token. TOKEN_ENCRYPTION_KEY must match the key used to encrypt it.")
        return value


def account_access_token(account: dict) -> str:
    encrypted = account.get("access_token_encrypted")
    if encrypted:
        return decrypt_secret(encrypted)
    legacy = account.get("access_token", "")
    if legacy:
        return legacy
    raise RuntimeError("Instagram account token is missing")
