import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ProfileItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ExperienceItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class CandidateProfile(BaseModel):
    """Structured candidate profile, stored exactly as submitted."""

    model_config = ConfigDict(extra="forbid")

    summary: str | None = Field(default=None, max_length=2000)
    skills: list[ProfileItem] = Field(default_factory=list, max_length=100)
    technologies: list[ProfileItem] = Field(default_factory=list, max_length=100)
    experience: list[ExperienceItem] = Field(default_factory=list, max_length=50)


class InterviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The role is free-form user input; it is never matched against a predefined list.
    role: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    candidate_profile: CandidateProfile | None = None


class InterviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    status: str
    candidate_profile: CandidateProfile | None
    created_at: datetime
    completed_at: datetime | None


class SourceReference(BaseModel):
    """A knowledge-base chunk that a question is based on, as returned by retrieval."""

    chunk_id: str
    source_file: str
    source_title: str
    page: int
    score: float


MAX_ANSWER_CHARS = 10_000  # structural limit on a single answer


class AnswerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_ANSWER_CHARS)]


Assessment = Literal["correct_and_complete", "mostly_correct", "partially_correct", "incorrect_or_off_topic"]


class FeedbackSource(BaseModel):
    """A passage that supports an evaluation. Copied from the question's own saved sources, never from the model."""

    chunk_id: str
    source_file: str
    source_title: str
    page: int


class AnswerFeedback(BaseModel):
    """Qualitative, AI-generated feedback on one answer. Guidance only; there is deliberately no numeric score."""

    assessment: Assessment
    summary: str
    strengths: list[str]
    gaps: list[str]
    suggestions: list[str]
    # Set by the application: true only when at least one valid reference to a supplied passage was verified.
    grounded: bool
    source_chunks: list[FeedbackSource]


class AnswerRead(BaseModel):
    """A saved answer, with its evaluation once one exists."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_id: uuid.UUID
    answer_text: str
    created_at: datetime
    feedback: AnswerFeedback | None = None


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    question_text: str
    topic: str | None
    difficulty: str | None
    source_chunks: list[SourceReference]
    created_at: datetime
    answer: AnswerRead | None = None  # null until the candidate has answered


class ReportRead(BaseModel):
    """The saved final report with the interview's questions, answers and per-question feedback."""

    session_id: uuid.UUID
    role: str
    status: str
    completed_at: datetime | None
    created_at: datetime
    summary: str
    strengths: list[str]
    improvement_topics: list[str]
    recommendations: list[str]
    questions: list[QuestionRead]
    # Number of answers evaluated without reference passages (computed from the saved feedback).
    ungrounded_evaluations: int
