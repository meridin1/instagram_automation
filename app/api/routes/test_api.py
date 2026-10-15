from fastapi import APIRouter, Depends
from app.core.security import get_client_id
from app.models.schemas import TestInbound
from app.services.conversation_service import process_inbound

router = APIRouter(prefix="/api/test", tags=["development"])


@router.post("/inbound")
async def inbound(payload: TestInbound, client_id: str = Depends(get_client_id)):
    return await process_inbound(
        client_id=client_id,
        sender_id=payload.sender_id,
        text=payload.text,
        product_id=payload.product_id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        send_to_instagram=False,
    )
