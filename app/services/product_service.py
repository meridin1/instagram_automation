from datetime import datetime, timezone
from bson import ObjectId
from fastapi import HTTPException
from app.database.mongo import db


def now():
    return datetime.now(timezone.utc)


def serialize(doc: dict | None):
    if not doc:
        return None
    out = dict(doc)
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    return out


async def get_product(client_id: str, product_id: str | None):
    if not product_id:
        return None
    try:
        oid = ObjectId(product_id)
    except Exception:
        return None
    return await db().products.find_one({"_id": oid, "client_id": client_id})


async def create_product(client_id: str, data: dict):
    if data.get("sale_price") is not None and data["sale_price"] > data["price"]:
        raise HTTPException(400, "sale_price cannot be greater than price")
    data = dict(data)
    if isinstance(data.get("sku"), str):
        data["sku"] = data["sku"].strip() or None
    data["client_id"] = client_id
    data["created_at"] = now()
    data["updated_at"] = now()
    result = await db().products.insert_one(data)
    return serialize(await db().products.find_one({"_id": result.inserted_id, "client_id": client_id}))


async def update_product(client_id: str, product_id: str, data: dict):
    try:
        oid = ObjectId(product_id)
    except Exception:
        raise HTTPException(400, "Invalid product id")
    clean = {k: v for k, v in data.items() if v is not None}
    current = await db().products.find_one({"_id": oid, "client_id": client_id})
    if not current:
        raise HTTPException(404, "Product not found")
    price = clean.get("price", current["price"])
    sale_price = clean.get("sale_price", current.get("sale_price"))
    if sale_price is not None and sale_price > price:
        raise HTTPException(400, "sale_price cannot be greater than price")
    clean["updated_at"] = now()
    await db().products.update_one({"_id": oid, "client_id": client_id}, {"$set": clean})
    return serialize(await db().products.find_one({"_id": oid, "client_id": client_id}))


async def product_summary(product: dict) -> dict:
    return {
        "id": str(product["_id"]),
        "name": product.get("name", ""),
        "price": product.get("price", 0),
        "sale_price": product.get("sale_price"),
        "category": product.get("category", ""),
        "brand": product.get("brand", ""),
        "description": product.get("description", ""),
        "sizes": product.get("sizes", []),
        "colors": product.get("colors", []),
        "stock": bool(product.get("stock", False)),
        "quantity": int(product.get("quantity", 0)),
        "product_url": product.get("product_url", ""),
        "image_url": product.get("image_url", ""),
        "active": bool(product.get("active", True)),
    }
