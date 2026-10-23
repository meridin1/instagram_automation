from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.core.security import get_client_id
from app.services.knowledge_service import upsert_knowledge, list_knowledge, delete_knowledge

router = APIRouter(prefix="/api/knowledge", tags=["merchant knowledge / RAG"])
class KnowledgeInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=12000)
    category: str = Field(default="faq", max_length=60)
    tags: list[str] = Field(default_factory=list, max_length=30)

@router.get("")
async def get_documents(client_id: str = Depends(get_client_id)):
    return await list_knowledge(client_id)

@router.post("")
async def create_document(payload: KnowledgeInput, client_id: str = Depends(get_client_id)):
    try: return await upsert_knowledge(client_id, **payload.model_dump())
    except ValueError as exc: raise HTTPException(400, str(exc))

@router.put("/{document_id}")
async def update_document(document_id: str, payload: KnowledgeInput, client_id: str = Depends(get_client_id)):
    try: result = await upsert_knowledge(client_id, document_id=document_id, **payload.model_dump())
    except ValueError as exc: raise HTTPException(400, str(exc))
    if not result: raise HTTPException(404, "Knowledge document not found")
    return result

@router.delete("/{document_id}")
async def remove_document(document_id: str, client_id: str = Depends(get_client_id)):
    if not await delete_knowledge(client_id, document_id): raise HTTPException(404, "Knowledge document not found")
    return {"ok": True}
