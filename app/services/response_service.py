from app.database.mongo import db
from app.services.intent import IntentResult
from app.services.semantic_search_service import search_products
from app.core.config import settings as app_settings


async def business_settings(client_id: str):
    return await db().business_settings.find_one({"client_id": client_id}) or {}


async def automation_settings(client_id: str):
    return await db().automation_settings.find_one({"client_id": client_id}) or {
        "automation_enabled": True,
        "llm_enabled": False,
        "human_handoff_on_unknown": True,
        "tone": "Friendly",
        "language": "English",
    }


def _display_price(product: dict) -> str:
    sale = product.get("sale_price")
    if sale is not None:
        return f"₹{sale:.0f} (was ₹{product.get('price', 0):.0f})"
    return f"₹{product.get('price', 0):.0f}"


def _product_list(results: list[dict], heading="Here are some matching products:"):
    lines = [heading]
    for product in results:
        lines.append(f"• {product.get('name', '')} — {_display_price(product)}")
        if product.get("product_url"):
            lines.append(f"  {product['product_url']}")
    return "\n".join(lines)


async def execute_tool(client_id: str, tool: str, args: dict):
    if tool == "search_products":
        return await search_products(client_id, args.get("query", ""), args.get("entities", {}), int(args.get("limit", 3)))
    if tool == "get_product":
        from app.services.product_service import get_product
        return await get_product(client_id, args.get("product_id"))
    if tool == "check_availability":
        from app.services.product_service import get_product
        product = await get_product(client_id, args.get("product_id"))
        if not product:
            return None
        return {
            "available": bool(product.get("stock")) and int(product.get("quantity", 0)) > 0,
            "sizes": product.get("sizes", []),
            "colors": product.get("colors", []),
            "quantity": product.get("quantity", 0),
        }
    if tool == "get_business_info":
        return await business_settings(client_id)
    if tool == "get_delivery_info":
        settings = await business_settings(client_id)
        return {"delivery_info": settings.get("delivery_info", "")}
    if tool == "get_customer_context":
        return args.get("context", {})
    if tool == "handoff_to_human":
        return {"handoff": True}
    return None


async def build_response(
    client_id: str,
    intent: IntentResult,
    product: dict | None,
    original_text: str = "",
    *,
    visual_candidates: list[dict] | None = None,
    visual_filtered_candidates: list[dict] | None = None,
    has_image: bool = False,
):
    visual_candidates = visual_candidates or []
    visual_filtered_candidates = visual_filtered_candidates or []

    def visual_target(items: list[dict]):
        if not items:
            return None
        if len(items) == 1:
            return items[0]
        # Only auto-select when the best visual match is clearly ahead. Otherwise
        # show choices rather than risk quoting another design's price.
        if float(items[0].get("visual_similarity", 0)) - float(items[1].get("visual_similarity", 0)) >= app_settings.visual_match_margin:
            return items[0]
        return None

    # Attachment-only messages can now be matched against indexed catalogue images.
    # If no confident visual match exists, ask for clarification rather than guessing.
    if original_text == "[instagram_attachment:image]":
        target = visual_target(visual_candidates)
        if target:
            return (
                f"This looks closest to {target.get('name', 'this catalogue item')} "
                f"({_display_price(target)}). Is this the design you mean? 😊"
                + (f"\n{target['product_url']}" if target.get("product_url") else ""),
                "automated",
            )
        if visual_candidates:
            return _product_list(visual_candidates[:3], "These are the closest catalogue image matches:") + "\nWhich design do you mean? 😊", "automated"
        return "I received your photo 😊 I couldn't confidently match it to the catalogue. Could you send the product name or post link?", "automated"
    if original_text == "[instagram_attachment:audio]":
        return "I received your voice message 😊 I can’t transcribe voice notes yet. Could you type your question here?", "automated"
    if original_text == "[instagram_attachment:video]":
        return "I received your video 😊 Could you share the product name or post link so I can help with the correct details?", "automated"
    if original_text == "[instagram_attachment:other]":
        return "I received your attachment 😊 Could you type your question or share the product name?", "automated"

    settings = await business_settings(client_id)
    automation = await automation_settings(client_id)
    location = settings.get("location", "")
    delivery = settings.get("delivery_info", "")
    business_hours = str(settings.get("business_hours", "") or "").strip()

    if has_image and visual_candidates and intent.intent == "unknown":
        return _product_list(visual_candidates[:3], "I found these visually similar catalogue designs:") + "\nWhich one do you mean? 😊", "automated"

    # Tier 3: ask a concise clarification instead of executing a low-confidence guess.
    if intent.clarification_required and not (has_image and visual_filtered_candidates):
        if intent.needs_context or intent.entities.get("PRODUCT") or intent.entities.get("CATEGORY"):
            return "Sure 😊 Could you share the product name or a picture/post link so I can check the correct item?", "automated"
        return "I want to make sure I understand you correctly 😊 Could you explain a little more?", "automated"

    if intent.intent == "greeting":
        return "Hi 😊 How can I help you today?", "automated"
    if intent.intent == "thanks":
        return "You're welcome 😊", "automated"
    if intent.intent == "goodbye":
        return "Thank you for messaging us 😊 Have a lovely day!", "automated"
    if intent.intent == "human_handoff":
        return "Sure 😊 I'll connect you with our team.", "human"
    if intent.intent == "location_query":
        return location or "Please message us for our location details.", "automated"
    if intent.intent == "delivery_query":
        return delivery or "Please message us for delivery details.", "automated"
    if intent.intent == "delivery_time_query":
        delivery_time = settings.get("delivery_time", "") or settings.get("estimated_delivery", "")
        if delivery_time:
            return f"Our listed delivery estimate is {delivery_time}. 😊", "automated"
        return "Delivery time depends on the destination. I'll connect you with our team to confirm the estimate. 😊", "human"
    if intent.intent == "business_hours_query":
        if business_hours:
            # Common shorthand entered in dashboards: 9-9 means 9 AM to 9 PM.
            if business_hours.lower().replace(" ", "") in {"9-9", "9–9", "9to9"}:
                business_hours = "9 AM to 9 PM"
            return f"Our working hours are {business_hours}. 😊", "automated"
        return "Our working hours haven't been added here yet. Please message the shop directly and the team will confirm. 😊", "automated"

    if intent.intent in {"return_request", "exchange_request", "return_policy_query", "exchange_policy_query"}:
        policy_key = "return_policy" if intent.intent in {"return_request", "return_policy_query"} else "exchange_policy"
        policy = str(settings.get(policy_key, "") or "").strip()
        if policy and intent.intent in {"return_policy_query", "exchange_policy_query"}:
            return policy, "automated"
        return "I'll connect you with our team so they can help with the return/exchange request and confirm the applicable policy. 😊", "human"
    if intent.intent in {"order_request", "cancel_order", "order_status", "complaint", "delivery_issue"}:
        if intent.intent == "order_request":
            message = "Sure 😊 I'll connect you with our team to complete the order."
        elif intent.intent == "cancel_order":
            message = "I'll connect you with our team to review your cancellation request. 😊"
        elif intent.intent == "order_status":
            message = "I'll connect you with our team to check your order status. If possible, keep your order ID ready. 😊"
        elif intent.intent == "delivery_issue":
            message = "I'm sorry about the delivery issue. I'll connect you with our team to check this. 😊"
        else:
            message = "I'm sorry about this experience. I'll connect you with our team so they can help. 😊"
        return message, "human"
    if intent.intent == "payment_query":
        methods = settings.get("payment_methods", "") or settings.get("payment_info", "")
        if methods:
            return f"Our listed payment options are: {methods}", "automated"
        return "I'll connect you with our team to confirm the available payment methods. 😊", "human"
    if intent.intent == "discount_inquiry":
        return "I'll connect you with our team to confirm any current offers or discounts. 😊", "human"

    if intent.intent in {"product_inquiry", "product_details", "media_product_identification", "product_comparison"}:
        if has_image and not visual_candidates:
            return "I couldn't confidently match the photo to a catalogue item. Could you share a clearer photo or the product/post link? 😊", "automated"
        if has_image and visual_candidates and not visual_filtered_candidates:
            return _product_list(visual_candidates[:3], "These are the closest visual matches, but they don't match every detail in your message:") + "\nWhich one should I check? 😊", "automated"
        results = visual_filtered_candidates if has_image else await search_products(client_id, original_text, intent.entities, limit=3)
        if results:
            return _product_list(results, "Here are the closest catalogue matches:") + "\nPlease tell me which one you mean, and I'll check its details.", "automated"
        if automation.get("human_handoff_on_unknown", True):
            return "Could you share the product name or post link? I'll connect you with the team if I still can't match it. 😊", "human"
        return "Could you share the product name or post link so I can find the right item? 😊", "automated"

    if intent.intent == "product_search":
        if has_image and not visual_candidates:
            return "I couldn't confidently match the photo to a catalogue item. Could you share a clearer photo or the product/post link? 😊", "automated"
        if has_image and visual_candidates and not visual_filtered_candidates:
            return _product_list(visual_candidates[:3], "These are the closest visual matches:") + "\nWould you like details about one of these? 😊", "automated"
        results = visual_filtered_candidates if has_image else await search_products(client_id, original_text, intent.entities, limit=3)
        if results:
            return _product_list(results), "automated"

    if intent.intent in {"product_price", "product_availability", "product_size", "product_color", "product_link", "product_alternatives"}:
        # With an image, do not silently fall back to an unrelated lexical match.
        # The visual candidate set must establish the design before quoting its data.
        if has_image and not visual_candidates and intent.entities.get("COLOR"):
            requested_color = str(intent.entities.get("COLOR")).strip()
            return f"I couldn't confidently match the photo to a catalogue design, so I can't confirm whether this style comes in {requested_color}. Could you share a clearer photo or the product/post link? 😊", "automated"
        if has_image and not visual_candidates:
            return "I couldn't confidently match the photo to a catalogue design, so I don't want to guess its price or availability. Could you share a clearer photo or the product/post link? 😊", "automated"
        # For image + text, visual candidates establish the style first; explicit
        # text attributes (for example COLOR=blue) filter those candidates.
        if has_image and intent.entities.get("COLOR") and not visual_filtered_candidates and visual_candidates:
            requested_color = str(intent.entities.get("COLOR")).strip()
            return f"I couldn't find this same or a visually similar design in {requested_color} right now. Would you like to see the closest available designs? 😊", "automated"
        if has_image and not visual_filtered_candidates and visual_candidates and any(
            intent.entities.get(key) is not None for key in ("SIZE", "PRICE", "MIN_PRICE", "MAX_PRICE")
        ):
            return "I found visually similar designs, but none matched all the size/budget details you mentioned. Would you like to see the closest designs instead? 😊", "automated"

        target = visual_target(visual_filtered_candidates) if has_image else product
        if not target and has_image and visual_filtered_candidates:
            return _product_list(visual_filtered_candidates[:3], "These are the closest matching designs:") + "\nWhich one should I check? 😊", "automated"
        if not target:
            results = await search_products(
                client_id,
                original_text,
                intent.entities,
                limit=3,
            )
            if intent.intent == "product_alternatives" and results:
                target = results[0]
            elif len(results) == 1:
                target = results[0]
            elif len(results) > 1:
                return _product_list(results), "automated"

        if not target:
            if automation.get("human_handoff_on_unknown", True):
                return "I couldn't confidently match that to a catalogue item. Please send the product name or post, and I'll connect you with the team if needed.", "human"
            return "I couldn't find a matching product in the catalogue.", "automated"

        name = target.get("name", "This product")
        if intent.intent == "product_price":
            return f"{name} is {_display_price(target)}.", "automated"
        if intent.intent in {"product_availability", "product_size"}:
            available = bool(target.get("stock")) and int(target.get("quantity", 0)) > 0
            size = intent.entities.get("SIZE")
            if size:
                listed = size.upper() in [str(x).upper() for x in target.get("sizes", [])]
                return (f"Yes 😊 {size.upper()} is available for {name}." if available and listed else f"Sorry, {size.upper()} is not listed as available for {name}.", "automated")
            return (f"Yes 😊 {name} is currently available." if available else f"Sorry, {name} is currently out of stock.", "automated")
        if intent.intent == "product_color":
            colors = target.get("colors", [])
            requested_color = str(intent.entities.get("COLOR", "")).strip()
            if has_image and requested_color:
                has_requested_color = requested_color.lower() in [str(c).lower() for c in colors]
                if has_requested_color:
                    return f"Yes 😊 A visually similar design, {name}, is listed in {requested_color}. {_display_price(target)}.", "automated"
                if colors:
                    return f"I couldn't confirm {name} in {requested_color}. Listed colours are: {', '.join(colors)}.", "automated"
                return f"I don't have colour information listed for {name}.", "automated"
            return (f"Available colours for {name}: {', '.join(colors)}." if colors else f"I don't have colour information listed for {name}."), "automated"
        if intent.intent == "product_link":
            link = target.get("product_url", "")
            return (f"Sure 😊 Here is the link for {name}: {link}" if link else f"I don't have a product link listed for {name}.", "automated")
        if intent.intent == "product_alternatives":
            results = await search_products(
                client_id,
                f"{name} {target.get('category', '')} similar alternative",
                {},
                limit=3,
                exclude_product_id=str(target["_id"]),
            )
            return (_product_list(results, "Here are some other designs:"), "automated") if results else ("I couldn't find another matching design in the catalogue.", "automated")

    if automation.get("human_handoff_on_unknown", True):
        return "I'm not fully sure about that. I'll connect you with our team so you get the correct answer.", "human"
    return "I'm not fully sure about that. Please send the product name or post.", "automated"
