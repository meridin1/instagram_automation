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


@router.post("/register")
async def register(payload: RegisterRequest):
    """Submit a client application. A client workspace is created only after admin approval."""
    database = db()
    email = _normalize_email(str(payload.email))
    instagram_username = _normalize_instagram_username(payload.instagram_username)

    # Approved accounts cannot re-register; pending requests return a friendly status
    # instead of creating another admin notification/application.
    if await database.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="An account with this email already exists. Please sign in.")
    existing = await database.signup_applications.find_one({"email": email, "status": {"$in": ["pending", "approving"]}})
    if existing:
        return {
            "status": "pending",
            "message": "An application with this email is already pending. Please wait for Meridin admin approval.",
            "email": email,
        }
    if instagram_username and await database.clients.find_one({"instagram_username": instagram_username}):
        raise HTTPException(status_code=409, detail="Instagram username is already registered")

    now = datetime.now(timezone.utc)
    application = {
        "brand_name": payload.resolved_name,
        "email": email,
        "password_hash": hash_password(payload.password),
        "instagram_username": instagram_username,
        "business_information": payload.business_information.strip(),
        "location": payload.location.strip(),
        "delivery_information": payload.delivery_information.strip(),
        "business_hours": payload.business_hours.strip(),
        "language": payload.language.strip() or "English",
        "tone": payload.tone.strip() or "Friendly",
        "automation_enabled": payload.automation_enabled,
        "llm_enabled": payload.llm_enabled,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    }
    try:
        await database.signup_applications.insert_one(application)
    except DuplicateKeyError:
        # Handles two near-simultaneous submissions for the same normalized email.
        existing = await database.signup_applications.find_one({"email": email, "status": {"$in": ["pending", "approving"]}})
        if existing:
            return {
                "status": "pending",
                "message": "An application with this email is already pending. Please wait for Meridin admin approval.",
                "email": email,
            }
        if await database.users.find_one({"email": email}):
            raise HTTPException(status_code=409, detail="An account with this email already exists. Please sign in.")
        raise HTTPException(status_code=409, detail="An application for this email already exists. Please contact Meridin support.")

    return {
        "status": "pending",
        "message": "Your application has been submitted and is waiting for admin approval. You can sign in after it is approved.",
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
