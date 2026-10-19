"""Tier 2 structured intent/entity interpreter.

Uses an OpenAI-compatible API endpoint. To run a fine-tuned Llama model, configure
LLM_BASE_URL, LLM_API_STYLE=chat_completions, and LLM_MODEL to your hosted model ID.
The model itself is hosted separately; this application does not bundle Llama weights.
"""
import json
import logging
import httpx
from bson import ObjectId
from app.core.config import settings
from app.database.mongo import db
from app.services.usage_service import record_llm_usage, llm_limit_reached
from app.services.intent import INTENTS, canonical_intent

logger = logging.getLogger(__name__)

ENTITY_KEYS = ["PRODUCT", "CATEGORY", "BRAND", "COLOR", "SIZE", "PRICE", "MIN_PRICE", "MAX_PRICE", "PATTERN", "ORDER_ID", "LOCATION", "QUANTITY", "occasion"]

SYSTEM_PROMPT = """
You are Meridin's Tier 2 Instagram-commerce intent and entity interpreter for clothing stores.
Interpret the customer's message in English, Malayalam, Manglish, spelling variations, and short
follow-ups. Return only JSON matching the requested schema. Use only supported intent labels.
The primary intent must describe the customer's main goal. Use secondary_intents for additional
clear intents (for example, greeting plus product availability). Extract only entities supported by
the message or supplied conversation context. Use null for absent values; never invent product names,
prices, stock, policies, delivery promises, working hours, or catalogue facts. If a message depends on
an unknown product/photo/context, set needs_context=true and clarification_required=true as appropriate.
If meaning is still unclear, use intent=unknown. Confidence is your estimated interpretation confidence,
not confidence that a product is in stock. Backend catalogue and business settings are the source of truth.
""".strip()


class LLMService:
    async def classify(self, text: str, context: dict | None = None, client_id: str | None = None) -> dict | None:
        if not settings.llm_enabled or not settings.llm_api_key:
            return None
        api_key = settings.llm_api_key
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

    @staticmethod
    def _schema() -> dict:
        return {
            "type": "object", "additionalProperties": False,
            "properties": {
                "intent": {"type": "string", "enum": sorted(INTENTS)},
                "secondary_intents": {"type": "array", "items": {"type": "string", "enum": sorted(INTENTS)}, "maxItems": 4},
                "entities": {"type": "object", "additionalProperties": False, "properties": {
                    "PRODUCT": {"type": ["string", "null"]}, "CATEGORY": {"type": ["string", "null"]},
                    "BRAND": {"type": ["string", "null"]}, "COLOR": {"type": ["string", "null"]},
                    "SIZE": {"type": ["string", "null"]}, "PRICE": {"type": ["number", "null"]},
                    "MIN_PRICE": {"type": ["number", "null"]}, "MAX_PRICE": {"type": ["number", "null"]},
                    "PATTERN": {"type": ["string", "null"]}, "ORDER_ID": {"type": ["string", "null"]},
                    "LOCATION": {"type": ["string", "null"]}, "QUANTITY": {"type": ["integer", "null"]},
                    "occasion": {"type": ["string", "null"]},
                }, "required": ENTITY_KEYS},
                "language": {"type": "string"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "needs_context": {"type": "boolean"}, "clarification_required": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["intent", "secondary_intents", "entities", "language", "confidence", "needs_context", "clarification_required", "reason"],
        }

    async def _responses(self, text: str, context: dict | None, api_key: str):
        payload = {
            "model": settings.llm_model, "instructions": SYSTEM_PROMPT,
            "input": json.dumps({"message": text, "context": context or {}}, ensure_ascii=False),
            "temperature": 0, "max_output_tokens": settings.llm_max_output_tokens, "store": False,
            "text": {"format": {"type": "json_schema", "name": "meridin_intent", "description": "Tier 2 intent and entity extraction", "strict": True, "schema": self._schema()}},
        }
        return await self._post_and_parse(f"{settings.llm_base_url.rstrip('/')}/responses", payload, api_key)

    async def _chat_completions(self, text: str, context: dict | None, api_key: str):
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT + "\nReturn a single valid JSON object with fields: intent, secondary_intents, entities, language, confidence, needs_context, clarification_required, reason. Entity keys: " + ", ".join(ENTITY_KEYS) + ". Use null for absent entity values."},
                {"role": "user", "content": json.dumps({"message": text, "context": context or {}}, ensure_ascii=False)},
            ], "temperature": 0, "max_tokens": settings.llm_max_output_tokens,
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
            usage_info = {"input_tokens": usage.get("input_tokens", usage.get("prompt_tokens", 0)), "output_tokens": usage.get("output_tokens", usage.get("completion_tokens", 0)), "model": data.get("model", settings.llm_model)}
            if parsed:
                parsed["_usage"] = usage_info
                return parsed
            return {"_invalid": True, "_usage": usage_info}
        except Exception as exc:
            logger.warning("Tier 2 model request failed: %s", exc)
            return None

    @staticmethod
    def _extract_text(data: dict) -> str | None:
        if data.get("output_text"):
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
        if not isinstance(data, dict):
            return None
        intent = canonical_intent(data.get("intent", "unknown"))
        # Do not silently convert unsupported model labels into a real unknown result.
        if str(data.get("intent", "unknown")).strip().lower() not in INTENTS and str(data.get("intent", "unknown")).strip().lower() not in {"size_availability", "color_availability", "order_link_request", "human_handover_request", "order_placement", "product_inquiry_query"}:
            return None
        entities = data.get("entities") or {}
        if not isinstance(entities, dict):
            return None
        clean_entities = {}
        for key in ENTITY_KEYS:
            value = entities.get(key)
            if value is None or value == "" or value == []:
                continue
            if key in {"PRICE", "MIN_PRICE", "MAX_PRICE"}:
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
            if key == "QUANTITY":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            if isinstance(value, str):
                value = value.strip()[:160]
            clean_entities[key] = value
        try:
            confidence = float(data.get("confidence", 0))
        except (TypeError, ValueError):
            return None
        secondary = []
        for label in data.get("secondary_intents", []) if isinstance(data.get("secondary_intents", []), list) else []:
            canonical = canonical_intent(label)
            if canonical != "unknown" and canonical != intent and canonical not in secondary:
                secondary.append(canonical)
        return {
            "intent": intent, "secondary_intents": secondary[:4], "entities": clean_entities,
            "language": str(data.get("language", "Other"))[:40],
            "confidence": max(0.0, min(1.0, confidence)),
            "needs_context": bool(data.get("needs_context", False)),
            "clarification_required": bool(data.get("clarification_required", False)),
            "reason": str(data.get("reason", ""))[:300],
        }


llm_service = LLMService()
