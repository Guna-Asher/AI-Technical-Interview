import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CandidateAnswer, InterviewQuestion, InterviewReport, InterviewSession

# Synthetic values used only to exercise the schema.


def new_session(db: Session) -> InterviewSession:
    interview = InterviewSession(role="synthetic role", candidate_profile={"skills": ["skill-a"]})
    db.add(interview)
    db.commit()
    return interview


def new_question(db: Session, session_id: uuid.UUID, position: int = 1) -> InterviewQuestion:
    question = InterviewQuestion(session_id=session_id, position=position, question_text=f"question {position}")
    db.add(question)
    db.commit()
    return question


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_full_interview_chain_persists_and_loads(db: Session) -> None:
    interview = new_session(db)
    chunks = [{"chunk_id": "chunk-1", "source": "synthetic source", "page": 3}]
    db.add_all(
        [
            InterviewQuestion(session_id=interview.id, position=2, question_text="second"),
            InterviewQuestion(
                session_id=interview.id, position=1, question_text="first", topic="topic-a", source_chunks=chunks
            ),
        ]
    )
    db.commit()
    first = db.scalars(select(InterviewQuestion).where(InterviewQuestion.position == 1)).one()
    db.add(CandidateAnswer(question_id=first.id, answer_text="synthetic answer"))
    db.add(InterviewReport(session_id=interview.id, summary="synthetic summary", strengths=["s1"]))
    db.commit()
    db.expire_all()

    loaded = db.get(InterviewSession, interview.id)

    assert loaded is not None
    assert [q.position for q in loaded.questions] == [1, 2]
    assert loaded.questions[0].source_chunks == chunks
    assert loaded.questions[1].source_chunks == []
    assert loaded.questions[0].answer is not None
    assert loaded.questions[0].answer.answer_text == "synthetic answer"
    assert loaded.questions[0].answer.feedback is None
    assert loaded.questions[1].answer is None
    assert loaded.report is not None
    assert loaded.report.strengths == ["s1"]
    assert loaded.report.improvement_topics == []


def test_answer_feedback_round_trips_as_jsonb(db: Session) -> None:
    question = new_question(db, new_session(db).id)
    feedback = {"synthetic": {"nested": [1, 2, 3]}, "note": "text"}
    db.add(CandidateAnswer(question_id=question.id, answer_text="answer", feedback=feedback))
    db.commit()
    db.expire_all()

    assert db.scalars(select(CandidateAnswer)).one().feedback == feedback


def test_duplicate_question_position_is_rejected(db: Session) -> None:
    interview = new_session(db)
    new_question(db, interview.id, position=1)

    with pytest.raises(IntegrityError):
        new_question(db, interview.id, position=1)


def test_question_position_must_be_positive(db: Session) -> None:
    with pytest.raises(IntegrityError):
        new_question(db, new_session(db).id, position=0)


def test_invalid_status_is_rejected(db: Session) -> None:
    db.add(InterviewSession(role="synthetic role", status="not-a-status"))

    with pytest.raises(IntegrityError):
        db.commit()


def test_question_can_only_have_one_answer(db: Session) -> None:
    question = new_question(db, new_session(db).id)
    db.add(CandidateAnswer(question_id=question.id, answer_text="first"))
    db.commit()
    db.add(CandidateAnswer(question_id=question.id, answer_text="second"))

    with pytest.raises(IntegrityError):
        db.commit()


def test_deleting_a_session_removes_its_related_rows(db: Session) -> None:
    interview = new_session(db)
    question = new_question(db, interview.id)
    db.add(CandidateAnswer(question_id=question.id, answer_text="answer"))
    db.add(InterviewReport(session_id=interview.id, summary="summary"))
    db.commit()

    db.delete(interview)
    db.commit()

    assert [count(db, m) for m in (InterviewSession, InterviewQuestion, CandidateAnswer, InterviewReport)] == [0] * 4
