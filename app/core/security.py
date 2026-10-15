from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings
from app.database.mongo import db
from bson import ObjectId

_password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def hash_password(password: str) -> str:
    return _password_hash.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)

def create_access_token(user_id: str, client_id: str, role: str = "owner") -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "client_id": client_id, "role": role, "exp": expires}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    client_id = payload.get("client_id")
    if not user_id or not client_id:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    try:
        user = await db().users.find_one({"_id": ObjectId(user_id), "client_id": client_id, "$or": [{"active": True}, {"is_active": True}]})
        client = await db().clients.find_one({"_id": ObjectId(client_id)})
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid user identity") from exc
    if not user or not client:
        raise HTTPException(status_code=401, detail="User not found or disabled")
    if client.get("active", True) is False and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Client account is disabled")
    user["id"] = str(user.pop("_id"))
    user.pop("password_hash", None)
    return user

async def get_client_id(current_user: dict = Depends(get_current_user)) -> str:
    return current_user["client_id"]

async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
