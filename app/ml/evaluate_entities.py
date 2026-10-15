"""Evaluate the Phase 3 entity tagger on the bundled examples."""
import json
from pathlib import Path
import joblib
from sklearn.metrics import classification_report, accuracy_score
from app.ml.entity_extractor import tokenize, _token_features
from app.ml.train_entities import bio_labels

BASE = Path(__file__).resolve().parent
DATA = BASE / "entity_data" / "test_entities.json"
MODELS = BASE / "entity_models"


def main():
    model = joblib.load(MODELS / "entity_tagger.joblib")
    vectorizer = joblib.load(MODELS / "entity_vectorizer.joblib")
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    y_true, y_pred = [], []
    for row in rows:
        tokens, labels = bio_labels(row["text"], row["entities"])
        X = vectorizer.transform([_token_features(tokens, i) for i in range(len(tokens))])
        pred = model.predict(X).tolist()
        y_true.extend(labels)
        y_pred.extend(pred)
    print(f"Token accuracy: {accuracy_score(y_true, y_pred):.4f}")
    print(classification_report(y_true, y_pred, zero_division=0))


if __name__ == "__main__":
    main()
