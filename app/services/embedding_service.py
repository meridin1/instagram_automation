from functools import lru_cache
from app.core.config import settings


@lru_cache
def get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embedding_model)


def embed(text: str):
    return get_model().encode(text, normalize_embeddings=True).tolist()
