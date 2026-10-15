from fastapi import APIRouter
from app.database.mongo import db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    await db().command("ping")
    return {"status": "ok", "service": "meridin-instagram"}
