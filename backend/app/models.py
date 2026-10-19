import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InterviewStatus(enum.StrEnum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('created', 'in_progress', 'completed')", name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    role: Mapped[str] = mapped_column(String(100))
    candidate_profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    status: Mapped[str] = mapped_column(
        String(20), default=InterviewStatus.CREATED.value, server_default=InterviewStatus.CREATED.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    questions: Mapped[list["InterviewQuestion"]] = relationship(
        back_populates="session",
        order_by="InterviewQuestion.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    report: Mapped["InterviewReport | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"
    __table_args__ = (
        UniqueConstraint("session_id", "position"),
        CheckConstraint("position >= 1", name="position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    question_text: Mapped[str] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(String(100))
    difficulty: Mapped[str | None] = mapped_column(String(20))
    # References to the Chroma chunks that informed the question; empty means not source-grounded.
    source_chunks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[InterviewSession] = relationship(back_populates="questions")
    answer: Mapped["CandidateAnswer | None"] = relationship(
        back_populates="question", cascade="all, delete-orphan", passive_deletes=True
    )


class CandidateAnswer(Base):
    __tablename__ = "candidate_answers"
    __table_args__ = (UniqueConstraint("question_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_questions.id", ondelete="CASCADE"))
    answer_text: Mapped[str] = mapped_column(Text)
    # Structured evaluation of this answer; NULL until an evaluation exists.
    feedback: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    question: Mapped[InterviewQuestion] = relationship(back_populates="answer")


class InterviewReport(Base):
    __tablename__ = "interview_reports"
    __table_args__ = (UniqueConstraint("session_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"))
    summary: Mapped[str] = mapped_column(Text)
    strengths: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    improvement_topics: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    recommendations: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[InterviewSession] = relationship(back_populates="report")
