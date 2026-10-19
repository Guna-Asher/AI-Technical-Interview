"""Helpers for RAG tests: synthetic PDFs and a deterministic fake embedder (no model, no network)."""

import hashlib
import math
import re
from collections.abc import Sequence
from pathlib import Path

import pymupdf

FAKE_DIM = 512


def make_pdf(path: Path, pages: list[str], title: str | None = None) -> Path:
    """Write a synthetic PDF with one page per string (an empty string gives a page without text)."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(50, 50, 550, 750), text, fontsize=11)
    if title:
        doc.set_metadata({"title": title})
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()
    return path


def fake_embed(texts: Sequence[str]) -> list[list[float]]:
    """Hashed bag-of-words vectors, L2-normalised: texts sharing words are similar, disjoint texts are about orthogonal."""
    vectors = []
    for text in texts:
        vec = [0.0] * FAKE_DIM
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            vec[int(hashlib.sha1(token.encode()).hexdigest(), 16) % FAKE_DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vectors.append([v / norm for v in vec])
    return vectors
