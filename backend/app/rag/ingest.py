"""Knowledge ingestion: PDFs -> per-page text -> chunks -> local embeddings -> Chroma.

Run it as a separate command (it is never triggered by an API request):
    python -m app.rag.ingest
"""

import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings
from app.rag.documents import MIN_TEXT_CHARS, UnreadableDocument, chunk_text, discover_pdfs, extract_document
from app.rag.embeddings import Embedder, embed_texts
from app.rag.store import KnowledgeBaseError, get_collection

WRITE_BATCH = 256


class IngestError(Exception):
    """The ingestion cannot start (for example the knowledge directory is missing or has no PDFs)."""


@dataclass
class FileResult:
    source_file: str
    status: str  # added | replaced | unchanged | no_text | failed
    pages: int = 0
    chunks: int = 0
    detail: str = ""


@dataclass
class IngestReport:
    results: list[FileResult] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)  # indexed, but no longer on disk
    total_chunks: int = 0

    def with_status(self, *statuses: str) -> list[FileResult]:
        return [r for r in self.results if r.status in statuses]

    @property
    def processed(self) -> int:
        """Documents that are now indexed (added, replaced) or confirmed up to date (unchanged)."""
        return len(self.with_status("added", "replaced", "unchanged"))


def _fingerprint(path: Path, model_name: str, chunk_size: int, chunk_overlap: int) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    digest.update(f"|{model_name}|{chunk_size}|{chunk_overlap}".encode())
    return digest.hexdigest()


def ingest_directory(
    directory: Path | str | None = None,
    *,
    collection_name: str | None = None,
    embedder: Embedder | None = None,
    model_name: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> IngestReport:
    """Ingest every PDF under `directory` into Chroma. Repeatable: unchanged files are skipped, changed ones replaced."""
    settings = get_settings()
    directory = Path(directory or settings.knowledge_dir)
    model_name = model_name or settings.embedding_model
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = settings.chunk_overlap if chunk_overlap is None else chunk_overlap

    if not directory.is_dir():
        raise IngestError(
            f"Knowledge directory not found: {directory}. Create it and put the technical PDF files there "
            "(the container reads the host folder ./knowledge, or the one set by KNOWLEDGE_HOST_DIR), then run again."
        )
    pdfs = discover_pdfs(directory)
    if not pdfs:
        raise IngestError(
            f"No PDF files found in {directory}. Put the technical PDF files in the host folder mounted there "
            "(default ./knowledge, or set KNOWLEDGE_HOST_DIR) and run again."
        )

    collection = get_collection(collection_name, create=True)
    assert collection is not None
    report = IngestReport()

    for pdf in pdfs:
        source_file = pdf.relative_to(directory).as_posix()
        fingerprint = _fingerprint(pdf, model_name, chunk_size, chunk_overlap)
        existing = collection.get(where={"source_file": source_file}, limit=1, include=["metadatas"])
        previously_indexed = bool(existing["ids"])
        if previously_indexed and (existing["metadatas"] or [{}])[0].get("fingerprint") == fingerprint:
            report.results.append(FileResult(source_file, "unchanged"))
            continue

        try:
            document = extract_document(pdf)
        except UnreadableDocument as exc:
            report.results.append(FileResult(source_file, "failed", detail=str(exc)))
            continue

        title = document.title if document.title and len(document.title) >= 4 else pdf.stem
        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, str | int]] = []
        for page in document.pages:
            for index, chunk in enumerate(c for c in chunk_text(page.text, chunk_size, chunk_overlap) if len(c) >= MIN_TEXT_CHARS):
                ids.append(f"{source_file}::p{page.page}::c{index}")
                texts.append(chunk)
                metadatas.append(
                    {
                        "source_file": source_file,
                        "source_title": title,
                        "page": page.page,
                        "chunk_index": index,
                        "fingerprint": fingerprint,
                    }
                )

        if not texts:
            if previously_indexed:  # the file changed and now has no text, so its old chunks are stale
                collection.delete(where={"source_file": source_file})
            report.results.append(FileResult(source_file, "no_text", detail="no extractable text (OCR is not supported)"))
            continue

        vectors = (embedder or embed_texts)(texts)  # computed before touching the collection, so a failure leaves old chunks intact
        if previously_indexed:
            collection.delete(where={"source_file": source_file})
        for start in range(0, len(ids), WRITE_BATCH):
            end = start + WRITE_BATCH
            collection.upsert(ids=ids[start:end], documents=texts[start:end], embeddings=vectors[start:end], metadatas=metadatas[start:end])
        report.results.append(
            FileResult(source_file, "replaced" if previously_indexed else "added", pages=len(document.pages), chunks=len(ids))
        )

    on_disk = {r.source_file for r in report.results}
    indexed = {m["source_file"] for m in collection.get(include=["metadatas"])["metadatas"] or []}
    report.missing_sources = sorted(str(s) for s in indexed - on_disk)
    report.total_chunks = collection.count()
    return report


def _print_report(report: IngestReport, directory: str) -> None:
    print(f"Knowledge directory: {directory} ({len(report.results)} PDF file(s))")
    for r in report.results:
        extra = f"{r.pages} page(s) with text, {r.chunks} chunk(s)" if r.chunks else r.detail
        print(f"  {r.status:<9} {r.source_file}" + (f"  ({extra})" if extra else ""))
    for source in report.missing_sources:
        print(f"  note: '{source}' is indexed but no longer on disk (left in place)")
    print(f"Collection now holds {report.total_chunks} chunk(s).")


def main() -> int:
    settings = get_settings()
    try:
        report = ingest_directory()
    except IngestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KnowledgeBaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # e.g. the embedding model could not be loaded
        print(f"ERROR: ingestion failed: {exc}", file=sys.stderr)
        return 1

    _print_report(report, settings.knowledge_dir)
    failed = report.with_status("failed")
    if failed:
        print(f"ERROR: {len(failed)} file(s) could not be read; see above.", file=sys.stderr)
        return 1
    if report.processed == 0:
        print("ERROR: no documents were indexed; none of the PDFs contained extractable text.", file=sys.stderr)
        return 1
    print("Ingestion complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
