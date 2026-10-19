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
    product = await db().products.find_one({"_id": ObjectId(doc["id"]), "client_id": client_id})
    try:
        await reindex_product(client_id, product)
        from app.services.visual_search_service import index_product_image
        await index_product_image(client_id, product)
    except Exception:
        # Product creation must still succeed if optional CLIP/model hosting is unavailable.
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


@router.post("/visual-reindex")
async def visual_reindex(client_id: str = Depends(get_client_id)):
    """Precompute CLIP vectors for this client's active catalogue images."""
    from app.core.config import settings
    if not settings.visual_search_enabled:
        raise HTTPException(409, "Visual search is disabled. Set VISUAL_SEARCH_ENABLED=true and install requirements-vision.txt.")
    from app.services.visual_search_service import index_product_image
    cursor = db().products.find({"client_id": client_id, "active": {"$ne": False}})
    indexed = 0
    failed = 0
    async for product in cursor:
        try:
            result = await index_product_image(client_id, product)
            if result.get("ok"):
                indexed += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    return {"ok": failed == 0, "indexed": indexed, "failed": failed, "model": settings.clip_model_name}


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
    product = await db().products.find_one({"_id": ObjectId(product_id), "client_id": client_id})
    await reindex_product(client_id, product)
    try:
        from app.services.visual_search_service import index_product_image
        await index_product_image(client_id, product)
    except Exception:
        pass
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
