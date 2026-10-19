"""Resume handling: upload validation, in-memory text extraction, and LLM profile extraction.

The raw file and its text are never stored or logged; only the extracted profile is kept.
"""

from pathlib import PurePath

from app.openrouter import LLMBadResponse, OpenRouterClient, complete_validated
from app.prompts import DATA_REMINDER, UNTRUSTED_DATA_RULES, untrusted_block
from app.rag.documents import UnreadableDocument, extract_document
from app.schemas import CandidateProfile


class ResumeError(Exception):
    """The upload cannot be used. `status_code` is the HTTP status the API reports."""

    status_code = 422


class UnsupportedResumeType(ResumeError):
    status_code = 415


class ResumeTooLarge(ResumeError):
    status_code = 413


class EmptyProfile(ValueError):
    """The model's reply held no profile information at all."""


def extract_resume_text(filename: str | None, data: bytes, *, max_bytes: int, max_chars: int) -> str:
    """Validate an upload by extension and content, and return its text (truncated to `max_chars`)."""
    extension = PurePath(filename or "").suffix.lower()
    if extension not in (".pdf", ".txt"):
        raise UnsupportedResumeType("Unsupported file type. Upload a PDF or TXT resume.")
    if len(data) > max_bytes:
        raise ResumeTooLarge(f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit.")
    if not data:
        raise ResumeError("The uploaded file is empty.")

    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ResumeError("The file is named .pdf but is not a PDF document.")
        try:
            document = extract_document(data)
        except UnreadableDocument as exc:
            raise ResumeError(f"The PDF could not be read: {exc}.") from exc
        text = "\n\n".join(page.text for page in document.pages)
        if not text.strip():
            raise ResumeError("The PDF contains no extractable text (scanned or image-only PDFs are not supported).")
    else:
        if b"\x00" in data:
            raise ResumeError("The file is not a plain text file.")
        try:
            text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").strip()
        except UnicodeDecodeError as exc:
            raise ResumeError("The text file must be UTF-8 encoded.") from exc
        if not text:
            raise ResumeError("The text file contains no text.")
    return text[:max_chars]


PROFILE_SYSTEM = f"""\
You extract a structured candidate profile from resume text for a technical interview application.

Task:
- The resume text is supplied in the user message inside a data block.
- Return one JSON object with exactly these keys:
  "summary": a neutral summary of the candidate in at most three sentences, or null;
  "skills": an array of short strings (abilities, domains, concepts);
  "technologies": an array of short strings (languages, frameworks, libraries, tools, platforms, databases);
  "experience": an array of strings, one concise sentence per job, project or study item.
- Use only information that is stated in the resume. Do not infer, guess or add skills, technologies or
  experience that the resume does not mention.
- Return only the JSON object, with no commentary.

{UNTRUSTED_DATA_RULES}"""


def build_profile_messages(resume_text: str) -> tuple[str, str]:
    """The (system, user) messages for profile extraction. The system message never contains resume text."""
    return PROFILE_SYSTEM, f"{untrusted_block('RESUME_DATA', resume_text)}\n\n{DATA_REMINDER}"


_LIST_CAPS = {"skills": 100, "technologies": 100, "experience": 50}


def validate_profile(data: dict) -> CandidateProfile:
    """Turn the model's reply into a CandidateProfile. Unknown keys are ignored; anything else is validated."""
    cleaned: dict[str, object] = {}
    summary = data.get("summary")
    if summary is not None and not isinstance(summary, str):
        raise ValueError("'summary' must be a string or null")
    cleaned["summary"] = (summary or "").strip() or None
    for key, cap in _LIST_CAPS.items():
        items = data.get(key, [])
        if items is None:
            items = []
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            raise ValueError(f"'{key}' must be an array of strings")
        seen: set[str] = set()
        unique = []
        for item in (i.strip() for i in items):
            if item and item.lower() not in seen:
                seen.add(item.lower())
                unique.append(item)
        cleaned[key] = unique[:cap]
    profile = CandidateProfile(**cleaned)  # type: ignore[arg-type]  # pydantic enforces lengths; ValidationError is a ValueError
    if not (profile.summary or profile.skills or profile.technologies or profile.experience):
        raise EmptyProfile("the profile contains no information")
    return profile


def extract_profile(llm: OpenRouterClient, resume_text: str) -> CandidateProfile:
    """Ask the configured model for a profile of the resume. Raises LLMError subclasses, or ResumeError if empty."""
    system, user = build_profile_messages(resume_text)
    try:
        return complete_validated(llm, system, user, validate_profile, temperature=0)
    except LLMBadResponse as exc:
        if isinstance(exc.__cause__, EmptyProfile):
            raise ResumeError("No profile information could be extracted from this resume.") from exc
        raise
