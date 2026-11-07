from app.services.intent import detect


def test_manglish_price():
    result = detect("ee dress inte price ethra?")
    assert result.intent == "product_price"


def test_manglish_availability_entities():
    result = detect("black colour undo XL?")
    assert result.intent == "product_availability"
    assert result.entities["COLOR"] == "black"
    assert result.entities["SIZE"] == "XL"


def test_handoff():
    assert detect("I want to talk to a human").intent == "human_handoff"


def test_search():
    assert detect("show me something under 1500").intent == "product_search"
    assert detect("show me something under 1500").entities["PRICE"] == 1500.0


def test_manglish_product_image_requests_are_not_stock_queries():
    assert detect("Jeans nte image undo").intent == "media_product_identification"
    assert detect("Image ayakuo").intent == "media_product_identification"
    assert detect("Image ayakk").intent == "media_product_identification"


def test_short_price_followup_is_classified_as_product_price():
    assert detect("Price?").intent == "product_price"
    assert detect("Jeans nte price ethraya").intent == "product_price"


def test_manglish_category_availability_queries():
    jeans = detect("Ningal jeans vilkkunnundo?")
    assert jeans.intent == "product_availability"
    assert jeans.entities.get("CATEGORY") == "jeans"
    shirt = detect("Shirt vilkkunnundo?")
    assert shirt.intent == "product_availability"
    assert shirt.entities.get("CATEGORY") == "shirt"


def test_generic_catalogue_browse_in_manglish():
    result = detect("Ningal enthokke products anu sell cheyyunnath")
    assert result.intent == "product_search"


def test_manglish_picture_request_variants():
    assert detect("Pic ayakuo").intent == "media_product_identification"


def test_purchase_interest_in_manglish():
    assert detect("Ee jeans vangan thalparyam und").intent == "purchase_interest"
