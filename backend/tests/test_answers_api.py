import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import CandidateAnswer, InterviewQuestion

# Sessions, questions and answers here are synthetic fixtures that exist only in the test database.


def make_session(client: TestClient) -> str:
    return client.post("/api/interviews", json={"role": "synthetic role"}).json()["id"]


def add_questions(db: Session, session_id: str, count: int = 3) -> list[str]:
    rows = [
        InterviewQuestion(
            session_id=uuid.UUID(session_id),
            position=i,
            question_text=f"synthetic question {i}",
            topic=f"topic {i}",
            difficulty="easy",
            source_chunks=[{"chunk_id": f"c{i}", "source_file": "f.pdf", "source_title": "T", "page": i, "score": 0.5}],
        )
        for i in range(1, count + 1)
    ]
    db.add_all(rows)
    db.commit()
    return [str(r.id) for r in rows]


def answer_url(session_id: str, question_id: str) -> str:
    return f"/api/interviews/{session_id}/questions/{question_id}/answer"


def answer_count(db: Session) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(CandidateAnswer)) or 0


def test_submitting_an_answer_saves_it(api_client: TestClient, db: Session) -> None:
    session_id = make_session(api_client)
    q1, *_ = add_questions(db, session_id)

    response = api_client.post(answer_url(session_id, q1), json={"answer_text": "  my synthetic answer  "})

    assert response.status_code == 201
    body = response.json()
    assert body["answer_text"] == "my synthetic answer"
    assert body["question_id"] == q1
    assert set(body) == {"id", "question_id", "answer_text", "created_at"}  # no feedback exposed
    with SessionLocal() as fresh:  # a different connection than the request used
        row = fresh.scalars(select(CandidateAnswer)).one()
        assert (str(row.id), str(row.question_id), row.answer_text, row.feedback) == (body["id"], q1, "my synthetic answer", None)


@pytest.mark.parametrize(
    "body",
    [{}, {"answer_text": ""}, {"answer_text": "   \n "}, {"answer_text": 123}, {"answer_text": None}, {"answer_text": "a", "extra": 1}, {"answer_text": "x" * 10_001}],
)
def test_invalid_bodies_are_rejected_and_nothing_is_saved(api_client: TestClient, db: Session, body: dict) -> None:
    session_id = make_session(api_client)
    q1, *_ = add_questions(db, session_id)

    assert api_client.post(answer_url(session_id, q1), json=body).status_code == 422
    assert answer_count(db) == 0


def test_the_maximum_length_is_accepted(api_client: TestClient, db: Session) -> None:
    session_id = make_session(api_client)
    q1, *_ = add_questions(db, session_id)

    assert api_client.post(answer_url(session_id, q1), json={"answer_text": "x" * 10_000}).status_code == 201


def test_unknown_session_and_unknown_question_return_404(api_client: TestClient, db: Session) -> None:
    session_id = make_session(api_client)
    q1, *_ = add_questions(db, session_id)

    unknown_session = api_client.post(answer_url(str(uuid.uuid4()), q1), json={"answer_text": "a"})
    unknown_question = api_client.post(answer_url(session_id, str(uuid.uuid4())), json={"answer_text": "a"})

    assert unknown_session.status_code == 404 and unknown_session.json()["detail"] == "Interview session not found"
    assert unknown_question.status_code == 404 and unknown_question.json()["detail"] == "Question not found in this interview"
    assert answer_count(db) == 0


def test_malformed_ids_return_422(api_client: TestClient, db: Session) -> None:
    session_id = make_session(api_client)
    q1, *_ = add_questions(db, session_id)

    assert api_client.post(answer_url("not-a-uuid", q1), json={"answer_text": "a"}).status_code == 422
    assert api_client.post(answer_url(session_id, "not-a-uuid"), json={"answer_text": "a"}).status_code == 422


def test_a_question_from_another_session_returns_404_and_saves_nothing(api_client: TestClient, db: Session) -> None:
    session_a, session_b = make_session(api_client), make_session(api_client)
    add_questions(db, session_a)
    [question_b, *_] = add_questions(db, session_b)

    response = api_client.post(answer_url(session_a, question_b), json={"answer_text": "wrong session"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Question not found in this interview"
    assert answer_count(db) == 0


def test_a_second_answer_is_a_conflict_and_never_overwrites(api_client: TestClient, db: Session) -> None:
    session_id = make_session(api_client)
    q1, *_ = add_questions(db, session_id)
    assert api_client.post(answer_url(session_id, q1), json={"answer_text": "first"}).status_code == 201

    response = api_client.post(answer_url(session_id, q1), json={"answer_text": "second"})

    assert response.status_code == 409
    assert response.json()["detail"] == "This question has already been answered"
    assert answer_count(db) == 1
    assert db.scalars(select(CandidateAnswer)).one().answer_text == "first"


def test_the_unique_constraint_still_returns_409_when_the_pre_check_is_bypassed(
    api_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = make_session(api_client)
    q1, *_ = add_questions(db, session_id)
    api_client.post(answer_url(session_id, q1), json={"answer_text": "first"})
    monkeypatch.setattr("app.api.interviews._existing_answer", lambda db, question_id: None)  # simulate the race

    response = api_client.post(answer_url(session_id, q1), json={"answer_text": "second"})

    assert response.status_code == 409
    assert answer_count(db) == 1
    assert db.scalars(select(CandidateAnswer)).one().answer_text == "first"


def test_the_question_list_reports_which_questions_are_answered(api_client: TestClient, db: Session) -> None:
    session_id = make_session(api_client)
    q1, q2, q3 = add_questions(db, session_id)
    api_client.post(answer_url(session_id, q1), json={"answer_text": "answer one"})
    api_client.post(answer_url(session_id, q3), json={"answer_text": "answer three"})

    first = api_client.get(f"/api/interviews/{session_id}/questions").json()
    again = api_client.get(f"/api/interviews/{session_id}/questions").json()  # e.g. after a browser refresh

    assert first == again
    assert [q["position"] for q in first] == [1, 2, 3]
    assert [q["id"] for q in first] == [q1, q2, q3]
    assert [q["answer"]["answer_text"] if q["answer"] else None for q in first] == ["answer one", None, "answer three"]
    assert set(first[0]["answer"]) == {"id", "question_id", "answer_text", "created_at"}
    assert first[0]["answer"]["question_id"] == q1
    assert "feedback" not in str(first)


def test_answers_never_leak_between_sessions(api_client: TestClient, db: Session) -> None:
    session_a, session_b = make_session(api_client), make_session(api_client)
    [qa, *_] = add_questions(db, session_a)
    add_questions(db, session_b)
    api_client.post(answer_url(session_a, qa), json={"answer_text": "only for session a"})

    assert all(q["answer"] is None for q in api_client.get(f"/api/interviews/{session_b}/questions").json())
    assert "only for session a" not in api_client.get(f"/api/interviews/{session_b}/questions").text
