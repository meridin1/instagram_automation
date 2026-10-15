from collections import Counter
import re
from app.database.mongo import db


def _text(product: dict) -> str:
    return " ".join(
        str(x) for x in [
            product.get("name", ""),
            product.get("category", ""),
            product.get("brand", ""),
            product.get("description", ""),
            " ".join(product.get("colors", []) or []),
            " ".join(product.get("sizes", []) or []),
            product.get("sku", ""),
        ] if x
    )


def _tokens(value: str) -> list[str]:
    # Keep alphanumeric tokens; useful for English and numbers like XL/1299.
    return re.findall(r"[a-z0-9]+", (value or "").lower())


async def reindex_product(client_id: str, product: dict | None):
    """Compatibility endpoint: keyword search needs no stored vector/index."""
    if not product or not product.get("_id"):
        return {"ok": False, "reason": "product_not_found"}
    # Remove obsolete vectors written by the former embedding implementation.
    await db().products.update_one(
        {"_id": product["_id"], "client_id": client_id},
        {"$unset": {"embedding": ""}},
    )
    return {"ok": True, "mode": "keyword"}


async def reindex_client(client_id: str) -> int:
    cursor = db().products.find({"client_id": client_id, "active": True})
    count = 0
    async for product in cursor:
        await reindex_product(client_id, product)
        count += 1
    return count


def _passes_filters(product: dict, entities: dict) -> bool:
    color = str(entities.get("COLOR", "")).strip().lower()
    size = str(entities.get("SIZE", "")).strip().upper()
    max_price = entities.get("PRICE")
    if color and color not in [str(x).lower() for x in (product.get("colors", []) or [])]:
        return False
    if size and size not in [str(x).upper() for x in (product.get("sizes", []) or [])]:
        return False
    if max_price is not None:
        try:
            price = float(product.get("sale_price") or product.get("price", 0) or 0)
            if price > float(max_price):
                return False
        except (TypeError, ValueError):
            return False
    if product.get("active") is False:
        return False
    return True


async def search_products(
    client_id: str,
    query: str,
    entities: dict | None = None,
    limit: int = 5,
    exclude_product_id: str | None = None,
):
    """Tenant-scoped catalogue search using weighted lexical matching."""
    entities = entities or {}
    docs = []
    cursor = db().products.find({"client_id": client_id, "active": True})
    async for product in cursor:
        if exclude_product_id and str(product.get("_id")) == str(exclude_product_id):
            continue
        if _passes_filters(product, entities):
            docs.append(product)

    if not docs:
        return []

    query_tokens = _tokens(query)
    if not query_tokens:
        return docs[:max(1, min(int(limit), 50))]
    q_counter = Counter(query_tokens)
    scored = []
    query_lower = (query or "").strip().lower()
    for product in docs:
        product_text = _text(product).lower()
        p_counter = Counter(_tokens(product_text))
        overlap = sum(min(count, p_counter[token]) for token, count in q_counter.items())
        # Product name matches are more valuable than descriptions/categories.
        name_tokens = set(_tokens(str(product.get("name", ""))))
        name_overlap = sum(1 for token in q_counter if token in name_tokens)
        phrase_bonus = 4 if query_lower and query_lower in product_text else 0
        score = overlap + (name_overlap * 2) + phrase_bonus
        # A query consisting only of filters can legitimately match any filtered product.
        scored.append((score, product))

    scored.sort(key=lambda item: item[0], reverse=True)
    max_results = max(1, min(int(limit), 50))
    matched = [product for score, product in scored if score > 0]
    # If entities filter the catalogue and all products have score zero, return filtered matches.
    if not matched and entities:
        matched = [product for _, product in scored]
    return matched[:max_results]
