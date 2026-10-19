"""The final interview report, written from the saved questions, answers and evaluations. Pure logic."""

import json
from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from app.openrouter import OpenRouterClient, complete_validated
from app.prompts import DATA_REMINDER, UNTRUSTED_DATA_RULES, untrusted_block
from app.schemas import AnswerFeedback

MAX_ITEMS = 8  # entries kept per report list
ANSWER_PROMPT_CHARS = 1500  # answers are shortened in the prompt only; the full text stays stored

Item = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


@dataclass(frozen=True)
class ReportItem:
    """One answered question with its saved evaluation."""

    position: int
    topic: str | None
    difficulty: str | None
    question: str
    answer: str
    feedback: AnswerFeedback


REPORT_SYSTEM = f"""\
You write the final report of a practice technical interview, for the candidate.

Task:
- The user message contains one data block with the interview role and, for each question, the question, the
  candidate's answer and the feedback that was already written for that answer.
- Base the report only on that data. Do not add facts, topics or advice that are not supported by it, and do not
  use generic advice that is not tied to the candidate's actual answers.
- Feedback marked evaluated_with_reference_passages: false was written without reference passages; do not
  present it as backed by source material.
- This is guidance for practice, not a measurement of professional competence.
- Return one JSON object of this form:
  {{"summary": string: an overall summary of how the interview went,
    "strengths": [strings: strengths shown in the answers],
    "improvement_topics": [strings: topics that need more practice],
    "recommendations": [strings: concrete, actionable next steps for study, at least one]}}
- Return only the JSON object, with no commentary.

{UNTRUSTED_DATA_RULES}"""


def _shorten(answer: str) -> str:
    return answer if len(answer) <= ANSWER_PROMPT_CHARS else answer[:ANSWER_PROMPT_CHARS] + " [answer shortened for this prompt]"


def build_report_messages(role: str, items: list[ReportItem]) -> tuple[str, str]:
    """The (system, user) messages. The system message is static; everything else is one delimited data block."""
    data = {
        "role": role,
        "questions": [
            {
                "position": item.position,
                "topic": item.topic,
                "difficulty": item.difficulty,
                "question": item.question,
                "answer": _shorten(item.answer),
                "evaluated_with_reference_passages": item.feedback.grounded,
                "feedback": {
                    "assessment": item.feedback.assessment,
                    "summary": item.feedback.summary,
                    "strengths": item.feedback.strengths,
                    "gaps": item.feedback.gaps,
                    "suggestions": item.feedback.suggestions,
                },
            }
            for item in items
        ],
    }
    return REPORT_SYSTEM, f"{untrusted_block('INTERVIEW_DATA', json.dumps(data, indent=2))}\n\n{DATA_REMINDER}"


def _clip(value: object) -> object:
    return value[:MAX_ITEMS] if isinstance(value, list) else value


class ReportContent(BaseModel):
    """A validated report. Unknown keys in the model's reply are ignored."""

    model_config = ConfigDict(extra="ignore")

    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)]
    strengths: Annotated[list[Item], BeforeValidator(_clip)] = []
    improvement_topics: Annotated[list[Item], BeforeValidator(_clip)] = []
    recommendations: Annotated[list[Item], BeforeValidator(_clip), Field(min_length=1)]


def validate_report(data: dict) -> ReportContent:
    return ReportContent.model_validate(data)


def generate_report(llm: OpenRouterClient, role: str, items: list[ReportItem]) -> ReportContent:
    """Ask the configured model for the report. Raises LLMError subclasses; invalid output is retried."""
    system, user = build_report_messages(role, items)
    return complete_validated(llm, system, user, validate_report, temperature=0.3)
