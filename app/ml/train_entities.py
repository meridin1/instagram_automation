"""Train the Phase 3 BIO entity tagger."""
import json
from pathlib import Path
import joblib
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from app.ml.entity_extractor import tokenize, _token_features

BASE = Path(__file__).resolve().parent
DATA = BASE / "entity_data" / "entities.json"
MODELS = BASE / "entity_models"


def bio_labels(text, entities):
    tokens = tokenize(text)
    labels = ["O"] * len(tokens)
    for start, end, typ in entities:
        inside = [i for i, (_, s, e) in enumerate(tokens) if s >= start and e <= end]
        if not inside:
            continue
        labels[inside[0]] = f"B-{typ}"
        for i in inside[1:]:
            labels[i] = f"I-{typ}"
    return tokens, labels


def main():
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    X_dict, y = [], []
    for row in rows:
        tokens, labels = bio_labels(row["text"], row["entities"])
        for i, label in enumerate(labels):
            X_dict.append(_token_features(tokens, i))
            y.append(label)

    vectorizer = DictVectorizer(sparse=True)
    X = vectorizer.fit_transform(X_dict)
    model = LogisticRegression(max_iter=1200, class_weight="balanced")
    model.fit(X, y)
    MODELS.mkdir(exist_ok=True)
    joblib.dump(model, MODELS / "entity_tagger.joblib")
    joblib.dump(vectorizer, MODELS / "entity_vectorizer.joblib")
    print(f"Trained BIO entity tagger on {len(rows)} examples and {len(y)} tokens.")
    print(f"Saved: {MODELS / 'entity_tagger.joblib'}")


if __name__ == "__main__":
    main()
