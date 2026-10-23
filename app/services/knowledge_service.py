"""Tenant-isolated lexical RAG for merchant FAQs and policies.

Documents are stored in MongoDB and retrieved by a transparent token-overlap scorer.
This intentionally avoids requiring a separate vector database or embedding model.
"""
from collections import Counter
from datetime import datetime, timezone
import re
from bson import ObjectId
from app.database.mongo import db


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").casefold())


def _clean(doc: dict) -> dict:
    return {"id": str(doc["_id"]), "title": doc.get("title", ""), "content": doc.get("content", ""),
            "category": doc.get("category", "faq"), "tags": doc.get("tags", []),
            "updated_at": doc.get("updated_at")}

async def upsert_knowledge(client_id: str, *, title: str, content: str, category: str = "faq", tags: list[str] | None = None, document_id: str | None = None):
    title, content = title.strip(), content.strip()
    if not title or not content:
        raise ValueError("title and content are required")
    now = datetime.now(timezone.utc)
    doc = {"client_id": client_id, "title": title[:200], "content": content[:12000], "category": (category or "faq")[:60],
           "tags": [str(x).strip()[:60] for x in (tags or []) if str(x).strip()][:30], "active": True, "updated_at": now}
    if document_id:
        try: oid = ObjectId(document_id)
        except Exception: raise ValueError("Invalid knowledge document id")
        result = await db().knowledge_documents.update_one({"_id": oid, "client_id": client_id}, {"$set": doc})
        if not result.matched_count: return None
        return _clean(await db().knowledge_documents.find_one({"_id": oid, "client_id": client_id}))
    doc["created_at"] = now
    result = await db().knowledge_documents.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _clean(doc)

async def list_knowledge(client_id: str):
    cursor = db().knowledge_documents.find({"client_id": client_id, "active": {"$ne": False}}).sort("updated_at", -1).limit(500)
    return [_clean(x) async for x in cursor]

async def delete_knowledge(client_id: str, document_id: str) -> bool:
    try: oid = ObjectId(document_id)
    except Exception: return False
    result = await db().knowledge_documents.update_one({"_id": oid, "client_id": client_id}, {"$set": {"active": False, "updated_at": datetime.now(timezone.utc)}})
    return result.matched_count > 0

async def retrieve_knowledge(client_id: str, query: str, limit: int = 4) -> list[dict]:
    """Retrieve only this tenant's active docs; no cross-client fallback."""
    q = Counter(_tokens(query))
    if not q: return []
    cursor = db().knowledge_documents.find({"client_id": client_id, "active": {"$ne": False}}).limit(1000)
    scored = []
    async for doc in cursor:
        text = " ".join([doc.get("title", ""), doc.get("content", ""), " ".join(doc.get("tags", [])), doc.get("category", "")])
        d = Counter(_tokens(text))
        overlap = sum(min(count, d[token]) for token, count in q.items())
        title_tokens = set(_tokens(doc.get("title", "")))
        title_bonus = sum(2 for token in q if token in title_tokens)
        phrase_bonus = 3 if query.casefold().strip() and query.casefold().strip() in text.casefold() else 0
        score = overlap + title_bonus + phrase_bonus
        # Relevance is based on query coverage, not normalized against the top result
        # (which would make even a single accidental token match appear perfect).
        relevance = min(1.0, (overlap + (title_bonus * 0.35) + (phrase_bonus * 0.5)) / max(2.0, len(q) * 1.35))
        if score > 0: scored.append((score, relevance, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored: return []
    return [{**_clean(doc), "retrieval_score": round(relevance, 3)} for score, relevance, doc in scored[:max(1, min(limit, 8))]]
