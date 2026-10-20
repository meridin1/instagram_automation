"""Shared catalogue vocabulary managed by platform admins and consumed by client forms."""
from datetime import datetime, timezone
from typing import Literal, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from app.core.security import get_admin_user, get_client_id
from app.database.mongo import db

router = APIRouter(tags=["catalogue options"])
OptionType = Literal["department", "category", "subcategory", "product_type", "target_gender", "color", "size"]

class OptionCreate(BaseModel):
    type: OptionType
    value: str = Field(min_length=1, max_length=80)
    parent: Optional[str] = Field(default=None, max_length=80)
    active: bool = True

    @field_validator("value")
    @classmethod
    def trim_value(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Option value cannot be blank")
        return value

    @field_validator("parent")
    @classmethod
    def trim_parent(cls, value):
        return value.strip() if value and value.strip() else None


def _serialize(doc):
    if not doc:
        return None
    item = dict(doc)
    item["id"] = str(item.pop("_id"))
    return item

@router.get("/api/catalogue-options")
async def list_options(client_id: str = Depends(get_client_id)):
    """Authenticated client endpoint. Options are platform-wide, not tenant-specific."""
    cursor = db().catalogue_options.find({"active": {"$ne": False}}).sort([("type", 1), ("value", 1)])
    items = [_serialize(x) async for x in cursor]
    grouped = {kind: [] for kind in ("department", "category", "subcategory", "product_type", "target_gender", "color", "size")}
    for item in items:
        grouped.setdefault(item["type"], []).append(item)
    return grouped

@router.get("/api/admin/catalogue-options")
async def admin_list_options(user=Depends(get_admin_user)):
    cursor = db().catalogue_options.find({}).sort([("type", 1), ("value", 1)])
    return [_serialize(x) async for x in cursor]

@router.post("/api/admin/catalogue-options", status_code=201)
async def create_option(payload: OptionCreate, user=Depends(get_admin_user)):
    database = db()
    value = payload.value.strip()
    query = {"type": payload.type, "value_key": value.casefold(), "active": {"$ne": False}}
    if await database.catalogue_options.find_one(query):
        raise HTTPException(409, f"An active {payload.type.replace('_', ' ')} named '{value}' already exists")
    now = datetime.now(timezone.utc)
    doc = {"type": payload.type, "value": value, "value_key": value.casefold(), "parent": payload.parent, "active": payload.active, "created_at": now, "updated_at": now}
    result = await database.catalogue_options.insert_one(doc)
    return _serialize(await database.catalogue_options.find_one({"_id": result.inserted_id}))

@router.patch("/api/admin/catalogue-options/{option_id}")
async def update_option(option_id: str, payload: OptionCreate, user=Depends(get_admin_user)):
    try:
        oid = ObjectId(option_id)
    except Exception as exc:
        raise HTTPException(400, "Invalid option id") from exc
    database = db()
    current = await database.catalogue_options.find_one({"_id": oid})
    if not current:
        raise HTTPException(404, "Catalogue option not found")
    value = payload.value.strip()
    duplicate = await database.catalogue_options.find_one({"_id": {"$ne": oid}, "type": payload.type, "value_key": value.casefold(), "active": {"$ne": False}})
    if duplicate:
        raise HTTPException(409, f"An active {payload.type.replace('_', ' ')} named '{value}' already exists")
    await database.catalogue_options.update_one({"_id": oid}, {"$set": {"type": payload.type, "value": value, "value_key": value.casefold(), "parent": payload.parent, "active": payload.active, "updated_at": datetime.now(timezone.utc)}})
    return _serialize(await database.catalogue_options.find_one({"_id": oid}))

@router.delete("/api/admin/catalogue-options/{option_id}")
async def deactivate_option(option_id: str, user=Depends(get_admin_user)):
    try:
        oid = ObjectId(option_id)
    except Exception as exc:
        raise HTTPException(400, "Invalid option id") from exc
    result = await db().catalogue_options.update_one({"_id": oid}, {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}})
    if not result.matched_count:
        raise HTTPException(404, "Catalogue option not found")
    return {"ok": True, "active": False, "id": option_id}
