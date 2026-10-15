from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from app.database.mongo import db
from app.models.schemas import ClientCreate, BusinessSettingsUpdate, AutomationSettingsUpdate
from app.core.security import get_client_id

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("/me")
async def get_me(client_id: str = Depends(get_client_id)):
    client = await db().clients.find_one({"_id": ObjectId(client_id)})
    if not client:
        raise HTTPException(404, "Client not found")
    client["id"] = str(client.pop("_id"))
    client.pop("access_token", None)
    return client


@router.patch("/me")
async def update_me(payload: ClientCreate, client_id: str = Depends(get_client_id)):
    data = payload.model_dump()
    data["updated_at"] = datetime.now(timezone.utc)
    await db().clients.update_one({"_id": ObjectId(client_id)}, {"$set": data})
    client = await db().clients.find_one({"_id": ObjectId(client_id)})
    client["id"] = str(client.pop("_id"))
    return client


@router.get("/business-settings")
async def get_business_settings(client_id: str = Depends(get_client_id)):
    return await db().business_settings.find_one({"client_id": client_id}, {"_id": 0}) or {}


@router.patch("/business-settings")
async def update_business_settings(payload: BusinessSettingsUpdate, client_id: str = Depends(get_client_id)):
    data = payload.model_dump()
    data["updated_at"] = datetime.now(timezone.utc)
    await db().business_settings.update_one({"client_id": client_id}, {"$set": data, "$setOnInsert": {"client_id": client_id}}, upsert=True)
    await db().clients.update_one({"_id": ObjectId(client_id)}, {"$set": {
        "business_information": data["business_information"],
        "location": data["location"],
        "delivery_information": data["delivery_info"],
        "business_hours": data["business_hours"],
        "language": data["language"],
        "tone": data["tone"],
        "updated_at": data["updated_at"],
    }})
    return {"ok": True}


@router.get("/automation-settings")
async def get_automation_settings(client_id: str = Depends(get_client_id)):
    return await db().automation_settings.find_one({"client_id": client_id}, {"_id": 0}) or {}


@router.patch("/automation-settings")
async def update_automation_settings(payload: AutomationSettingsUpdate, client_id: str = Depends(get_client_id)):
    data = payload.model_dump()
    data["updated_at"] = datetime.now(timezone.utc)
    await db().automation_settings.update_one({"client_id": client_id}, {"$set": data, "$setOnInsert": {"client_id": client_id}}, upsert=True)
    await db().clients.update_one({"_id": ObjectId(client_id)}, {"$set": {
        "automation_enabled": data["automation_enabled"],
        "llm_enabled": data["llm_enabled"],
        "language": data["language"],
        "tone": data["tone"],
        "updated_at": data["updated_at"],
    }})
    return {"ok": True}
