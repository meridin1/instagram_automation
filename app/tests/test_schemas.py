from app.models.schemas import RegisterRequest


def test_register_accepts_brand_name():
    payload = RegisterRequest(brand_name="Test Clothing", email="test@example.com", password="test1234")
    assert payload.resolved_name == "Test Clothing"


def test_register_accepts_legacy_name():
    payload = RegisterRequest(name="Test Clothing", email="test2@example.com", password="test1234")
    assert payload.resolved_name == "Test Clothing"
