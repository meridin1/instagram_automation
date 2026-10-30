# Meridin follow-up fixes — 2026-10-29

Changes based on the latest conversation examples:

- `ethokke size il und` is classified as a size-list question and returns only sizes saved on the selected catalogue product.
- `Color vere undo` is classified as a colour question rather than generic product availability. Colour-plus-size questions such as `black colour undo XL?` retain variant-availability handling.
- `Vere designs undo` is classified as an alternatives request. Alternative lookup tries broader catalogue attributes (category, subcategory, product type, department) and excludes the current product. It never fabricates a product; if the active catalogue contains no other matching item, it explains that honestly.
- Explicit phrases such as `Ith order cheyyanam` are mapped to purchase intent before ML classification, preventing an erroneous cancellation classification.

Validation: `python -m compileall -q app` passed; `PYTHONPATH=. pytest -q app/tests/test_intent.py` passed (10 tests). This does not validate live Instagram delivery or the contents of a specific tenant's catalogue.
