from fastapi import APIRouter, Depends
from app.core.security import get_client_id
from app.models.schemas import ProductSearchRequest
from app.services.semantic_search_service import search_products, reindex_client
from app.services.product_service import serialize

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("/products")
async def search(payload: ProductSearchRequest, client_id: str = Depends(get_client_id)):
    results = await search_products(client_id, payload.query, payload.entities, payload.limit, payload.exclude_product_id)
    return [serialize(x) for x in results]


@router.post("/reindex")
async def reindex(client_id: str = Depends(get_client_id)):
    count = await reindex_client(client_id)
    return {"ok": True, "reindexed": count}
