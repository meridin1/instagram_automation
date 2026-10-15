# Meridin Instagram Phase 2 — ML Intent Classifier

This is a drop-in upgrade for Phase 1.

## Files added

```text
app/ml/__init__.py
app/ml/data/intents.csv
app/ml/train_intent.py
app/ml/predict_intent.py
app/ml/models/.gitkeep
PHASE2_ML_SETUP.md
```

## Files changed

```text
requirements.txt
app/services/intent.py
app/services/conversation_service.py
.gitignore
```

## Install

From the project root, activate your existing virtual environment and run:

```powershell
python -m pip install -r requirements.txt
```

## Train the model

```powershell
python -m app.ml.train_intent
```

This creates:

```text
app/ml/models/intent_classifier.joblib
```

The model is intentionally optional. If the model file is missing, the API still works using the deterministic rules.

## Run the API

```powershell
uvicorn app.main:app --reload --port 8000
```

## Test

Use the existing `POST /api/test/inbound` endpoint.

Try messages that rules already handle:

```text
What colours are available?
Is XL available?
Send me the link
Any other designs?
```

Then try more natural/ambiguous messages such as:

```text
Could you tell me what this costs?
Do you still have one of these?
I'd like to see something similar
Can someone from the shop help me?
```

## Important

The current dataset is a development starter dataset, not a production-quality training set. Before relying on the classifier in production, collect real, anonymized customer messages and add them to `app/ml/data/intents.csv`.

The classifier uses TF-IDF + Logistic Regression. A confidence threshold of 0.72 is used. Low-confidence predictions fall back to `unknown` instead of guessing.

Rules remain first for commerce-critical signals such as price, size, colour, product links, delivery and human handoff.
