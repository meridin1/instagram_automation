from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pymongo.errors import DuplicateKeyError

from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database.mongo import db
from app.models.schemas import RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_instagram_username(username: str | None) -> str | None:
    if not username:
        return None
    value = username.strip().lstrip("@").lower()
    return value or None


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest):
    database = db()
    email = _normalize_email(str(payload.email))
    instagram_username = _normalize_instagram_username(payload.instagram_username)

    if await database.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Email already registered")

    if instagram_username and await database.clients.find_one({"instagram_username": instagram_username}):
        raise HTTPException(status_code=409, detail="Instagram username already registered")

    now = datetime.now(timezone.utc)
    client_doc = {
        "name": payload.resolved_name,
        "instagram_username": instagram_username,
        "business_information": payload.business_information.strip(),
        "location": payload.location.strip(),
        "delivery_information": payload.delivery_information.strip(),
        "business_hours": payload.business_hours.strip(),
        "language": payload.language.strip() or "English",
        "tone": payload.tone.strip() or "Friendly",
        "automation_enabled": payload.automation_enabled,
        "llm_enabled": payload.llm_enabled,
        "rate_limit_per_minute": 60,
        "monthly_llm_limit": 1000,
        "monthly_llm_token_limit": 1000000,
        "monthly_data_limit_mb": 1024,
        "active": True,
        "created_at": now,
        "updated_at": now,
    }

    client_id = None
    client_object_id = None
    user_object_id = None
    try:
        client_result = await database.clients.insert_one(client_doc)
        client_object_id = client_result.inserted_id
        client_id = str(client_object_id)

        user_doc = {
            "client_id": client_id,
            "email": email,
            "password_hash": hash_password(payload.password),
            "role": "owner",
            "active": True,
            "created_at": now,
            "updated_at": now,
        }
        user_result = await database.users.insert_one(user_doc)
        user_object_id = user_result.inserted_id

        await database.business_settings.update_one(
            {"client_id": client_id},
            {"$set": {
                "client_id": client_id,
                "business_information": payload.business_information.strip(),
                "location": payload.location.strip(),
                "delivery_info": payload.delivery_information.strip(),
                "business_hours": payload.business_hours.strip(),
                "contact": "",
                "language": payload.language.strip() or "English",
                "tone": payload.tone.strip() or "Friendly",
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

        await database.automation_settings.update_one(
            {"client_id": client_id},
            {"$set": {
                "client_id": client_id,
                "automation_enabled": payload.automation_enabled,
                "llm_enabled": payload.llm_enabled,
                "language": payload.language.strip() or "English",
                "tone": payload.tone.strip() or "Friendly",
                "human_handoff_on_unknown": True,
                "low_confidence_threshold": 0.55,
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    except DuplicateKeyError as exc:
        if user_object_id:
            await database.users.delete_one({"_id": user_object_id})
        if client_object_id:
            await database.clients.delete_one({"_id": client_object_id})
        if client_id:
            await database.business_settings.delete_one({"client_id": client_id})
            await database.automation_settings.delete_one({"client_id": client_id})
        raise HTTPException(status_code=409, detail="Email or Instagram username is already registered") from exc
    except Exception:
        if user_object_id:
            await database.users.delete_one({"_id": user_object_id})
        if client_object_id:
            await database.clients.delete_one({"_id": client_object_id})
        if client_id:
            await database.business_settings.delete_one({"client_id": client_id})
            await database.automation_settings.delete_one({"client_id": client_id})
        raise

    access_token = create_access_token(str(user_result.inserted_id), client_id, "owner")
    return {
        "message": "Client registered successfully.",
        "access_token": access_token,
        "token_type": "bearer",
        "client_id": client_id,
        "email": email,
    }


@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    database = db()
    email = _normalize_email(form_data.username)
    user = await database.users.find_one({"email": email})

    if not user or not user.get("active", user.get("is_active", True)):
        raise HTTPException(status_code=401, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"})

    password_hash = user.get("password_hash")
    if not password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"})

    try:
        valid = verify_password(form_data.password, password_hash)
    except Exception:
        valid = False

    if not valid:
        raise HTTPException(status_code=401, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"})

    client_id = str(user["client_id"])
    access_token = create_access_token(str(user["_id"]), client_id, user.get("role", "owner"))
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "client_id": client_id,
    }


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user
