from app.database.mongo import db
from app.services.intent import IntentResult
from app.services.semantic_search_service import search_products


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


async def build_response(client_id: str, intent: IntentResult, product: dict | None, original_text: str = ""):
    # The current pipeline does not run image recognition or audio transcription. Give
    # customers a transparent next step instead of silently dropping attachment-only DMs.
    if original_text == "[instagram_attachment:image]":
        return "I received your photo 😊 Could you share the product name or the post link? I’ll check the correct price and availability.", "automated"
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

    if intent.intent == "greeting":
        return "Hi 😊 How can I help you today?", "automated"
    if intent.intent == "thanks":
        return "You're welcome 😊", "automated"
    if intent.intent == "human_handoff":
        return "Sure 😊 I'll connect you with our team.", "human"
    if intent.intent == "location_query":
        return location or "Please message us for our location details.", "automated"
    if intent.intent == "delivery_query":
        return delivery or "Please message us for delivery details.", "automated"

    if intent.intent in {"return_request", "exchange_request"}:
        return "I'll connect you with our team so they can help with the return/exchange policy.", "human"
    if intent.intent == "order_request":
        return "Sure 😊 I'll connect you with our team to complete the order.", "human"

    if intent.intent == "product_search":
        results = await search_products(client_id, original_text, intent.entities, limit=3)
        if results:
            return _product_list(results), "automated"

    if intent.intent in {"product_price", "product_availability", "product_size", "product_color", "product_link", "product_alternatives"}:
        target = product
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
