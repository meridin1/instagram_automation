# Meridin Instagram Automation — Phase 2 Complete

Phase 2 adds a hybrid ML intent-classification layer while preserving the deterministic Phase 1 rules.

## What Phase 2 contains

- TF-IDF + Logistic Regression intent classifier
- 11 initial intents
- Expanded training dataset
- Separate unseen evaluation dataset
- Evaluation script with accuracy, precision, recall, F1 and confusion matrix
- CLI prediction tool
- Confidence threshold in `app/services/intent.py`
- Rule-first behavior for important commerce signals
- MongoDB logging of `intent_confidence` and `intent_source`

## Intents

- greeting
- thanks
- human_handoff
- product_alternatives
- product_link
- location_query
- delivery_query
- product_price
- product_availability
- product_color
- unknown

## Install

```powershell
python -m pip install -r requirements.txt
```

## Train

From the project root:

```powershell
python -m app.ml.train_intent
```

This creates:

```text
app/ml/models/intent_classifier.joblib
```

The model file is intentionally not committed to source control. Train it locally or in deployment.

## Evaluate

```powershell
python -m app.ml.evaluate_intent
```

The evaluation set is stored in:

```text
app/ml/data/test_intents.csv
```

The evaluation set is separate from the training CSV.

## Test the classifier directly

```powershell
python -m app.ml.predict_intent "Do you currently have this?"
python -m app.ml.predict_intent "Which shades can I choose from?"
python -m app.ml.predict_intent "Can you send me the product page?"
```

## Run the API

```powershell
uvicorn app.main:app --reload --port 8000
```

Then use:

```text
POST http://localhost:8000/api/test/inbound
```

The existing Phase 1 endpoint remains the end-to-end test endpoint.

## Important

The starter dataset and fixed evaluation set are development data. A high score on these examples does not prove production accuracy. Before production, collect representative, consented/anonymized customer messages, maintain a separate validation/test set, monitor low-confidence and unknown messages, and retrain deliberately.
