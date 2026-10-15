from datetime import datetime, timezone
from app.core.config import settings
from app.core.security import hash_password
from app.database.mongo import db

async def ensure_admin():
    if not settings.admin_email or not settings.admin_password:
        return
    email=settings.admin_email.strip().lower()
    existing=await db().users.find_one({"email":email})
    now=datetime.now(timezone.utc)
    if existing:
        updates={"role":"admin","active":True,"updated_at":now}
        if settings.admin_password:
            updates["password_hash"]=hash_password(settings.admin_password)
        await db().users.update_one({"_id":existing["_id"]},{"$set":updates})
        return
    result=await db().clients.insert_one({"name":"Meridin Admin","active":True,"is_system":True,"created_at":now,"updated_at":now})
    await db().users.insert_one({"client_id":str(result.inserted_id),"email":email,"password_hash":hash_password(settings.admin_password),"role":"admin","active":True,"created_at":now,"updated_at":now})
