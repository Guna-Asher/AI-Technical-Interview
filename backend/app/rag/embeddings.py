"""Local embeddings with Sentence Transformers (no external API)."""

from collections.abc import Callable, Sequence
from functools import lru_cache

from app.config import get_settings

# Anything that maps texts to vectors; tests pass a deterministic fake instead of the real model.
Embedder = Callable[[Sequence[str]], list[list[float]]]


@lru_cache
def _load_model(model_name: str):  # noqa: ANN202
    # Imported lazily so that importing the RAG package (and starting the API) does not load PyTorch.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def embed_texts(texts: Sequence[str], batch_size: int = 64) -> list[list[float]]:
    """Embed texts with the configured model; vectors are L2-normalised so dot product equals cosine similarity."""
    if not texts:
        return []
    model = _load_model(get_settings().embedding_model)
    vectors = model.encode(list(texts), batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()
