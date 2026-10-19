from pathlib import Path

import pymupdf
import pytest

from app.rag.documents import UnreadableDocument, discover_pdfs, extract_document
from tests.rag_helpers import make_pdf

# Synthetic PDFs generated on the fly; used only inside these tests.


def test_pages_are_numbered_from_one_in_order(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "doc.pdf", ["Text on the first page of this synthetic file.", "", "Text on the third page of this synthetic file."])

    result = extract_document(pdf)

    assert [p.page for p in result.pages] == [1, 3]  # the blank page 2 is omitted, numbering is preserved
    assert "first page" in result.pages[0].text
    assert "third page" in result.pages[1].text


def test_title_comes_from_pdf_metadata_when_present(tmp_path: Path) -> None:
    assert extract_document(make_pdf(tmp_path / "a.pdf", ["Some synthetic page text here."], title="Synthetic Title")).title == "Synthetic Title"
    assert extract_document(make_pdf(tmp_path / "b.pdf", ["Some synthetic page text here."])).title is None


def test_hyphenated_line_breaks_are_rejoined_and_wrapping_removed(tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "doc.pdf", ["A synthetic sentence with a hyphen-\nated word that wraps\nacross lines."])

    text = extract_document(pdf).pages[0].text

    assert "hyphenated" in text
    assert "\n" not in text


def test_pdf_without_text_layer_yields_no_pages(tmp_path: Path) -> None:
    assert extract_document(make_pdf(tmp_path / "blank.pdf", ["", ""])).pages == []


def test_corrupt_file_raises_unreadable_document(tmp_path: Path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf")

    with pytest.raises(UnreadableDocument):
        extract_document(bad)


def test_password_protected_pdf_raises_unreadable_document(tmp_path: Path) -> None:
    plain = make_pdf(tmp_path / "plain.pdf", ["Secret synthetic page text."])
    locked = tmp_path / "locked.pdf"
    with pymupdf.open(plain) as doc:
        doc.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")

    with pytest.raises(UnreadableDocument):
        extract_document(locked)


def test_discovery_is_recursive_and_ignores_other_extensions(tmp_path: Path) -> None:
    make_pdf(tmp_path / "b.pdf", ["x"])
    make_pdf(tmp_path / "sub" / "a.PDF", ["x"])
    (tmp_path / "notes.txt").write_text("not a pdf")
    (tmp_path / "sub" / "pdf").write_text("no extension")

    found = discover_pdfs(tmp_path)

    assert [p.relative_to(tmp_path).as_posix() for p in found] == ["b.pdf", "sub/a.PDF"]


def test_discovery_of_empty_directory_returns_nothing(tmp_path: Path) -> None:
    assert discover_pdfs(tmp_path) == []
