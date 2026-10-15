import json
import logging
import httpx
from bson import ObjectId
from app.core.config import settings
from app.database.mongo import db
from app.services.usage_service import record_llm_usage, llm_limit_reached

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are Meridin's controlled Instagram-commerce understanding engine for clothing businesses.
Interpret customer messages. Never invent catalogue facts.

Return only the requested structured JSON. Supported intents:
greeting, thanks, product_price, product_availability, product_size, product_color,
product_link, product_alternatives, product_search, location_query, delivery_query,
order_request, return_request, exchange_request, human_handoff, unknown.

Entities:
PRODUCT, CATEGORY, BRAND, COLOR, SIZE, PRICE, occasion.

Malayalam script and Malayalam written using English letters (Manglish) are common.
If the message needs catalogue information, select a safe server tool:
search_products, get_product, check_availability, get_business_info, get_delivery_info,
get_customer_context, or handoff_to_human.
The server, not you, is the source of truth for prices, stock, sizes, colours, links,
delivery information and business policy.
"""


class LLMService:
    async def classify(self, text: str, context: dict | None = None, client_id: str | None = None) -> dict | None:
        # Meridin owns the provider/model/API key. Clients never supply their own key.
        if not settings.llm_enabled or not settings.llm_api_key:
            return None
        api_key = settings.llm_api_key
        client = None
        if client_id:
            try:
                client = await db().clients.find_one({"_id": ObjectId(client_id)})
            except Exception:
                return None
            if not client or client.get("active") is False or not client.get("llm_enabled", False):
                return None
            if await llm_limit_reached(client_id, client, {}):
                return None
        if settings.llm_api_style.lower() == "responses":
            result = await self._responses(text, context, api_key)
        else:
            result = await self._chat_completions(text, context, api_key)
        if result and client_id:
            usage = result.pop("_usage", {})
            await record_llm_usage(client_id, usage.get("input_tokens", usage.get("prompt_tokens", 0)), usage.get("output_tokens", usage.get("completion_tokens", 0)), usage.get("model", settings.llm_model))
            if result.pop("_invalid", False):
                return None
        return result

    async def _responses(self, text: str, context: dict | None, api_key: str):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "greeting", "thanks", "product_price", "product_availability",
                        "product_size", "product_color", "product_link", "product_alternatives",
                        "product_search", "location_query", "delivery_query", "order_request",
                        "return_request", "exchange_request", "human_handoff", "unknown"
                    ]
                },
                "entities": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "PRODUCT": {"type": ["string", "null"]},
                        "CATEGORY": {"type": ["string", "null"]},
                        "BRAND": {"type": ["string", "null"]},
                        "COLOR": {"type": ["string", "null"]},
                        "SIZE": {"type": ["string", "null"]},
                        "PRICE": {"type": ["number", "null"]},
                        "occasion": {"type": ["string", "null"]},
                    },
                    "required": ["PRODUCT", "CATEGORY", "BRAND", "COLOR", "SIZE", "PRICE", "occasion"],
                },
                "language": {"type": "string"},
                "confidence": {"type": "number"},
                "tool": {
                    "type": "string",
                    "enum": [
                        "search_products", "get_product", "check_availability",
                        "get_business_info", "get_delivery_info",
                        "get_customer_context", "handoff_to_human", "none"
                    ]
                },
                "tool_args": {"type": "object"},
                "reason": {"type": "string"},
            },
            "required": ["intent", "entities", "language", "confidence", "tool", "tool_args", "reason"],
        }
        payload = {
            "model": settings.llm_model,
            "instructions": SYSTEM_PROMPT,
            "input": json.dumps({"message": text, "context": context or {}}, ensure_ascii=False),
            "temperature": 0,
            "max_output_tokens": settings.llm_max_output_tokens,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "meridin_intent",
                    "description": "Structured intent and safe tool routing for Meridin.",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        return await self._post_and_parse(f"{settings.llm_base_url.rstrip('/')}/responses", payload, api_key)

    async def _chat_completions(self, text: str, context: dict | None, api_key: str):
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({"message": text, "context": context or {}}, ensure_ascii=False)},
            ],
            "temperature": 0,
            "max_tokens": settings.llm_max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        return await self._post_and_parse(f"{settings.llm_base_url.rstrip('/')}/chat/completions", payload, api_key)

    async def _post_and_parse(self, url: str, payload: dict, api_key: str):
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            content = self._extract_text(data)
            if not content:
                return None
            parsed = self._validate(json.loads(content))
            usage = data.get("usage") or {}
            usage_info = {
                "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens", 0)),
                "output_tokens": usage.get("output_tokens", usage.get("completion_tokens", 0)),
                "model": data.get("model", settings.llm_model),
            }
            if parsed:
                parsed["_usage"] = usage_info
                return parsed
            return {"_invalid": True, "_usage": usage_info}
        except Exception as exc:
            logger.exception("LLM request failed: %s", exc)
            return None

    @staticmethod
    def _extract_text(data: dict) -> str | None:
        if "output_text" in data and data["output_text"]:
            return data["output_text"]
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    return content["text"]
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None

    @staticmethod
    def _validate(data: dict) -> dict | None:
        allowed = {
            "greeting", "thanks", "product_price", "product_availability",
            "product_size", "product_color", "product_link", "product_alternatives",
            "product_search", "location_query", "delivery_query", "order_request",
            "return_request", "exchange_request", "human_handoff", "unknown",
        }
        intent = data.get("intent")
        if intent not in allowed:
            return None
        entities = data.get("entities") or {}
        if not isinstance(entities, dict):
            entities = {}
        confidence = float(data.get("confidence", 0))
        tool = data.get("tool", "none")
        allowed_tools = {
            "search_products", "get_product", "check_availability",
            "get_business_info", "get_delivery_info",
            "get_customer_context", "handoff_to_human", "none",
        }
        if tool not in allowed_tools:
            tool = "none"
        return {
            "intent": intent,
            "entities": {k: v for k, v in entities.items() if v not in (None, "", [])},
            "language": str(data.get("language", "Other")),
            "confidence": max(0.0, min(1.0, confidence)),
            "tool": tool,
            "tool_args": data.get("tool_args") if isinstance(data.get("tool_args"), dict) else {},
            "reason": str(data.get("reason", ""))[:300],
        }


llm_service = LLMService()
