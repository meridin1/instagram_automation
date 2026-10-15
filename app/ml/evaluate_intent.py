"""Evaluate the trained Meridin intent classifier on a fixed unseen test set.

Run from the project root:
    python -m app.ml.evaluate_intent
"""
from pathlib import Path
import csv
import joblib
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

BASE_DIR = Path(__file__).resolve().parent
TEST_PATH = BASE_DIR / 'data' / 'test_intents.csv'
MODEL_PATH = BASE_DIR / 'models' / 'intent_classifier.joblib'


def load_test_data():
    texts, labels = [], []
    with TEST_PATH.open('r', encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            texts.append(row['text'].strip())
            labels.append(row['intent'].strip())
    return texts, labels


def main():
    if not MODEL_PATH.exists():
        raise RuntimeError('Model not found. Run: python -m app.ml.train_intent')
    texts, labels = load_test_data()
    model = joblib.load(MODEL_PATH)
    predictions = model.predict(texts)
    accuracy = accuracy_score(labels, predictions)
    print(f'Test examples: {len(texts)}')
    print(f'Accuracy: {accuracy:.3f}')
    print('\nClassification report:')
    print(classification_report(labels, predictions, zero_division=0))
    print('Confusion matrix labels:')
    classes = list(model.classes_)
    print(classes)
    print(confusion_matrix(labels, predictions, labels=classes))
    print('\nIncorrect predictions:')
    probabilities = model.predict_proba(texts)
    for text, actual, predicted, probs in zip(texts, labels, predictions, probabilities):
        if actual != predicted:
            confidence = float(max(probs))
            print(f'- {text!r} | expected={actual} | predicted={predicted} | confidence={confidence:.3f}')

if __name__ == '__main__':
    main()
