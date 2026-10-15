"""Load and run the trained Meridin intent classifier.

Python API:
    from app.ml.predict_intent import predict
    intent, confidence = predict("Do you still have this?")

CLI:
    python -m app.ml.predict_intent "Do you still have this?"
"""
from pathlib import Path
import sys
import joblib

MODEL_PATH = Path(__file__).resolve().parent / "models" / "intent_classifier.joblib"
_model = None


def get_model():
    global _model
    if _model is None and MODEL_PATH.exists():
        _model = joblib.load(MODEL_PATH)
    return _model


def predict(text: str) -> tuple[str | None, float]:
    model = get_model()
    if model is None or not text.strip():
        return None, 0.0

    probabilities = model.predict_proba([text])[0]
    classes = model.classes_
    best_index = int(probabilities.argmax())
    return str(classes[best_index]), float(probabilities[best_index])


def main():
    text = " ".join(sys.argv[1:]).strip()
    if not text:
        print('Usage: python -m app.ml.predict_intent "your message"')
        raise SystemExit(1)

    if not MODEL_PATH.exists():
        print("Model not found. Run: python -m app.ml.train_intent")
        raise SystemExit(1)

    intent, confidence = predict(text)
    print(f"intent={intent}")
    print(f"confidence={confidence:.4f}")


if __name__ == "__main__":
    main()
