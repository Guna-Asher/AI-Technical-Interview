"""Dynamic question generation: retrieval queries from the session's role and profile, retrieved context,
an LLM call, and strict validation. Pure logic: no database access.
"""

import json
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, StrictInt, StringConstraints

from app.config import get_settings
from app.openrouter import OpenRouterClient, complete_validated
from app.prompts import DATA_REMINDER, UNTRUSTED_DATA_RULES, untrusted_block
from app.rag.retrieval import RetrievedChunk, indexed_chunk_count, retrieve
from app.schemas import CandidateProfile

QUERY_ITEMS = 6  # profile items combined per retrieval query
MAX_QUERY_CHARS = 500  # the embedding model reads only about 250 tokens


class NoRelevantKnowledge(Exception):
    """The knowledge base is empty or has too few relevant passages to ground questions."""


@dataclass(frozen=True)
class GeneratedQuestion:
    position: int  # 1-based
    question_text: str
    topic: str
    difficulty: str
    source_chunks: list[dict[str, Any]]  # built from retrieved chunks, never from model output


# --- Retrieval ---


def build_retrieval_queries(role: str, profile: CandidateProfile, max_queries: int) -> list[str]:
    """Assemble retrieval queries from the session's own role and profile. No fixed topics or fallback text."""
    role = role.strip()
    summary = (profile.summary or "").strip()
    queries = [f"{role}. {summary}" if summary else role]

    items: list[str] = []
    for item in [*profile.technologies, *profile.skills]:
        if item.lower() not in {i.lower() for i in items}:
            items.append(item)
    for start in range(0, len(items), QUERY_ITEMS):
        queries.append(f"{role}: {', '.join(items[start : start + QUERY_ITEMS])}")
    queries.extend(f"{role}: {entry}" for entry in profile.experience)

    unique: list[str] = []
    for query in (q[:MAX_QUERY_CHARS] for q in queries):
        if query not in unique:
            unique.append(query)
    return unique[:max_queries]


def gather_context(role: str, profile: CandidateProfile) -> list[RetrievedChunk]:
    """Retrieve passages for every query, merge by chunk (best score wins), and keep the best few.

    Raises NoRelevantKnowledge if the knowledge base is empty or too little relevant material is found.
    """
    settings = get_settings()
    if indexed_chunk_count() == 0:
        raise NoRelevantKnowledge(
            "The knowledge base is empty. Put the technical PDFs in the knowledge directory and run "
            "`python -m app.rag.ingest` (see the README), then try again."
        )
    best: dict[str, RetrievedChunk] = {}
    for query in build_retrieval_queries(role, profile, settings.max_retrieval_queries):
        for chunk in retrieve(query):
            if chunk.chunk_id not in best or chunk.score > best[chunk.chunk_id].score:
                best[chunk.chunk_id] = chunk
    chunks = sorted(best.values(), key=lambda c: c.score, reverse=True)[: settings.context_chunks]
    if len(chunks) < settings.min_context_chunks:
        raise NoRelevantKnowledge(
            f"Only {len(chunks)} sufficiently relevant passage(s) were found in the knowledge base for this role "
            f"and profile (at least {settings.min_context_chunks} are needed). Add more relevant technical PDFs "
            "and run ingestion, or use a role and profile that the ingested material covers."
        )
    return chunks


# --- Prompt ---


def _question_system(count: int) -> str:
    return f"""\
You write technical interview questions for a candidate.

Task:
- The user message contains data blocks: the candidate's target role, the candidate's profile, and numbered
  passages from technical reference material.
- Write exactly {count} interview questions tailored to this candidate and role. Each question must test
  understanding of concepts covered by one or more of the numbered passages, and may relate them to the
  candidate's stated experience.
- Do not write a question that the passages do not support, and do not base a question on knowledge that is
  not in the passages.
- Return one JSON object of this form:
  {{"questions": [{{"question": string, "topic": short string, "difficulty": "easy" | "medium" | "hard", "source_refs": [integers]}}]}}
- "source_refs" lists the numbers of the passages the question is based on, as integers, at least one per question.
- Return only the JSON object, with no commentary.

{UNTRUSTED_DATA_RULES}"""


def build_question_messages(
    role: str, profile: CandidateProfile, passages: list[RetrievedChunk], count: int
) -> tuple[str, str]:
    """The (system, user) messages. The system message holds only static instructions; all data is delimited."""
    numbered = "\n\n".join(f"[{i}] {chunk.text}" for i, chunk in enumerate(passages, start=1))
    user = "\n\n".join(
        [
            untrusted_block("ROLE_DATA", role),
            untrusted_block("PROFILE_DATA", json.dumps(profile.model_dump(), indent=2)),
            untrusted_block("PASSAGES_DATA", numbered),
            DATA_REMINDER,
        ]
    )
    return _question_system(count), user


# --- Validation ---


def _lower(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


class _QuestionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")  # anything else the model adds (such as chunk ids) is dropped

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=1000)]
    topic: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    difficulty: Annotated[Literal["easy", "medium", "hard"], BeforeValidator(_lower)]
    source_refs: list[StrictInt]


def _reference(chunk: RetrievedChunk) -> dict[str, Any]:
    """The saved record of a cited chunk, taken from the retrieval result.

    `text` is a snapshot of the exact passage the model saw, so later evaluation does not depend on Chroma,
    where a re-ingested document could have changed. The API exposes only the metadata (see SourceReference).
    """
    return {
        "chunk_id": chunk.chunk_id,
        "source_file": chunk.source_file,
        "source_title": chunk.source_title,
        "page": chunk.page,
        "score": round(chunk.score, 4),
        "text": chunk.text,
    }


def validate_questions(data: dict, passages: list[RetrievedChunk], count: int) -> list[GeneratedQuestion]:
    """Validate the model's reply and build questions whose source references come from `passages` only."""
    items = data.get("questions")
    if not isinstance(items, list):
        raise ValueError("'questions' must be an array")
    if len(items) != count:
        raise ValueError(f"expected exactly {count} questions, got {len(items)}")

    questions: list[GeneratedQuestion] = []
    seen: set[str] = set()
    for position, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"question {position} must be an object")
        item = _QuestionItem.model_validate(raw)
        if not item.source_refs:
            raise ValueError(f"question {position} must cite at least one passage in 'source_refs'")
        bad = [ref for ref in item.source_refs if not 1 <= ref <= len(passages)]
        if bad:
            raise ValueError(f"question {position} cites passage numbers {bad}; valid numbers are 1 to {len(passages)}")
        key = " ".join(item.question.lower().split())
        if key in seen:
            raise ValueError(f"question {position} duplicates an earlier question")
        seen.add(key)
        refs = list(dict.fromkeys(item.source_refs))
        questions.append(
            GeneratedQuestion(
                position=position,
                question_text=item.question,
                topic=item.topic,
                difficulty=item.difficulty,
                source_chunks=[_reference(passages[ref - 1]) for ref in refs],
            )
        )
    return questions


def generate_questions(
    llm: OpenRouterClient, role: str, profile: CandidateProfile, passages: list[RetrievedChunk], count: int
) -> list[GeneratedQuestion]:
    """Ask the configured model for questions grounded in `passages`. Raises LLMError subclasses on failure."""
    system, user = build_question_messages(role, profile, passages, count)
    return complete_validated(
        llm, system, user, lambda data: validate_questions(data, passages, count), temperature=0.7
    )
