from datetime import datetime, timezone
from app.database.mongo import db
from pymongo.errors import DuplicateKeyError


def now():
    return datetime.now(timezone.utc)


def month_key(at=None):
    at = at or now()
    return at.strftime("%Y-%m")

async def record_message(client_id: str, direction: str, text: str):
    at = now(); month = month_key(at); size = len((text or "").encode("utf-8"))
    field = "messages_in" if direction == "inbound" else "messages_out"
    byte_field = "data_in_bytes" if direction == "inbound" else "data_out_bytes"
    await db().client_usage.update_one(
        {"client_id": client_id, "month": month},
        {"$inc": {field: 1, byte_field: size}, "$set": {"updated_at": at}, "$setOnInsert": {"client_id": client_id, "month": month, "created_at": at}},
        upsert=True,
    )
    await db().client_usage_totals.update_one(
        {"client_id": client_id},
        {"$inc": {field: 1, byte_field: size}, "$set": {"updated_at": at}, "$setOnInsert": {"client_id": client_id, "created_at": at}},
        upsert=True,
    )

async def record_llm_usage(client_id: str, prompt_tokens: int = 0, completion_tokens: int = 0, model: str = ""):
    from app.core.config import settings
    at = now(); month = month_key(at); prompt = max(0, int(prompt_tokens)); completion = max(0, int(completion_tokens)); total = prompt + completion
    # Optional, operator-configured rates; zero means cost is unknown/not configured, not free.
    estimated_cost = (prompt * max(0.0, settings.llm_input_cost_per_million_usd) + completion * max(0.0, settings.llm_output_cost_per_million_usd)) / 1_000_000
    increments = {"llm_requests": 1, "llm_prompt_tokens": prompt, "llm_completion_tokens": completion, "llm_total_tokens": total, "llm_estimated_cost_usd": estimated_cost}
    base = {"updated_at": at, "last_llm_model": model, "llm_cost_rates_configured": bool(settings.llm_input_cost_per_million_usd or settings.llm_output_cost_per_million_usd)}
    await db().client_usage.update_one({"client_id": client_id, "month": month}, {"$inc": increments, "$set": base, "$setOnInsert": {"client_id": client_id, "month": month, "created_at": at}}, upsert=True)
    await db().client_usage_totals.update_one({"client_id": client_id}, {"$inc": increments, "$set": base, "$setOnInsert": {"client_id": client_id, "created_at": at}}, upsert=True)
    await db().llm_usage_events.insert_one({"client_id": client_id, "month": month, "model": model, "prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total, "estimated_cost_usd": estimated_cost, "cost_rates_configured": bool(settings.llm_input_cost_per_million_usd or settings.llm_output_cost_per_million_usd), "created_at": at})

async def get_client_usage(client_id: str):
    month = month_key()
    monthly = await db().client_usage.find_one({"client_id": client_id, "month": month}, {"_id": 0}) or {"client_id": client_id, "month": month}
    total = await db().client_usage_totals.find_one({"client_id": client_id}, {"_id": 0}) or {"client_id": client_id}
    return {"month": month, "monthly": monthly, "lifetime": total}

async def reserve_message_rate(client_id: str, per_minute: int):
    """Atomic per-client minute window; returns False after the configured limit."""
    at = now(); window = at.strftime("%Y-%m-%dT%H:%M")
    limit = max(1, int(per_minute or 60))
    query = {"client_id": client_id, "window": window}
    update = {"$inc": {"count": 1}, "$set": {"updated_at": at}, "$setOnInsert": {"client_id": client_id, "window": window, "created_at": at}}
    try:
        doc = await db().client_rate_windows.find_one_and_update(query, update, upsert=True, return_document=True)
    except DuplicateKeyError:
        # Another worker created this minute bucket concurrently; retry without upsert.
        doc = await db().client_rate_windows.find_one_and_update(query, {"$inc": {"count": 1}, "$set": {"updated_at": at}}, upsert=False, return_document=True)
    return int((doc or {}).get("count", 1)) <= limit

async def llm_limit_reached(client_id: str, client: dict, automation: dict):
    month = month_key()
    limit = int(client.get("monthly_llm_limit", 1000) or 0)
    token_limit = int(client.get("monthly_llm_token_limit", 1000000) or 0)
    current = await db().client_usage.find_one({"client_id": client_id, "month": month}) or {}
    requests = int(current.get("llm_requests", 0))
    tokens = int(current.get("llm_total_tokens", 0))
    return (limit > 0 and requests >= limit) or (token_limit > 0 and tokens >= token_limit)

async def data_limit_reached(client_id: str, client: dict):
    limit_mb = int(client.get("monthly_data_limit_mb", 1024) or 0)
    if limit_mb <= 0:
        return False
    current = await db().client_usage.find_one({"client_id": client_id, "month": month_key()}) or {}
    used = int(current.get("data_in_bytes", 0)) + int(current.get("data_out_bytes", 0))
    return used >= limit_mb * 1024 * 1024
