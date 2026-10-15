"""Legacy compatibility module; neural embeddings are intentionally disabled in production."""
import re
from collections import Counter


def embed(text: str):
    """Return a lightweight token-count mapping, not a neural vector."""
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return dict(Counter(token for token in tokens if len(token) > 1))
