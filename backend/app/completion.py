"""Finishing an interview: evaluate every saved answer, then write and save the final report.

Answers are saved by a separate request and never depend on the model. This operation is resumable and idempotent:
- each evaluation is saved as soon as it is valid (write-once), so a later failure never loses it;
- retrying evaluates only the answers that still have no feedback;
- the report is created once (UNIQUE session_id); a repeated request returns the saved report.
"""

import uuid
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.evaluation import evaluate_answer
from app.models import CandidateAnswer, InterviewQuestion, InterviewReport, InterviewSession, InterviewStatus
from app.openrouter import LLMError, LLMNotConfigured, OpenRouterClient
from app.reporting import ReportItem, generate_report
from app.schemas import AnswerFeedback, QuestionRead, ReportRead


class IncompleteInterview(Exception):
    """The interview cannot be completed yet; the message says what is missing."""


def load_questions(db: Session, session_id: uuid.UUID) -> list[InterviewQuestion]:
    """A session's questions in order, each with its saved answer (if any), read fresh from the database."""
    return list(
        db.scalars(
            select(InterviewQuestion)
            .where(InterviewQuestion.session_id == session_id)
            .options(selectinload(InterviewQuestion.answer))
            .order_by(InterviewQuestion.position)
            .execution_options(populate_existing=True)
        )
    )


def get_report(db: Session, session_id: uuid.UUID) -> InterviewReport | None:
    return db.scalar(select(InterviewReport).where(InterviewReport.session_id == session_id))


def _same_error(exc: LLMError, message: str) -> LLMError:
    return type(exc)(message)


def _save_feedback(db: Session, answer_id: uuid.UUID, feedback: AnswerFeedback) -> None:
    """Write-once: only an answer without feedback is updated, so a concurrent request cannot overwrite it."""
    db.execute(
        update(CandidateAnswer)
        .where(CandidateAnswer.id == answer_id, CandidateAnswer.feedback.is_(None))
        .values(feedback=feedback.model_dump())
    )
    db.commit()


def _ensure_completed(db: Session, interview: InterviewSession) -> None:
    """Make the session row agree with an existing report (a report is the proof of completion)."""
    if interview.status != InterviewStatus.COMPLETED.value or interview.completed_at is None:
        interview.status = InterviewStatus.COMPLETED.value
        interview.completed_at = interview.completed_at or datetime.now(timezone.utc)
        db.commit()


def complete_interview(db: Session, llm: OpenRouterClient, session_id: uuid.UUID) -> tuple[InterviewReport, bool]:
    """Evaluate the answers and create the report. Returns (report, created)."""
    interview = db.get(InterviewSession, session_id)
    assert interview is not None  # the route has already returned 404 for unknown sessions

    existing = get_report(db, session_id)
    if existing is not None:
        _ensure_completed(db, interview)
        return existing, False

    questions = load_questions(db, session_id)
    if not questions:
        raise IncompleteInterview("This interview has no questions yet.")
    unanswered = [q.position for q in questions if q.answer is None]
    if unanswered:
        raise IncompleteInterview(
            "Answer question(s) " + ", ".join(str(p) for p in unanswered) + " before finishing the interview."
        )

    total = len(questions)
    done = sum(1 for q in questions if q.answer and q.answer.feedback is not None)
    for question in questions:
        answer = question.answer
        assert answer is not None
        if answer.feedback is not None:
            continue
        try:
            feedback = evaluate_answer(
                llm, question.question_text, question.topic, question.difficulty, answer.answer_text, question.source_chunks
            )
        except LLMNotConfigured:
            raise
        except LLMError as exc:
            raise _same_error(
                exc,
                f"{done} of {total} answers evaluated before the error. Your answers and the finished evaluations "
                f"are saved; try again to continue. Details: {exc}",
            ) from exc
        _save_feedback(db, answer.id, feedback)
        done += 1

    questions = load_questions(db, session_id)  # re-read: another request may have saved some feedback first
    items = []
    for question in questions:
        try:
            feedback = AnswerFeedback.model_validate(question.answer.feedback) if question.answer else None
        except ValidationError:
            feedback = None
        if question.answer is None or feedback is None:
            raise IncompleteInterview(f"Question {question.position} does not have a valid evaluation yet.")
        items.append(
            ReportItem(question.position, question.topic, question.difficulty, question.question_text, question.answer.answer_text, feedback)
        )

    try:
        content = generate_report(llm, interview.role, items)
    except LLMNotConfigured:
        raise
    except LLMError as exc:
        raise _same_error(
            exc, f"All {total} answers are evaluated and saved, but the report could not be written. Try again. Details: {exc}"
        ) from exc

    report = InterviewReport(
        session_id=session_id,
        summary=content.summary,
        strengths=content.strengths,
        improvement_topics=content.improvement_topics,
        recommendations=content.recommendations,
    )
    interview.status = InterviewStatus.COMPLETED.value
    interview.completed_at = datetime.now(timezone.utc)
    db.add(report)
    try:
        db.commit()
    except IntegrityError:  # another request saved the report first; use it
        db.rollback()
        existing = get_report(db, session_id)
        if existing is None:
            raise
        _ensure_completed(db, db.get(InterviewSession, session_id))  # type: ignore[arg-type]
        return existing, False
    return report, True


def build_report_read(db: Session, session_id: uuid.UUID) -> ReportRead:
    """The saved report joined with the interview's questions, answers and feedback, all read from the database."""
    interview = db.get(InterviewSession, session_id)
    report = get_report(db, session_id)
    assert interview is not None and report is not None
    db.refresh(interview)
    questions = load_questions(db, session_id)
    ungrounded = sum(1 for q in questions if q.answer and q.answer.feedback and not q.answer.feedback.get("grounded"))
    return ReportRead(
        session_id=session_id,
        role=interview.role,
        status=interview.status,
        completed_at=interview.completed_at,
        created_at=report.created_at,
        summary=report.summary,
        strengths=report.strengths,
        improvement_topics=report.improvement_topics,
        recommendations=report.recommendations,
        questions=[QuestionRead.model_validate(q) for q in questions],
        ungrounded_evaluations=ungrounded,
    )
