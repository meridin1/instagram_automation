from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from app.core.security import get_client_id
from app.database.mongo import db

router = APIRouter(prefix="/api/orders", tags=["orders"])

ORDER_STATUSES = {"pending", "confirmed", "processing", "shipped", "delivered", "cancelled"}


class OrderItemInput(BaseModel):
    product_id: str = Field(min_length=24, max_length=24)
    quantity: int = Field(ge=1, le=100)
    size: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, max_length=60)


class OrderCreate(BaseModel):
    conversation_id: str | None = Field(default=None, min_length=24, max_length=24)
    customer_name: str = Field(min_length=1, max_length=120)
    customer_phone: str = Field(min_length=5, max_length=30)
    delivery_address: str = Field(min_length=5, max_length=1000)
    delivery_pincode: str = Field(min_length=4, max_length=12)
    notes: str = Field(default="", max_length=1000)
    items: list[OrderItemInput] = Field(min_length=1, max_length=20)

    @field_validator("customer_name", "customer_phone", "delivery_address", "delivery_pincode")
    @classmethod
    def strip_required_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value


class OrderStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        value = value.strip().lower()
        if value not in ORDER_STATUSES:
            raise ValueError("Invalid order status")
        return value


def _serialize(order):
    result = dict(order)
    result["id"] = str(result.pop("_id"))
    if isinstance(result.get("conversation_id"), ObjectId):
        result["conversation_id"] = str(result["conversation_id"])
    return result


@router.get("")
async def list_orders(
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    client_id: str = Depends(get_client_id),
):
    query = {"client_id": client_id}
    if status:
        if status not in ORDER_STATUSES:
            raise HTTPException(400, "Invalid order status")
        query["status"] = status
    cursor = db().orders.find(query).sort("created_at", -1).limit(limit)
    return [_serialize(order) async for order in cursor]


@router.post("", status_code=201)
async def create_order(payload: OrderCreate, client_id: str = Depends(get_client_id)):
    database = db()
    conversation_oid = None
    if payload.conversation_id:
        conversation_oid = ObjectId(payload.conversation_id)
        conversation = await database.conversations.find_one(
            {"_id": conversation_oid, "client_id": client_id}
        )
        if not conversation:
            raise HTTPException(404, "Conversation not found for this workspace")

    # Resolve every product inside this tenant and snapshot its catalogue facts.
    # Orders deliberately do not reserve stock; the owner confirms availability first.
    snapshots = []
    total = 0.0
    for item in payload.items:
        product = await database.products.find_one({
            "_id": ObjectId(item.product_id),
            "client_id": client_id,
            "active": {"$ne": False},
        })
        if not product:
            raise HTTPException(422, "One or more products are unavailable in this workspace")
        if not product.get("stock", False) or int(product.get("quantity", 0)) < item.quantity:
            raise HTTPException(409, f"Insufficient stock for {product.get('name', 'selected product')}")
        if item.size and item.size not in (product.get("sizes") or []):
            raise HTTPException(422, f"Size {item.size} is not available for {product.get('name')}")
        if item.color and item.color not in (product.get("colors") or []):
            raise HTTPException(422, f"Colour {item.color} is not available for {product.get('name')}")
        unit_price = float(product.get("sale_price") if product.get("sale_price") is not None else product.get("price", 0))
        line_total = round(unit_price * item.quantity, 2)
        total += line_total
        snapshots.append({
            "product_id": str(product["_id"]),
            "product_name": product.get("name", ""),
            "sku": product.get("sku"),
            "unit_price": unit_price,
            "quantity": item.quantity,
            "size": item.size,
            "color": item.color,
            "line_total": line_total,
        })

    now = datetime.now(timezone.utc)
    order = {
        "client_id": client_id,
        "order_number": f"MRD-{now.strftime('%y%m%d')}-{ObjectId()}",
        "conversation_id": conversation_oid,
        "customer": {
            "name": payload.customer_name,
            "phone": payload.customer_phone,
            "delivery_address": payload.delivery_address,
            "delivery_pincode": payload.delivery_pincode,
        },
        "items": snapshots,
        "subtotal": round(total, 2),
        "total": round(total, 2),
        "currency": "INR",
        "notes": payload.notes,
        "status": "pending",
        "stock_reserved": False,
        "created_at": now,
        "updated_at": now,
    }
    inserted = await database.orders.insert_one(order)
    return _serialize(await database.orders.find_one({"_id": inserted.inserted_id, "client_id": client_id}))


@router.patch("/{order_id}/status")
async def update_order_status(order_id: str, payload: OrderStatusUpdate, client_id: str = Depends(get_client_id)):
    try:
        oid = ObjectId(order_id)
    except Exception:
        raise HTTPException(400, "Invalid order id")
    existing = await db().orders.find_one({"_id": oid, "client_id": client_id})
    if not existing:
        raise HTTPException(404, "Order not found")
    current = existing.get("status", "pending")
    if current in {"delivered", "cancelled"} and payload.status != current:
        raise HTTPException(409, f"A {current} order cannot be changed")
    await db().orders.update_one(
        {"_id": oid, "client_id": client_id},
        {"$set": {"status": payload.status, "updated_at": datetime.now(timezone.utc)}},
    )
    return _serialize(await db().orders.find_one({"_id": oid, "client_id": client_id}))
