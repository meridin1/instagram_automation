# Meridin Instagram Phase 3 — Entity Extraction

Phase 3 adds a hybrid entity layer on top of Phase 2.

## Entities
- PRODUCT
- CATEGORY
- BRAND
- COLOR
- SIZE
- PRICE

Commerce-critical values (COLOR, SIZE, PRICE) use deterministic extraction. Dynamic product names are matched against the current tenant catalog. A lightweight BIO Logistic Regression tagger learns reusable PRODUCT/CATEGORY/BRAND patterns from the bundled examples.

## Files added
```text
app/ml/entity_data/entities.json
app/ml/entity_data/test_entities.json
app/ml/entity_models/entity_tagger.joblib
app/ml/entity_models/entity_vectorizer.joblib
app/ml/entity_extractor.py
app/ml/train_entities.py
app/ml/evaluate_entities.py
app/ml/predict_entities.py
app/tests/test_phase3.py
PHASE3_ENTITY_EXTRACTION.md
```

## Files changed from Phase 2
```text
app/services/intent.py
app/services/conversation_service.py
```

## Train
```powershell
python -m app.ml.train_entities
```

## Evaluate on unseen entity examples
```powershell
python -m app.ml.evaluate_entities
```

## Direct entity test
```powershell
python -m app.ml.predict_entities "Show me a black kurti in XL under 1500"
```

## Automated tests
```powershell
python -m unittest discover -s app/tests -v
```

## API
The existing endpoint remains:
`POST /api/test/inbound`

It now returns `entities`, `intent_confidence`, and `intent_source`.

Example input:
```json
{"client_id":"...","sender_id":"customer_001","text":"Show me the black kurti in XL under ₹1500","product_id":"..."}
```

Example result shape:
```json
{
  "status":"automated",
  "reply":"Floral Kurti is ₹1299.",
  "intent":"product_price",
  "intent_confidence":1.0,
  "intent_source":"rules",
  "entities":{
    "size":"XL",
    "color":"black",
    "max_price":1500.0,
    "by_type":{"COLOR":["black"],"PRODUCT":["Floral Kurti"],"CATEGORY":["kurti"],"SIZE":["XL"],"PRICE":[1500.0]}
  }
}
```
