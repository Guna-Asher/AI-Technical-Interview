"""Smoke test of the real embedding model and its cache. Excluded from the default run.

Run it explicitly (needs network on the first run; afterwards the model is cached in the hf_cache volume):
    docker compose run --rm backend pytest -q -m real_model
"""

import math

import pytest

from app.rag.embeddings import embed_texts

pytestmark = pytest.mark.real_model


def test_real_model_embeds_and_ranks_a_relevant_sentence_first() -> None:
    query = "how do database indexes speed up queries"
    candidates = [
        "A btree index lets the database find rows without scanning the whole table.",
        "Sourdough bread rises slowly because wild yeast ferments the dough.",
        "The tomato seedlings need plenty of sunlight.",
    ]

    query_vec, *candidate_vecs = embed_texts([query, *candidates])

    assert len(query_vec) == 384
    assert math.isclose(sum(v * v for v in query_vec), 1.0, rel_tol=1e-3)
    similarities = [sum(a * b for a, b in zip(query_vec, vec)) for vec in candidate_vecs]
    assert similarities.index(max(similarities)) == 0
