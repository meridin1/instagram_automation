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
