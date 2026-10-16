from datetime import datetime, timezone
from pydantic import BaseModel
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError
from app.core.security import get_admin_user, hash_password
from app.database.mongo import db
from app.models.schemas import AdminClientCreate, AdminClientUpdate

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _now(): return datetime.now(timezone.utc)

def _client(doc):
    if not doc: return None
    out = dict(doc); out["id"] = str(out.pop("_id"))
    out.pop("llm_api_key_encrypted", None); out.pop("llm_api_key", None); out.pop("access_token", None)
    return out

@router.get("/me")
async def admin_me(user=Depends(get_admin_user)):
    return user

@router.get("/stats")
async def stats(user=Depends(get_admin_user)):
    database = db()
    llm_month = await database.client_usage.aggregate([{"$match":{"month":datetime.now(timezone.utc).strftime("%Y-%m")}}, {"$group":{"_id":None,"n":{"$sum":"$llm_requests"},"tokens":{"$sum":"$llm_total_tokens"},"bytes":{"$sum":{"$add":["$data_in_bytes","$data_out_bytes"]}}}}]).to_list(1)
    usage = llm_month[0] if llm_month else {}
    return {
        "clients": await database.clients.count_documents({"is_system": {"$ne": True}}),
        "active_clients": await database.clients.count_documents({"is_system": {"$ne": True}, "active": {"$ne": False}}),
        "disabled_clients": await database.clients.count_documents({"is_system": {"$ne": True}, "active": False}),
        "users": await database.users.count_documents({}),
        "products": await database.products.count_documents({}),
        "conversations": await database.conversations.count_documents({}),
        "messages": await database.messages.count_documents({}),
        "instagram_accounts": await database.instagram_accounts.count_documents({"active": True}),
        "llm_requests_this_month": usage.get("n", 0),
        "llm_tokens_this_month": usage.get("tokens", 0),
        "data_bytes_this_month": usage.get("bytes", 0),
    }

@router.get("/clients")
async def list_clients(user=Depends(get_admin_user)):
    cursor = db().clients.find({"is_system": {"$ne": True}}).sort("created_at", -1)
    result=[]
    async for c in cursor:
        item=_client(c)
        item.pop("access_token", None)
        users=[]
        uc=db().users.find({"client_id": item["id"]}, {"password_hash":0})
        async for u in uc:
            u["id"]=str(u.pop("_id")); users.append(u)
        item["users"]=users
        item.pop("llm_api_key_encrypted", None)
        item.pop("llm_api_key", None)
        usage_month = datetime.now(timezone.utc).strftime("%Y-%m")
        item["usage_monthly"] = await db().client_usage.find_one({"client_id": item["id"], "month": usage_month}, {"_id": 0}) or {"month": usage_month}
        item["usage_lifetime"] = await db().client_usage_totals.find_one({"client_id": item["id"]}, {"_id": 0}) or {}
        item["instagram_connected"]=await db().instagram_accounts.count_documents({"client_id":item["id"],"active":True})>0
        result.append(item)
    return result


@router.get("/usage")
async def usage_report(user=Depends(get_admin_user)):
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    clients = await list_clients(user)
    rows = []
    for c in clients:
        monthly = c.get("usage_monthly", {})
        lifetime = c.get("usage_lifetime", {})
        rows.append({
            "client_id": c["id"], "brand_name": c.get("name", ""),
            "email": (c.get("users") or [{}])[0].get("email", ""),
            "month": month,
            "monthly_llm_requests": int(monthly.get("llm_requests", 0)),
            "monthly_llm_tokens": int(monthly.get("llm_total_tokens", 0)),
            "monthly_data_bytes": int(monthly.get("data_in_bytes", 0)) + int(monthly.get("data_out_bytes", 0)),
            "monthly_messages": int(monthly.get("messages_in", 0)) + int(monthly.get("messages_out", 0)),
            "total_llm_requests": int(lifetime.get("llm_requests", 0)),
            "total_llm_tokens": int(lifetime.get("llm_total_tokens", 0)),
            "total_data_bytes": int(lifetime.get("data_in_bytes", 0)) + int(lifetime.get("data_out_bytes", 0)),
            "total_messages": int(lifetime.get("messages_in", 0)) + int(lifetime.get("messages_out", 0)),
            "rate_limit_per_minute": int(c.get("rate_limit_per_minute", 60)),
            "monthly_llm_limit": int(c.get("monthly_llm_limit", 1000)),
            "monthly_llm_token_limit": int(c.get("monthly_llm_token_limit", 1000000)),
            "monthly_data_limit_mb": int(c.get("monthly_data_limit_mb", 1024)),
            "llm_enabled": bool(c.get("llm_enabled", False)),
            "active": c.get("active", True) is not False,
        })
    return {"month": month, "clients": rows}

@router.post("/clients", status_code=201)
async def create_client(payload: AdminClientCreate, user=Depends(get_admin_user)):
    database=db(); now=_now(); email=payload.email.strip().lower(); username=(payload.instagram_username or "").strip().lstrip("@").lower() or None
    if await database.users.find_one({"email":email}): raise HTTPException(409,"Email already registered")
    if username and await database.clients.find_one({"instagram_username":username}): raise HTTPException(409,"Instagram username already registered")
    client={"name":payload.brand_name.strip(),"instagram_username":username,"business_information":payload.business_information,"location":payload.location,"delivery_information":payload.delivery_information,"business_hours":payload.business_hours,"language":payload.language,"tone":payload.tone,"automation_enabled":payload.automation_enabled,"llm_enabled":payload.llm_enabled,"rate_limit_per_minute":payload.rate_limit_per_minute,"monthly_llm_limit":payload.monthly_llm_limit,"monthly_llm_token_limit":payload.monthly_llm_token_limit,"monthly_data_limit_mb":payload.monthly_data_limit_mb,"active":True,"created_at":now,"updated_at":now}
    try:
        cr=await database.clients.insert_one(client); cid=str(cr.inserted_id)
        await database.users.insert_one({"client_id":cid,"email":email,"password_hash":hash_password(payload.password),"role":"owner","active":True,"created_at":now,"updated_at":now})
        await database.business_settings.update_one({"client_id":cid},{"$set":{"client_id":cid,"business_information":payload.business_information,"location":payload.location,"delivery_info":payload.delivery_information,"business_hours":payload.business_hours,"contact":"","language":payload.language,"tone":payload.tone,"updated_at":now},"$setOnInsert":{"created_at":now}},upsert=True)
        await database.automation_settings.update_one({"client_id":cid},{"$set":{"client_id":cid,"automation_enabled":payload.automation_enabled,"llm_enabled":payload.llm_enabled,"language":payload.language,"tone":payload.tone,"human_handoff_on_unknown":True,"low_confidence_threshold":.55,"updated_at":now},"$setOnInsert":{"created_at":now}},upsert=True)
    except DuplicateKeyError as exc: raise HTTPException(409,"Email or Instagram username already registered") from exc
    return {"ok":True,"client_id":cid,"email":email}

@router.patch("/clients/{client_id}")
async def update_client(client_id:str,payload:AdminClientUpdate,user=Depends(get_admin_user)):
    try: oid=ObjectId(client_id)
    except Exception: raise HTTPException(400,"Invalid client id")
    current=await db().clients.find_one({"_id":oid})
    if not current: raise HTTPException(404,"Client not found")
    data=payload.model_dump(exclude_unset=True)
    if "brand_name" in data:
        data["name"] = data.pop("brand_name")
    if "instagram_username" in data: data["instagram_username"]=(data["instagram_username"] or "").strip().lstrip("@").lower() or None
    if "email" in data:
        email=data.pop("email").strip().lower()
        await db().users.update_one({"client_id":client_id,"role":"owner"},{"$set":{"email":email,"updated_at":_now()}})
    if "password" in data:
        pw=data.pop("password")
        if pw: await db().users.update_one({"client_id":client_id,"role":"owner"},{"$set":{"password_hash":hash_password(pw),"updated_at":_now()}})
    data["updated_at"]=_now()
    if data: await db().clients.update_one({"_id":oid},{"$set":data})
    sync_fields = {k: data[k] for k in ("automation_enabled", "llm_enabled", "language", "tone") if k in data}
    if sync_fields:
        sync_fields["updated_at"] = _now()
        await db().automation_settings.update_one({"client_id": client_id}, {"$set": sync_fields}, upsert=True)
    return _client(await db().clients.find_one({"_id":oid}))

@router.post("/clients/{client_id}/disable")
async def disable_client(client_id:str,user=Depends(get_admin_user)):
    return await _set_client_active(client_id,False)

@router.post("/clients/{client_id}/enable")
async def enable_client(client_id:str,user=Depends(get_admin_user)):
    return await _set_client_active(client_id,True)

async def _set_client_active(client_id, active):
    try: oid=ObjectId(client_id)
    except Exception: raise HTTPException(400,"Invalid client id")
    r=await db().clients.update_one({"_id":oid},{"$set":{"active":active,"updated_at":_now()}})
    if not r.matched_count: raise HTTPException(404,"Client not found")
    await db().users.update_many({"client_id":client_id},{"$set":{"active":active,"updated_at":_now()}})
    if not active: await db().conversations.update_many({"client_id":client_id},{"$set":{"automation_enabled":False,"status":"human"}})
    return {"ok":True,"active":active,"client_id":client_id}

@router.delete("/clients/{client_id}")
async def delete_client(client_id:str,user=Depends(get_admin_user)):
    try: oid=ObjectId(client_id)
    except Exception: raise HTTPException(400,"Invalid client id")
    client=await db().clients.find_one({"_id":oid})
    if not client: raise HTTPException(404,"Client not found")
    for collection in ["users","products","conversations","messages","instagram_accounts","product_mappings","business_settings","automation_settings","client_usage","client_usage_totals","client_rate_windows","llm_usage_events"]:
        await db()[collection].delete_many({"client_id":client_id})
    await db().clients.delete_one({"_id":oid})
    return {"ok":True,"deleted_client_id":client_id}
