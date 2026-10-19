from pathlib import Path

import pytest

from app.rag import ingest as ingest_module
from app.rag.ingest import IngestError, ingest_directory
from app.rag.retrieval import indexed_chunk_count, retrieve
from app.rag.store import get_collection
from tests.rag_helpers import fake_embed, make_pdf

# Everything here is synthetic and exists only inside these tests: PDFs in temporary directories,
# a deterministic fake embedder, and a throwaway "pytest_" Chroma collection.

DB_TEXT = "Database indexes speed up queries by avoiding full table scans. A btree index keeps keys sorted."
GARDEN_TEXT = "Tomato seedlings need sunlight and regular watering. Compost enriches garden soil with nutrients."
BREAD_TEXT = "Sourdough bread rises slowly because wild yeast ferments the dough overnight."


def ingest(directory: Path, collection: str, **kwargs):  # type: ignore[no-untyped-def]
    return ingest_directory(directory, collection_name=collection, embedder=fake_embed, model_name="fake", **kwargs)


@pytest.fixture
def library(rag_collection: str, tmp_path: Path) -> Path:
    """Two synthetic PDFs, one in a subfolder, so a single code path handles different documents."""
    directory = tmp_path / "library"
    make_pdf(directory / "db.pdf", ["Intro page about nothing in particular here.", DB_TEXT], title="Synthetic DB Book")
    make_pdf(directory / "sub" / "garden.pdf", [GARDEN_TEXT])
    return directory


def statuses(report) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {r.source_file: r.status for r in report.results}


def test_ingest_stores_chunks_with_source_metadata(rag_collection: str, library: Path) -> None:
    report = ingest(library, rag_collection)

    assert statuses(report) == {"db.pdf": "added", "sub/garden.pdf": "added"}
    collection = get_collection(rag_collection)
    assert collection is not None
    stored = collection.get(include=["metadatas", "documents"])
    assert collection.count() == report.total_chunks == sum(r.chunks for r in report.results)
    by_id = dict(zip(stored["ids"], stored["metadatas"]))
    db_page2 = next(m for i, m in by_id.items() if i.startswith("db.pdf::p2::"))
    assert db_page2["source_file"] == "db.pdf"
    assert db_page2["source_title"] == "Synthetic DB Book"  # from PDF metadata
    assert db_page2["page"] == 2
    garden = next(m for i, m in by_id.items() if i.startswith("sub/garden.pdf::"))
    assert garden["source_title"] == "garden"  # falls back to the filename
    assert garden["page"] == 1


def test_rerunning_ingestion_adds_no_duplicates(rag_collection: str, library: Path) -> None:
    first = ingest(library, rag_collection)
    second = ingest(library, rag_collection)

    assert set(statuses(second).values()) == {"unchanged"}
    assert second.processed == 2
    assert second.total_chunks == first.total_chunks


def test_changed_file_replaces_its_old_chunks(rag_collection: str, library: Path) -> None:
    ingest(library, rag_collection)
    make_pdf(library / "sub" / "garden.pdf", [BREAD_TEXT])

    report = ingest(library, rag_collection)

    assert statuses(report) == {"db.pdf": "unchanged", "sub/garden.pdf": "replaced"}
    collection = get_collection(rag_collection)
    assert collection is not None
    texts = " ".join(collection.get(where={"source_file": "sub/garden.pdf"})["documents"])
    assert "Sourdough" in texts
    assert "Tomato" not in texts


def test_changed_chunk_settings_reindex_everything(rag_collection: str, library: Path) -> None:
    ingest(library, rag_collection)

    report = ingest(library, rag_collection, chunk_size=300, chunk_overlap=30)

    assert set(statuses(report).values()) == {"replaced"}


def test_sources_removed_from_disk_are_reported_not_deleted(rag_collection: str, library: Path) -> None:
    first = ingest(library, rag_collection)
    (library / "sub" / "garden.pdf").unlink()

    report = ingest(library, rag_collection)

    assert report.missing_sources == ["sub/garden.pdf"]
    assert report.total_chunks == first.total_chunks


def test_missing_directory_is_an_actionable_error(rag_collection: str, tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="not found"):
        ingest(tmp_path / "nope", rag_collection)


def test_directory_without_pdfs_is_an_actionable_error(rag_collection: str, tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not a pdf")

    with pytest.raises(IngestError, match="No PDF files found"):
        ingest(tmp_path, rag_collection)


def test_pdf_without_text_is_reported_and_others_still_indexed(rag_collection: str, library: Path) -> None:
    make_pdf(library / "scanned.pdf", ["", ""])

    report = ingest(library, rag_collection)

    assert statuses(report)["scanned.pdf"] == "no_text"
    assert "OCR" in next(r.detail for r in report.results if r.source_file == "scanned.pdf")
    assert statuses(report)["db.pdf"] == "added"
    assert report.processed == 2


def test_corrupt_pdf_is_reported_as_failed_and_others_still_indexed(rag_collection: str, library: Path) -> None:
    (library / "broken.pdf").write_bytes(b"not a pdf")

    report = ingest(library, rag_collection)

    failed = report.with_status("failed")
    assert [r.source_file for r in failed] == ["broken.pdf"]
    assert failed[0].detail
    assert statuses(report)["db.pdf"] == "added"


# --- CLI exit codes and messages (settings are pointed at the temp directory and a pytest_ collection) ---


def has_line(output: str, status: str, name: str) -> bool:
    """True if the CLI summary has a line starting with `status` followed by `name`."""
    return any(line.split()[:2] == [status, name] for line in output.splitlines())


def run_cli(capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = ingest_module.main()
    out = capsys.readouterr()
    return code, out.out, out.err


def test_cli_missing_directory_fails_without_success_message(
    rag_collection: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("KNOWLEDGE_DIR", str(tmp_path / "nope"))
    get_settings.cache_clear()

    code, out, err = run_cli(capsys)

    assert code == 1
    assert "not found" in err
    assert "Ingestion complete" not in out


def test_cli_empty_directory_fails_without_success_message(
    rag_collection: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run_cli(capsys)  # KNOWLEDGE_DIR is the empty temp directory from the fixture

    assert code == 1
    assert "No PDF files found" in err
    assert "Ingestion complete" not in out


def test_cli_succeeds_when_some_pdfs_have_no_text(
    rag_collection: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.config import get_settings

    directory = Path(get_settings().knowledge_dir)
    make_pdf(directory / "good.pdf", [DB_TEXT])
    make_pdf(directory / "scanned.pdf", [""])
    monkeypatch.setattr(ingest_module, "embed_texts", fake_embed)

    code, out, _ = run_cli(capsys)

    assert code == 0
    assert has_line(out, "no_text", "scanned.pdf")
    assert has_line(out, "added", "good.pdf")
    assert "Ingestion complete" in out


def test_cli_fails_when_no_pdf_has_extractable_text(
    rag_collection: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.config import get_settings

    make_pdf(Path(get_settings().knowledge_dir) / "scanned.pdf", [""])

    code, out, err = run_cli(capsys)

    assert code == 1
    assert "no_text" in out
    assert "no documents were indexed" in err
    assert "Ingestion complete" not in out


def test_cli_exits_nonzero_after_processing_others_when_a_pdf_is_corrupt(
    rag_collection: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.config import get_settings

    directory = Path(get_settings().knowledge_dir)
    make_pdf(directory / "good.pdf", [DB_TEXT])
    (directory / "broken.pdf").write_bytes(b"not a pdf")
    monkeypatch.setattr(ingest_module, "embed_texts", fake_embed)

    code, out, err = run_cli(capsys)

    assert code == 1
    assert has_line(out, "added", "good.pdf")
    assert has_line(out, "failed", "broken.pdf")
    assert "could not be read" in err
    assert "Ingestion complete" not in out


def test_cli_rerun_on_up_to_date_knowledge_base_succeeds(
    rag_collection: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.config import get_settings

    make_pdf(Path(get_settings().knowledge_dir) / "good.pdf", [DB_TEXT])
    monkeypatch.setattr(ingest_module, "embed_texts", fake_embed)
    run_cli(capsys)

    code, out, _ = run_cli(capsys)

    assert code == 0
    assert "unchanged" in out


# --- Retrieval ---


def test_retrieval_returns_the_relevant_passage_with_references(rag_collection: str, library: Path) -> None:
    ingest(library, rag_collection)

    results = retrieve("how do database indexes speed up queries", collection_name=rag_collection, embedder=fake_embed, min_score=0.1)

    assert results
    top = results[0]
    assert (top.source_file, top.page, top.source_title) == ("db.pdf", 2, "Synthetic DB Book")
    assert top.chunk_id.startswith("db.pdf::p2::")
    assert "indexes" in top.text
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)
    assert all(r.score >= 0.1 for r in results)


def test_retrieval_finds_the_other_document_for_a_different_query(rag_collection: str, library: Path) -> None:
    ingest(library, rag_collection)

    top = retrieve("watering tomato seedlings with compost", collection_name=rag_collection, embedder=fake_embed, min_score=0.1)[0]

    assert top.source_file == "sub/garden.pdf"


def test_unrelated_query_returns_nothing(rag_collection: str, library: Path) -> None:
    ingest(library, rag_collection)

    assert retrieve("zebra xylophone quartz", collection_name=rag_collection, embedder=fake_embed) == []


def test_top_k_limits_the_number_of_results(rag_collection: str, library: Path) -> None:
    ingest(library, rag_collection)

    results = retrieve("database garden tomato index", top_k=1, collection_name=rag_collection, embedder=fake_embed, min_score=-1)

    assert len(results) == 1


@pytest.mark.parametrize("query", ["", "   "])
def test_blank_query_is_rejected(query: str) -> None:
    with pytest.raises(ValueError):
        retrieve(query, embedder=fake_embed)


def test_missing_or_empty_collection_returns_nothing(rag_collection: str) -> None:
    assert retrieve("anything", collection_name=rag_collection, embedder=fake_embed) == []  # does not exist yet
    assert indexed_chunk_count(rag_collection) == 0
    get_collection(rag_collection, create=True)
    assert retrieve("anything", collection_name=rag_collection, embedder=fake_embed) == []  # exists but empty
