"""CLI for testing Phase 3 entity extraction."""
import sys
from app.ml.entity_extractor import extract_entities

if __name__ == "__main__":
    text = " ".join(sys.argv[1:]).strip()
    if not text:
        raise SystemExit('Usage: python -m app.ml.predict_entities "black kurti in XL under 1500"')
    print(extract_entities(text))
