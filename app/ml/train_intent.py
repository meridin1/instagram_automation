"""Train the Meridin Phase 2 intent classifier.

Run from the project root:
    python -m app.ml.train_intent
"""
from pathlib import Path
import csv
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "intents.csv"
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "intent_classifier.joblib"


def load_data():
    texts, labels = [], []
    with DATA_PATH.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = row["text"].strip()
            label = row["intent"].strip()
            if text and label:
                texts.append(text)
                labels.append(label)
    return texts, labels


def main():
    texts, labels = load_data()
    if len(texts) < 50:
        raise RuntimeError("Not enough training examples. Add more examples to app/ml/data/intents.csv")

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=1,
        )),
        ("classifier", LogisticRegression(
            max_iter=2000,
            class_weight="balanced",
            random_state=42,
        )),
    ])

    # The dataset is intentionally small for Phase 2 development. A holdout split
    # is used only as a development signal; real production quality requires real
    # customer examples and a separate evaluation set.
    x_train, x_test, y_train, y_test = train_test_split(
        texts,
        labels,
        test_size=0.20,
        random_state=42,
        stratify=labels,
    )

    pipeline.fit(x_train, y_train)
    predictions = pipeline.predict(x_test)

    print(f"Examples: {len(texts)}")
    print(f"Accuracy on development holdout: {accuracy_score(y_test, predictions):.3f}")
    print(classification_report(y_test, predictions, zero_division=0))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)
    print(f"Saved model: {MODEL_PATH}")


if __name__ == "__main__":
    main()
