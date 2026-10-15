from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from app.database.mongo import db
from app.models.schemas import ProductCreate, ProductUpdate
from app.core.security import get_client_id
from app.services.product_service import create_product, update_product, serialize
from app.services.semantic_search_service import reindex_product

router = APIRouter(prefix="/api/products", tags=["catalogue"])


@router.post("")
async def create(payload: ProductCreate, client_id: str = Depends(get_client_id)):
    doc = await create_product(client_id, payload.model_dump())
    try:
        await reindex_product(client_id, await db().products.find_one({"_id": ObjectId(doc["id"]), "client_id": client_id}))
    except Exception:
        pass
    return doc


@router.get("")
async def list_products(
    q: str = "",
    category: str = "",
    active: bool | None = None,
    in_stock: bool | None = None,
    client_id: str = Depends(get_client_id),
):
    query = {"client_id": client_id}
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"sku": {"$regex": q, "$options": "i"}},
            {"category": {"$regex": q, "$options": "i"}},
            {"brand": {"$regex": q, "$options": "i"}},
        ]
    if category:
        query["category"] = category
    if active is not None:
        query["active"] = active
    if in_stock is not None:
        query["stock"] = in_stock
        if in_stock:
            query["quantity"] = {"$gt": 0}
    cursor = db().products.find(query).sort("created_at", -1).limit(500)
    return [serialize(x) async for x in cursor]


@router.get("/{product_id}")
async def get(product_id: str, client_id: str = Depends(get_client_id)):
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(400, "Invalid product id")
    product = await db().products.find_one({"_id": oid, "client_id": client_id})
    if not product:
        raise HTTPException(404, "Product not found")
    return serialize(product)


@router.patch("/{product_id}")
async def update(product_id: str, payload: ProductUpdate, client_id: str = Depends(get_client_id)):
    doc = await update_product(client_id, product_id, payload.model_dump(exclude_unset=True))
    await reindex_product(client_id, await db().products.find_one({"_id": ObjectId(product_id), "client_id": client_id}))
    return doc


@router.delete("/{product_id}")
async def deactivate(product_id: str, client_id: str = Depends(get_client_id)):
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(400, "Invalid product id")
    result = await db().products.update_one({"_id": oid, "client_id": client_id}, {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}})
    if result.matched_count == 0:
        raise HTTPException(404, "Product not found")
    return {"ok": True, "active": False}


@router.post("/{product_id}/reindex")
async def reindex(product_id: str, client_id: str = Depends(get_client_id)):
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(400, "Invalid product id")
    product = await db().products.find_one({"_id": oid, "client_id": client_id})
    if not product:
        raise HTTPException(404, "Product not found")
    await reindex_product(client_id, product)
    return {"ok": True}
