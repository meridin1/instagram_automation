import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from app.services.intent import detect
from app.services.llm_service import LLMService

cases = [
    ("ee dress inte price ethra?", "product_price"),
    ("black colour undo XL?", None),
    ("vere design undo?", "product_alternatives"),
    ("I want to talk to a human", "human_handoff"),
    ("show me something under 1500", "product_search"),
]

for text, expected in cases:
    result = detect(text)
    print(f"{text!r} -> {result.intent} {result.entities}")
    if expected and result.intent != expected:
        raise SystemExit(f"Smoke test failed for {text!r}: {result.intent} != {expected}")

print("Smoke tests passed.")
