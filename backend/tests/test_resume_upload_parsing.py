import pymupdf
import pytest

from app.resume import ResumeError, ResumeTooLarge, UnsupportedResumeType, extract_resume_text
from tests.rag_helpers import make_pdf

# Synthetic resume-like content used only to exercise parsing.
TEXT = "Synthetic candidate. Worked with alpha systems and beta tools for several years."
LIMITS = {"max_bytes": 1024 * 1024, "max_chars": 20_000}


def pdf_bytes(tmp_path, pages: list[str]) -> bytes:  # type: ignore[no-untyped-def]
    return make_pdf(tmp_path / "r.pdf", pages).read_bytes()


def test_pdf_text_is_extracted_from_bytes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    text = extract_resume_text("resume.PDF", pdf_bytes(tmp_path, [TEXT, "Second page about gamma work."]), **LIMITS)

    assert "alpha systems" in text and "gamma work" in text


def test_txt_is_decoded() -> None:
    assert extract_resume_text("resume.txt", f"  {TEXT}\r\nLine two.\r\n".encode(), **LIMITS) == f"{TEXT}\nLine two."


def test_utf8_bom_is_handled() -> None:
    assert extract_resume_text("r.txt", b"\xef\xbb\xbf" + "Café developer".encode(), **LIMITS) == "Café developer"


@pytest.mark.parametrize("filename", ["resume.docx", "resume", "resume.pdf.exe", None, "resume.md"])
def test_unsupported_types_are_rejected_with_415(filename: str | None) -> None:
    with pytest.raises(UnsupportedResumeType) as exc_info:
        extract_resume_text(filename, b"anything", **LIMITS)
    assert exc_info.value.status_code == 415


def test_oversize_files_are_rejected_with_413() -> None:
    with pytest.raises(ResumeTooLarge) as exc_info:
        extract_resume_text("r.txt", b"x" * 11, max_bytes=10, max_chars=100)
    assert exc_info.value.status_code == 413


@pytest.mark.parametrize(
    "filename, data, message",
    [
        ("r.txt", b"", "empty"),
        ("r.pdf", b"", "empty"),
        ("r.txt", b"   \n\t ", "no text"),
        ("r.txt", b"\xff\xfe\x00bad", "plain text"),
        ("r.txt", b"\x80\x81\x82 not utf-8", "UTF-8"),
        ("r.pdf", b"just some plain text", "not a PDF"),
        ("r.pdf", b"%PDF-1.7 corrupt", "could not be read"),
    ],
)
def test_unusable_files_are_rejected_with_a_specific_422(filename: str, data: bytes, message: str) -> None:
    with pytest.raises(ResumeError, match=message) as exc_info:
        extract_resume_text(filename, data, **LIMITS)
    assert exc_info.value.status_code == 422


def test_image_only_pdf_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ResumeError, match="no extractable text"):
        extract_resume_text("r.pdf", pdf_bytes(tmp_path, ["", ""]), **LIMITS)


def test_password_protected_pdf_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    plain = make_pdf(tmp_path / "plain.pdf", [TEXT])
    locked = tmp_path / "locked.pdf"
    with pymupdf.open(plain) as doc:
        doc.save(locked, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")

    with pytest.raises(ResumeError, match="password"):
        extract_resume_text("r.pdf", locked.read_bytes(), **LIMITS)


def test_text_is_truncated_to_the_character_limit() -> None:
    text = extract_resume_text("r.txt", ("word " * 100).encode(), max_bytes=10_000, max_chars=50)

    assert len(text) == 50
