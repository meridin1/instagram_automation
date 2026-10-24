"""Cloudflare R2 object storage for product images (S3-compatible API)."""
import asyncio
import logging
import uuid
from urllib.parse import quote

from fastapi import HTTPException, UploadFile
from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _configured() -> bool:
    return all((settings.r2_account_id, settings.r2_access_key_id, settings.r2_secret_access_key,
                settings.r2_bucket_name, settings.r2_public_base_url))


def _upload_bytes(data: bytes, key: str, content_type: str) -> None:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    client.put_object(
        Bucket=settings.r2_bucket_name,
        Key=key,
        Body=data,
        ContentType=content_type,
        CacheControl="public, max-age=31536000, immutable",
    )


async def upload_product_image(client_id: str, file: UploadFile) -> dict:
    if not _configured():
        raise HTTPException(503, "Product image uploads are not configured. Set the Cloudflare R2 environment variables.")
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Unsupported image type. Upload a JPEG, PNG, or WebP image.")
    data = await file.read(settings.product_image_max_bytes + 1)
    if not data:
        raise HTTPException(400, "The uploaded image is empty.")
    if len(data) > settings.product_image_max_bytes:
        raise HTTPException(413, f"Image is too large. Maximum size is {settings.product_image_max_bytes // (1024 * 1024)} MB.")
    # Random object keys prevent filename collisions and avoid storing user-provided path segments.
    key = f"products/{client_id}/{uuid.uuid4().hex}{ALLOWED_TYPES[content_type]}"
    try:
        await asyncio.to_thread(_upload_bytes, data, key, content_type)
    except Exception as exc:
        # Log the original failure without importing botocore in the handler.
        # This still works if boto3/botocore itself is missing from the deployment.
        # Do not log credentials, request headers, or uploaded image bytes.
        try:
            error_text = str(exc).replace(settings.r2_access_key_id or "", "[REDACTED]")
            error_text = error_text.replace(settings.r2_secret_access_key or "", "[REDACTED]")
            logger.error(
                "R2 product image upload failed: exception_type=%s error=%s object_key=%s",
                type(exc).__name__, error_text[:500], key,
            )
        except Exception:
            # Never let diagnostics mask the original upload failure.
            logger.error(
                "R2 product image upload failed and diagnostic formatting failed: exception_type=%s",
                type(exc).__name__,
            )
        raise HTTPException(
            502,
            "Cloudflare R2 could not store the image. Check the Render logs for the R2 error code.",
        ) from exc
    base = settings.r2_public_base_url.rstrip("/")
    return {"url": f"{base}/{quote(key, safe='/')}", "key": key, "content_type": content_type, "size": len(data)}
