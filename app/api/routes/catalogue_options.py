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


# Shared clothing taxonomy and variant option vocabulary. Admin edits are stored centrally
# so every client sees the same managed options.
def _default_catalogue_config():
    import json, re
    from pathlib import Path
    source = Path(__file__).resolve().parents[3] / "frontend" / "client" / "assets" / "clothing-taxonomy.js"
    text = source.read_text(encoding="utf-8")
    result = {}
    for js_name, key in (("MERIDIN_CLOTHING_TAXONOMY", "taxonomy"), ("MERIDIN_VARIANT_PRESETS", "variant_presets")):
        match = re.search(r"window\." + js_name + r"\s*=\s*(\{.*?\});", text, re.S)
        if not match:
            raise HTTPException(500, "Could not load default catalogue configuration")
        result[key] = json.loads(match.group(1))
    return result

@router.get("/api/catalogue-config")
async def get_catalogue_config(client_id: str = Depends(get_client_id)):
    saved = await db().catalogue_config.find_one({"_id": "shared"})
    return {"taxonomy": saved.get("taxonomy"), "variant_presets": saved.get("variant_presets")} if saved else _default_catalogue_config()

class CatalogueConfigUpdate(BaseModel):
    taxonomy: dict
    variant_presets: dict[str, list[str]]

@router.get("/api/admin/catalogue-config")
async def admin_get_catalogue_config(user=Depends(get_admin_user)):
    saved = await db().catalogue_config.find_one({"_id": "shared"})
    return {"taxonomy": saved.get("taxonomy"), "variant_presets": saved.get("variant_presets")} if saved else _default_catalogue_config()

@router.put("/api/admin/catalogue-config")
async def admin_update_catalogue_config(payload: CatalogueConfigUpdate, user=Depends(get_admin_user)):
    import json
    taxonomy = payload.taxonomy
    presets = payload.variant_presets
    if len(json.dumps(taxonomy)) > 500_000 or len(json.dumps(presets)) > 200_000:
        raise HTTPException(413, "Catalogue configuration is too large")
    def validate_tree(node, depth=0):
        if depth > 12:
            raise HTTPException(400, "Category nesting cannot exceed 12 levels")
        if not isinstance(node, dict):
            raise HTTPException(400, "Every category level must be an object")
        for name, child in node.items():
            if not isinstance(name, str) or not name.strip() or len(name) > 100:
                raise HTTPException(400, "Category names must be 1–100 characters")
            if isinstance(child, list):
                if any(not isinstance(v, str) or not v.strip() or len(v) > 100 for v in child):
                    raise HTTPException(400, "Category leaf values must be non-empty strings")
            elif isinstance(child, dict):
                validate_tree(child, depth + 1)
            else:
                raise HTTPException(400, "Category nodes must contain objects or lists")
    validate_tree(taxonomy)
    clean = {}
    for name, values in presets.items():
        label = name.strip() if isinstance(name, str) else ""
        if not label or len(label) > 80 or not isinstance(values, list) or len(values) > 500:
            raise HTTPException(400, "Variant names and values are invalid")
        clean[label] = list(dict.fromkeys(v.strip() for v in values if isinstance(v, str) and v.strip()))
    await db().catalogue_config.update_one({"_id": "shared"}, {"$set": {"taxonomy": taxonomy, "variant_presets": clean, "updated_at": datetime.now(timezone.utc)}}, upsert=True)
    return {"taxonomy": taxonomy, "variant_presets": clean}
