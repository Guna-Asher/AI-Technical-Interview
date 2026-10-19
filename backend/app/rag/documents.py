"""PDF discovery, per-page text extraction, and chunking."""

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

# Pages or chunks with fewer characters than this carry no useful text (page numbers, blank pages).
MIN_TEXT_CHARS = 20

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")


class UnreadableDocument(Exception):
    """The PDF is corrupt, encrypted, or otherwise cannot be read."""


@dataclass(frozen=True)
class PageText:
    page: int  # 1-based physical page index (may differ from the page number printed in the book)
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    title: str | None
    pages: list[PageText]


def discover_pdfs(directory: Path) -> list[Path]:
    """All PDF files under `directory` (recursive, case-insensitive extension), sorted by path."""
    return sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")


def _clean(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"-\n(?=[a-z])", "", text)  # re-join words hyphenated across line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)  # blank lines separate paragraphs
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)  # other line breaks are just wrapping
    return text.strip()


def extract_document(source: Path | bytes) -> ExtractedDocument:
    """Extract cleaned text per page from a PDF file or its raw bytes.

    Pages without useful text are omitted (scanned PDFs yield none).
    """
    try:
        doc = pymupdf.open(stream=source, filetype="pdf") if isinstance(source, bytes) else pymupdf.open(source)
    except Exception as exc:
        raise UnreadableDocument(f"cannot open PDF: {exc}") from exc
    with doc:
        if doc.needs_pass:
            raise UnreadableDocument("PDF is password-protected")
        try:
            pages = [PageText(i + 1, _clean(page.get_text("text"))) for i, page in enumerate(doc)]
        except Exception as exc:
            raise UnreadableDocument(f"cannot read PDF text: {exc}") from exc
        title = (doc.metadata or {}).get("title") or None
    return ExtractedDocument(
        title=title.strip() if title else None,
        pages=[p for p in pages if len(p.text) >= MIN_TEXT_CHARS],
    )


def _atoms(text: str, size: int, overlap: int) -> list[str]:
    """Split text into pieces of at most `size` characters, preferring paragraph, sentence, then word breaks."""
    atoms: list[str] = []
    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= size:
            atoms.append(paragraph)
            continue
        for sentence in _SENTENCE_BREAK.split(paragraph):
            if len(sentence) <= size:
                atoms.append(sentence)
                continue
            for word in sentence.split():  # an oversize sentence is split into words
                if len(word) <= size:
                    atoms.append(word)
                else:  # an unbroken token longer than a chunk: hard-split it with overlap
                    step = max(size - overlap, 1)
                    atoms.extend(word[i : i + size] for i in range(0, len(word), step))
    return atoms


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into chunks of at most `size` characters; consecutive chunks share about `overlap` characters."""
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("size must be positive and overlap must satisfy 0 <= overlap < size")
    chunks: list[str] = []
    current = ""
    for atom in _atoms(text, size, overlap):
        if current and len(current) + 1 + len(atom) <= size:
            current += " " + atom
            continue
        if current:
            chunks.append(current)
            # Carry the end of the previous chunk (from a word boundary) into the next one, as far as it fits.
            room = min(overlap, size - len(atom) - 1)
            tail = current[-room:].split(" ", 1)[-1] if room > 0 and len(current) > room else ""
            current = f"{tail} {atom}".strip()
        else:
            current = atom
    if current:
        chunks.append(current)
    return chunks
