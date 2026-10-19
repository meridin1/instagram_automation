"""Optional CLIP-based image-to-catalogue retrieval.

No image descriptions or LLM calls are used. Product vectors are stored per product
and per tenant in MongoDB; incoming image vectors are compared with cosine similarity.
The heavyweight ML dependencies are imported lazily so text-only deployments stay light.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from io import BytesIO
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.database.mongo import db
from app.services.semantic_search_service import _passes_filters

logger = logging.getLogger(__name__)
_model = None
_processor = None
_torch = None
_model_load_lock = None

META_IMAGE_HOST_SUFFIXES = (
    "cdninstagram.com",
    "fbcdn.net",
    "fbsbx.com",
    "instagram.com",
)


def _public_https_url(url: str, *, meta_only: bool = False) -> bool:
    try:
        parsed = urlparse(str(url or ""))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return False
        host = parsed.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return False
        if meta_only and not any(host == suffix or host.endswith("." + suffix) for suffix in META_IMAGE_HOST_SUFFIXES):
            return False
        # Reject literal private/reserved addresses. DNS answers are checked below too.
        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global:
                return False
        except ValueError:
            pass
        try:
            answers = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
            if not answers:
                return False
            for answer in answers:
                address = ipaddress.ip_address(answer[4][0])
                if not address.is_global:
                    return False
        except (OSError, ValueError):
            return False
        return True
    except Exception:
        return False


async def _download_image(url: str, *, meta_only: bool = False) -> bytes | None:
    """Download a bounded image while rejecting private hosts and unsafe redirects."""
    current = url
    timeout = httpx.Timeout(8.0, connect=4.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(4):
            if not _public_https_url(current, meta_only=meta_only):
                logger.warning("Visual search rejected an unsafe or non-public image URL")
                return None
            try:
                async with client.stream("GET", current, headers={"Accept": "image/*"}) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            return None
                        current = str(response.url.join(location))
                        continue
                    if response.status_code != 200:
                        return None
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if not content_type.startswith("image/"):
                        return None
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            if int(content_length) > settings.visual_image_max_bytes:
                                return None
                        except ValueError:
                            return None
                    chunks = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > settings.visual_image_max_bytes:
                            return None
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    return body or None
            except httpx.HTTPError:
                return None
    return None


def _load_clip():
    global _model, _processor, _torch
    if _model is not None:
        return _model, _processor, _torch
    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor
    except ImportError as exc:
        raise RuntimeError(
            "Visual search is enabled but optional dependencies are missing. Install requirements-vision.txt."
        ) from exc
    model_name = settings.clip_model_name
    _processor = CLIPProcessor.from_pretrained(model_name)
    _model = CLIPModel.from_pretrained(model_name)
    _model.eval()
    _torch = torch
    return _model, _processor, _torch


def _normalise_vector(vector) -> list[float]:
    values = [float(x) for x in vector]
    norm = sum(x * x for x in values) ** 0.5
    if norm <= 0:
        raise ValueError("CLIP produced an empty vector")
    return [x / norm for x in values]


def _encode_image_bytes(image_bytes: bytes) -> list[float]:
    from PIL import Image, UnidentifiedImageError
    model, processor, torch = _load_clip()
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Downloaded attachment is not a valid image") from exc
    inputs = processor(images=image, return_tensors="pt")
    with torch.inference_mode():
        features = model.get_image_features(**inputs)
    vector = features[0].detach().cpu().tolist()
    return _normalise_vector(vector)


async def image_url_embedding(url: str, *, meta_only: bool = False) -> list[float] | None:
    if not settings.visual_search_enabled or not url:
        return None
    try:
        raw = await _download_image(url, meta_only=meta_only)
        if not raw:
            return None
        # CLIP is CPU-bound in many deployments; do not block the async webhook loop.
        return await asyncio.to_thread(_encode_image_bytes, raw)
    except Exception:
        logger.exception("Visual image embedding failed; continuing without visual match")
        return None


async def index_product_image(client_id: str, product: dict) -> dict:
    """Compute/store a product image vector, scoped by client_id."""
    if not settings.visual_search_enabled:
        return {"ok": False, "reason": "visual_search_disabled"}
    product_id = product.get("_id")
    image_url = str(product.get("image_url") or "").strip()
    if not product_id or not image_url:
        if product_id:
            await db().products.update_one(
                {"_id": product_id, "client_id": client_id},
                {"$unset": {"visual_embedding": "", "visual_model": "", "visual_indexed_at": ""}},
            )
        return {"ok": False, "reason": "missing_product_image"}
    vector = await image_url_embedding(image_url)
    if not vector:
        await db().products.update_one(
            {"_id": product_id, "client_id": client_id},
            {"$set": {"visual_index_error": "image_download_or_embedding_failed"}},
        )
        return {"ok": False, "reason": "image_download_or_embedding_failed"}
    from datetime import datetime, timezone
    await db().products.update_one(
        {"_id": product_id, "client_id": client_id},
        {"$set": {
            "visual_embedding": vector,
            "visual_model": settings.clip_model_name,
            "visual_indexed_at": datetime.now(timezone.utc),
        }, "$unset": {"visual_index_error": ""}},
    )
    return {"ok": True, "dimensions": len(vector)}


def cosine_similarity_normalized(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return -1.0
    # Vectors are normalized before storage, so cosine similarity is their dot product.
    return sum(float(a) * float(b) for a, b in zip(left, right))


async def search_by_embedding(
    client_id: str,
    query_vector: list[float],
    entities: dict | None = None,
    limit: int = 5,
) -> list[dict]:
    """Search stored vectors for one tenant; no network/model work in this step."""
    cursor = db().products.find({
        "client_id": client_id,
        "active": {"$ne": False},
        "visual_model": settings.clip_model_name,
        "visual_embedding": {"$exists": True},
    })
    scored = []
    async for product in cursor:
        if not _passes_filters(product, entities or {}):
            continue
        score = cosine_similarity_normalized(query_vector, product.get("visual_embedding") or [])
        if score >= settings.visual_similarity_threshold:
            item = dict(product)
            item["visual_similarity"] = round(float(score), 4)
            scored.append(item)
    scored.sort(key=lambda item: item["visual_similarity"], reverse=True)
    return scored[:max(1, min(int(limit), 20))]


async def search_by_image(
    client_id: str,
    image_url: str,
    entities: dict | None = None,
    limit: int = 5,
    *,
    incoming_meta_url: bool = True,
) -> list[dict]:
    """Convenience wrapper used by tools/tests that do not need parallel fusion."""
    query_vector = await image_url_embedding(image_url, meta_only=incoming_meta_url)
    if not query_vector:
        return []
    return await search_by_embedding(client_id, query_vector, entities, limit)
