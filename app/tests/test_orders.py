import pytest
from pydantic import ValidationError
from app.api.routes.orders import OrderCreate, OrderItemInput, OrderStatusUpdate


def test_order_item_requires_valid_object_id():
    with pytest.raises(ValidationError):
        OrderItemInput(product_id="not-an-object-id", quantity=1)


def test_order_payload_trims_customer_fields():
    payload = OrderCreate(
        customer_name="  Anu  ",
        customer_phone=" 9876543210 ",
        delivery_address="  12 Main Road, Kannur ",
        delivery_pincode=" 670001 ",
        items=[{"product_id": "000000000000000000000001", "quantity": 2, "size": "M", "color": "Black"}],
    )
    assert payload.customer_name == "Anu"
    assert payload.customer_phone == "9876543210"
    assert payload.delivery_pincode == "670001"
    assert payload.items[0].quantity == 2


def test_order_requires_at_least_one_item():
    with pytest.raises(ValidationError):
        OrderCreate(
            customer_name="Anu",
            customer_phone="9876543210",
            delivery_address="12 Main Road, Kannur",
            delivery_pincode="670001",
            items=[],
        )


def test_order_status_is_normalized_and_validated():
    assert OrderStatusUpdate(status=" CONFIRMED ").status == "confirmed"
    with pytest.raises(ValidationError):
        OrderStatusUpdate(status="paid")


def test_order_status_transition_rules_are_explicit():
    from app.api.routes.orders import ALLOWED_TRANSITIONS
    assert "confirmed" in ALLOWED_TRANSITIONS["pending"]
    assert "delivered" not in ALLOWED_TRANSITIONS["pending"]
    assert not ALLOWED_TRANSITIONS["delivered"]
    assert not ALLOWED_TRANSITIONS["cancelled"]
