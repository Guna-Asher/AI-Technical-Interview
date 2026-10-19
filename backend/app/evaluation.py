"""Evaluation of one candidate answer against the passages its question was generated from. Pure logic.

The reference passages are the snapshots saved with the question (`InterviewQuestion.source_chunks[*].text`),
so evaluation never reads Chroma and never depends on documents that were re-ingested since.
"""

from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, StrictInt, StringConstraints

from app.openrouter import OpenRouterClient, complete_validated
from app.prompts import DATA_REMINDER, UNTRUSTED_DATA_RULES, untrusted_block
from app.schemas import Assessment, AnswerFeedback, FeedbackSource

MAX_ITEMS = 10  # entries kept per feedback list

Item = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    source_file: str
    source_title: str
    page: int
    text: str


def usable_passages(source_chunks: list[dict[str, Any]] | None) -> list[Passage]:
    """The saved snapshots that carry text. Entries without text (older or damaged data) are not usable."""
    passages = []
    for entry in source_chunks or []:
        try:
            text = entry["text"]
            if isinstance(text, str) and text.strip():
                passages.append(
                    Passage(str(entry["chunk_id"]), str(entry["source_file"]), str(entry["source_title"]), int(entry["page"]), text)
                )
        except (KeyError, TypeError, ValueError):
            continue
    return passages


EVALUATION_SYSTEM = f"""\
You evaluate one candidate's answer to one technical interview question and give feedback for practice.

Task:
- The user message contains data blocks: the question, the candidate's answer, and (usually) numbered reference
  passages from technical material that the question was based on.
- Judge the answer for correctness and completeness against the question and the reference passages.
- Do not state technical facts that the passages do not support. If the passages do not cover something, say so
  instead of inventing it. Do not invent sources. This is feedback for practice, not a measurement of competence.
- Return one JSON object of this form:
  {{"assessment": "correct_and_complete" | "mostly_correct" | "partially_correct" | "incorrect_or_off_topic",
    "summary": string,
    "strengths": [strings: concepts the candidate explained well],
    "gaps": [strings: important omissions or inaccuracies],
    "suggestions": [strings: concrete ways to improve the answer],
    "source_refs": [integers]}}
- "source_refs": when reference passages are provided, list the numbers of the passages that support your
  feedback, at least one. When the message says no reference passages are available, return an empty array.
- Return only the JSON object, with no commentary.

{UNTRUSTED_DATA_RULES}"""

NO_PASSAGES_NOTE = "No reference passages are available for this question. Return an empty source_refs array."


def build_evaluation_messages(
    question_text: str, topic: str | None, difficulty: str | None, answer_text: str, passages: list[Passage]
) -> tuple[str, str]:
    """The (system, user) messages. The system message is static; question, answer and passages are delimited data."""
    question_block = f"Topic: {topic or '-'}\nDifficulty: {difficulty or '-'}\nQuestion: {question_text}"
    parts = [untrusted_block("QUESTION_DATA", question_block), untrusted_block("ANSWER_DATA", answer_text)]
    if passages:
        parts.append(untrusted_block("REFERENCE_PASSAGES_DATA", "\n\n".join(f"[{i}] {p.text}" for i, p in enumerate(passages, start=1))))
    else:
        parts.append(NO_PASSAGES_NOTE)
    parts.append(DATA_REMINDER)
    return EVALUATION_SYSTEM, "\n\n".join(parts)


def _clip(value: object) -> object:
    return value[:MAX_ITEMS] if isinstance(value, list) else value


class _EvaluationItem(BaseModel):
    model_config = ConfigDict(extra="ignore")  # anything else the model adds is dropped

    assessment: Assessment
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    strengths: Annotated[list[Item], BeforeValidator(_clip)] = []
    gaps: Annotated[list[Item], BeforeValidator(_clip)] = []
    suggestions: Annotated[list[Item], BeforeValidator(_clip)] = []
    source_refs: list[StrictInt] = []


def validate_evaluation(data: dict, passages: list[Passage]) -> AnswerFeedback:
    """Validate the model's reply and build the feedback to save.

    With passages, at least one reference is required and every reference must be a supplied passage's number.
    Without passages, no reference is allowed. `grounded` is derived here from the verified references only.
    """
    item = _EvaluationItem.model_validate(data)
    if passages:
        if not item.source_refs:
            raise ValueError(f"source_refs must cite at least one of the supplied passages (numbers 1 to {len(passages)})")
        bad = [ref for ref in item.source_refs if not 1 <= ref <= len(passages)]
        if bad:
            raise ValueError(f"source_refs {bad} do not match a supplied passage; valid numbers are 1 to {len(passages)}")
        cited = [passages[ref - 1] for ref in dict.fromkeys(item.source_refs)]
        sources = [FeedbackSource(chunk_id=p.chunk_id, source_file=p.source_file, source_title=p.source_title, page=p.page) for p in cited]
    else:
        if item.source_refs:
            raise ValueError("no reference passages were supplied, so source_refs must be empty")
        sources = []
    return AnswerFeedback(
        assessment=item.assessment,
        summary=item.summary,
        strengths=item.strengths,
        gaps=item.gaps,
        suggestions=item.suggestions,
        grounded=bool(sources),
        source_chunks=sources,
    )


def evaluate_answer(
    llm: OpenRouterClient,
    question_text: str,
    topic: str | None,
    difficulty: str | None,
    answer_text: str,
    source_chunks: list[dict[str, Any]] | None,
) -> AnswerFeedback:
    """Ask the configured model to evaluate one answer. Raises LLMError subclasses; invalid output is retried."""
    passages = usable_passages(source_chunks)
    system, user = build_evaluation_messages(question_text, topic, difficulty, answer_text, passages)
    return complete_validated(llm, system, user, lambda data: validate_evaluation(data, passages), temperature=0.2)
