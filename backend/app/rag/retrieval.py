"""Retrieve relevant knowledge chunks for a runtime query.

CLI for manual checks:
    python -m app.rag.retrieval "your query" [--top-k N] [--min-score X]
"""

import argparse
import sys
from dataclasses import dataclass

from app.config import get_settings
from app.rag.embeddings import Embedder, embed_texts
from app.rag.store import KnowledgeBaseError, get_collection


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    source_file: str
    source_title: str
    page: int  # 1-based physical page of the PDF
    chunk_index: int
    # Cosine similarity. A ranking signal, not a probability or a reliable confidence measure.
    score: float


def indexed_chunk_count(collection_name: str | None = None) -> int:
    """Number of chunks in the knowledge base (0 if it has not been ingested)."""
    collection = get_collection(collection_name)
    return collection.count() if collection is not None else 0


def retrieve(
    query: str,
    *,
    top_k: int | None = None,
    min_score: float | None = None,
    collection_name: str | None = None,
    embedder: Embedder | None = None,
) -> list[RetrievedChunk]:
    """Chunks most similar to `query`, best first. Empty when nothing is indexed or nothing clears `min_score`."""
    if not query or not query.strip():
        raise ValueError("query must not be blank")
    settings = get_settings()
    top_k = top_k or settings.retrieval_top_k
    min_score = settings.retrieval_min_score if min_score is None else min_score

    collection = get_collection(collection_name)
    if collection is None or collection.count() == 0:
        return []

    [vector] = (embedder or embed_texts)([query.strip()])
    result = collection.query(
        query_embeddings=[vector], n_results=top_k, include=["documents", "metadatas", "distances"]
    )
    chunks = [
        RetrievedChunk(
            chunk_id=chunk_id,
            text=text,
            source_file=str(meta["source_file"]),
            source_title=str(meta["source_title"]),
            page=int(meta["page"]),
            chunk_index=int(meta["chunk_index"]),
            score=1.0 - distance,
        )
        for chunk_id, text, meta, distance in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
    ]
    return sorted((c for c in chunks if c.score >= min_score), key=lambda c: c.score, reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Search the knowledge base.")
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--min-score", type=float, help="override the configured minimum similarity (0 shows raw scores)")
    args = parser.parse_args()

    try:
        total = indexed_chunk_count()
        if total == 0:
            print("ERROR: the knowledge base is empty. Run `python -m app.rag.ingest` first.", file=sys.stderr)
            return 1
        min_score = get_settings().retrieval_min_score if args.min_score is None else args.min_score
        results = retrieve(args.query, top_k=args.top_k, min_score=args.min_score)
    except (KnowledgeBaseError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not results:
        print(f"No passages reached the minimum similarity of {min_score} ({total} chunks searched).")
    for r in results:
        snippet = r.text if len(r.text) <= 300 else r.text[:300] + "…"
        print(f"[{r.score:.3f}] {r.source_title} ({r.source_file}), page {r.page}, chunk {r.chunk_id}\n    {snippet}\n")
    print("Scores are cosine similarity: a ranking signal, not a probability or confidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
