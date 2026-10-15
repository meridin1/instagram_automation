from bson import ObjectId
from app.database.mongo import db
from app.services.embedding_service import embed


def _text(product: dict) -> str:
    return " ".join(
        str(x) for x in [
            product.get("name", ""),
            product.get("category", ""),
            product.get("brand", ""),
            product.get("description", ""),
            " ".join(product.get("colors", [])),
            " ".join(product.get("sizes", [])),
        ] if x
    )


async def reindex_product(client_id: str, product: dict):
    vector = embed(_text(product))
    await db().products.update_one(
        {"_id": product["_id"], "client_id": client_id},
        {"$set": {"embedding": vector}},
    )


async def reindex_client(client_id: str) -> int:
    cursor = db().products.find({"client_id": client_id, "active": True})
    count = 0
    async for product in cursor:
        await reindex_product(client_id, product)
        count += 1
    return count


def _passes_filters(product: dict, entities: dict) -> bool:
    color = str(entities.get("COLOR", "")).lower()
    size = str(entities.get("SIZE", "")).upper()
    max_price = entities.get("PRICE")
    if color and color not in [str(x).lower() for x in product.get("colors", [])]:
        return False
    if size and size not in [str(x).upper() for x in product.get("sizes", [])]:
        return False
    if max_price is not None:
        price = product.get("sale_price") or product.get("price", 0)
        if price > float(max_price):
            return False
    if product.get("active") is False:
        return False
    return True


async def search_products(client_id: str, query: str, entities: dict | None = None, limit: int = 5, exclude_product_id: str | None = None):
    entities = entities or {}
    docs = []
    cursor = db().products.find({"client_id": client_id, "active": True})
    async for p in cursor:
        if exclude_product_id and str(p["_id"]) == str(exclude_product_id):
            continue
        if _passes_filters(p, entities):
            docs.append(p)

    if not docs:
        return []

    try:
        import numpy as np
        q = np.asarray(embed(query), dtype=np.float32)
        scored = []
        for p in docs:
            vector = p.get("embedding")
            if vector:
                v = np.asarray(vector, dtype=np.float32)
                score = float(np.dot(q, v))
            else:
                score = 0.0
            scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]
    except Exception:
        # Keyword fallback keeps the catalogue usable if the embedding model is unavailable.
        terms = [t for t in query.lower().split() if len(t) > 2]
        scored = []
        for p in docs:
            hay = _text(p).lower()
            score = sum(1 for t in terms if t in hay)
            scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:limit]]
