import pytest


@pytest.fixture
def sample_product():
    return {
        "_id": "000000000000000000000001",
        "name": "Floral Kurti",
        "price": 1299,
        "sale_price": None,
        "category": "kurti",
        "brand": "Demo",
        "description": "Floral cotton kurti",
        "sizes": ["S", "M", "L", "XL"],
        "colors": ["Pink", "Black", "Blue"],
        "stock": True,
        "quantity": 12,
        "product_url": "https://example.com/floral-kurti",
        "active": True,
    }
