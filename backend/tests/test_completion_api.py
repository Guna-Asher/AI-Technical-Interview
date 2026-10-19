import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.evaluation import NO_PASSAGES_NOTE
from app.main import app
from app.models import CandidateAnswer, InterviewQuestion, InterviewReport, InterviewSession
from app.openrouter import LLMProviderError, LLMTimeout, get_llm
from app.rag.store import get_client, get_collection
from tests.rag_helpers import fake_embed
from tests.test_openrouter_client import FakeLLM

# Roles, profiles, questions, answers and model replies here are synthetic test data; no model is ever called.
PROFILE = {"summary": None, "skills": ["query tuning"], "technologies": ["postgres", "caching"], "experience": []}
GENERATED = {
    "questions": [
        {"question": f"Synthetic question number {i} about the passages?", "topic": f"topic {i}", "difficulty": "medium", "source_refs": [1, 2]}
        for i in range(1, 6)
    ]
}
REPORT = {
    "summary": "A synthetic overall summary of the interview.",
    "strengths": ["strong on idea-a"],
    "improvement_topics": ["idea-b"],
    "recommendations": ["study idea-b"],
}


def eval_reply(summary: str = "Synthetic evaluation.", refs: tuple[int, ...] = (1,), **overrides: object) -> dict:
    return {
        "assessment": "mostly_correct",
        "summary": summary,
        "strengths": ["explained idea-a"],
        "gaps": ["missed idea-b"],
        "suggestions": ["mention idea-b"],
        "source_refs": list(refs),
        **overrides,
    }


@pytest.fixture
def llm(api_client: TestClient) -> FakeLLM:
    fake = FakeLLM()
    app.dependency_overrides[get_llm] = lambda: fake
    yield fake  # type: ignore[misc]
    app.dependency_overrides.pop(get_llm, None)


def create(client: TestClient, profile: dict | None = PROFILE) -> str:
    body: dict = {"role": "synthetic role"}
    if profile is not None:
        body["candidate_profile"] = profile
    return client.post("/api/interviews", json=body).json()["id"]


def add_questions(db: Session, session_id: str, count: int = 3, with_text: bool = True) -> None:
    for i in range(1, count + 1):
        chunk = {"chunk_id": f"c{i}", "source_file": "f.pdf", "source_title": "Synthetic Book", "page": i, "score": 0.5}
        if with_text:
            chunk["text"] = f"snapshot text {i}"
        db.add(
            InterviewQuestion(
                session_id=uuid.UUID(session_id), position=i, question_text=f"Direct question {i}?", topic=f"t{i}", difficulty="easy", source_chunks=[chunk]
            )
        )
    db.commit()


def answer_all(client: TestClient, session_id: str, only: int | None = None) -> None:
    for q in client.get(f"/api/interviews/{session_id}/questions").json()[:only]:
        response = client.post(f"/api/interviews/{session_id}/questions/{q['id']}/answer", json={"answer_text": f"my answer {q['position']}"})
        assert response.status_code == 201


def direct_session(client: TestClient, db: Session, count: int = 3, with_text: bool = True) -> str:
    session_id = create(client)
    add_questions(db, session_id, count, with_text)
    answer_all(client, session_id)
    return session_id


def feedback_rows(db: Session, session_id: str) -> list[dict | None]:
    db.expire_all()
    rows = db.execute(
        select(CandidateAnswer.feedback)
        .join(InterviewQuestion, InterviewQuestion.id == CandidateAnswer.question_id)
        .where(InterviewQuestion.session_id == uuid.UUID(session_id))
        .order_by(InterviewQuestion.position)
    )
    return [r[0] for r in rows]


def answer_texts(db: Session, session_id: str) -> list[str]:
    db.expire_all()
    rows = db.execute(
        select(CandidateAnswer.answer_text)
        .join(InterviewQuestion, InterviewQuestion.id == CandidateAnswer.question_id)
        .where(InterviewQuestion.session_id == uuid.UUID(session_id))
        .order_by(InterviewQuestion.position)
    )
    return [r[0] for r in rows]


def report_count(db: Session, session_id: str) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(InterviewReport).where(InterviewReport.session_id == uuid.UUID(session_id))) or 0


def session_state(db: Session, session_id: str) -> tuple[str, object]:
    db.expire_all()
    row = db.get(InterviewSession, uuid.UUID(session_id))
    return row.status, row.completed_at  # type: ignore[union-attr]


def complete(client: TestClient, session_id: str):  # type: ignore[no-untyped-def]
    return client.post(f"/api/interviews/{session_id}/complete")


# --- Unknown session / no report ---


def test_unknown_session_returns_404_for_complete_and_report(api_client: TestClient, llm: FakeLLM) -> None:
    unknown = uuid.uuid4()

    assert api_client.post(f"/api/interviews/{unknown}/complete").status_code == 404
    assert api_client.get(f"/api/interviews/{unknown}/report").status_code == 404


def test_report_is_404_until_one_exists(api_client: TestClient, llm: FakeLLM) -> None:
    response = api_client.get(f"/api/interviews/{create(api_client)}/report")

    assert response.status_code == 404
    assert response.json()["detail"] == "No report has been generated for this interview yet"


# --- Premature completion ---


def test_completion_without_questions_is_refused(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = create(api_client)

    response = complete(api_client, session_id)

    assert response.status_code == 409 and "no questions" in response.json()["detail"]
    assert llm.prompts == [] and report_count(db, session_id) == 0


def test_completion_with_unanswered_questions_is_refused_and_names_what_remains(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = create(api_client)
    add_questions(db, session_id, 4)
    answer_all(api_client, session_id, only=2)

    response = complete(api_client, session_id)

    assert response.status_code == 409
    assert response.json()["detail"] == "Answer question(s) 3, 4 before finishing the interview."
    assert llm.prompts == []  # no model call
    assert all(f is None for f in feedback_rows(db, session_id))
    assert report_count(db, session_id) == 0
    assert session_state(db, session_id)[0] != "completed"


def test_the_status_alone_does_not_make_an_interview_complete(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = create(api_client)
    add_questions(db, session_id, 2)
    db.execute(update(InterviewSession).where(InterviewSession.id == uuid.UUID(session_id)).values(status="completed"))
    db.commit()

    response = complete(api_client, session_id)

    assert response.status_code == 409
    assert report_count(db, session_id) == 0 and llm.prompts == []
    assert api_client.get(f"/api/interviews/{session_id}/report").status_code == 404


# --- Happy path, generated through the real question-generation code ---


def generate_and_answer(client: TestClient, llm: FakeLLM, db: Session) -> str:
    session_id = create(client)
    llm.replies.append(GENERATED)
    assert client.post(f"/api/interviews/{session_id}/questions").status_code == 201
    answer_all(client, session_id)
    return session_id


def test_completion_evaluates_each_answer_and_saves_the_report(api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str) -> None:
    session_id = generate_and_answer(api_client, llm, db)
    calls_before = len(llm.prompts)
    llm.replies.extend([eval_reply(f"Evaluation {i}.", refs=(1, 2)) for i in range(1, 6)] + [REPORT])

    response = complete(api_client, session_id)

    assert response.status_code == 201
    body = response.json()
    assert (body["role"], body["status"], body["summary"]) == ("synthetic role", "completed", REPORT["summary"])
    assert body["completed_at"] and body["created_at"]
    assert (body["strengths"], body["improvement_topics"], body["recommendations"]) == (REPORT["strengths"], REPORT["improvement_topics"], REPORT["recommendations"])
    assert body["ungrounded_evaluations"] == 0
    assert [q["position"] for q in body["questions"]] == [1, 2, 3, 4, 5]
    for q in body["questions"]:
        assert q["answer"]["answer_text"] == f"my answer {q['position']}"
        feedback = q["answer"]["feedback"]
        assert feedback["grounded"] is True and feedback["assessment"] == "mostly_correct"
        assert feedback["summary"] == f"Evaluation {q['position']}."
        assert len(feedback["source_chunks"]) == 2
    # the evaluations were made from the real question, the real answer and the saved passage snapshots
    db.expire_all()
    saved = db.scalars(select(InterviewQuestion).where(InterviewQuestion.session_id == uuid.UUID(session_id)).order_by(InterviewQuestion.position)).all()
    eval_prompts = llm.prompts[calls_before : calls_before + 5]
    for question, prompt in zip(saved, eval_prompts):
        assert question.question_text in prompt
        assert f"my answer {question.position}" in prompt
        assert all(ref["text"] in prompt for ref in question.source_chunks)
    report_prompt = llm.prompts[-1]
    assert "INTERVIEW_DATA" in report_prompt and "Evaluation 3." in report_prompt and "my answer 5" in report_prompt
    assert len(llm.prompts) == calls_before + 6
    # persisted
    assert report_count(db, session_id) == 1
    status, completed_at = session_state(db, session_id)
    assert status == "completed" and completed_at is not None
    assert all(f is not None for f in feedback_rows(db, session_id))
    assert "snapshot" not in response.text and "Database indexes speed up queries" not in response.text  # passage text is never returned


def test_saved_sources_are_traceable_to_the_questions_own_retrieved_sources(
    api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str
) -> None:
    session_id = generate_and_answer(api_client, llm, db)
    llm.replies.extend([eval_reply(refs=(2,)) for _ in range(5)] + [REPORT])

    body = complete(api_client, session_id).json()

    for q in body["questions"]:
        own = {(s["chunk_id"], s["source_file"], s["source_title"], s["page"]) for s in q["source_chunks"]}
        cited = [(s["chunk_id"], s["source_file"], s["source_title"], s["page"]) for s in q["answer"]["feedback"]["source_chunks"]]
        assert cited and set(cited) <= own
    collection = get_collection(seeded_knowledge)
    assert collection is not None
    for q in body["questions"]:
        for s in q["answer"]["feedback"]["source_chunks"]:
            assert collection.get(ids=[s["chunk_id"]])["ids"] == [s["chunk_id"]]  # the chunk really came from retrieval


def test_evaluation_uses_the_saved_snapshot_even_if_chroma_changes_or_disappears(
    api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = generate_and_answer(api_client, llm, db)
    db.expire_all()
    snapshots = {ref["text"] for q in db.scalars(select(InterviewQuestion).where(InterviewQuestion.session_id == uuid.UUID(session_id))) for ref in q.source_chunks}
    collection = get_collection(seeded_knowledge)
    assert collection is not None
    stored = collection.get(include=["metadatas"])
    changed = ["CHANGED CHROMA TEXT"] * len(stored["ids"])
    collection.upsert(ids=stored["ids"], documents=changed, embeddings=fake_embed(changed), metadatas=stored["metadatas"])  # re-ingested with new content
    get_client().delete_collection(seeded_knowledge)  # and then removed entirely
    calls_before = len(llm.prompts)
    llm.replies.extend([eval_reply(refs=(1,)) for _ in range(5)] + [REPORT])

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("Chroma must not be used while completing an interview")

    with monkeypatch.context() as m:
        m.setattr("app.rag.store.get_client", fail)
        m.setattr("app.rag.retrieval.retrieve", fail)
        m.setattr("app.question_generation.retrieve", fail)
        response = complete(api_client, session_id)

    assert response.status_code == 201
    prompts = "\n".join(llm.prompts[calls_before:])
    assert all(text in prompts for text in snapshots)  # the original retrieved text
    assert "CHANGED CHROMA TEXT" not in prompts
    assert all(q["answer"]["feedback"]["grounded"] for q in response.json()["questions"])


# --- No usable snapshot: honest ungrounded evaluation ---


def test_questions_without_a_snapshot_are_evaluated_as_ungrounded_and_flagged(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = direct_session(api_client, db, 3, with_text=False)
    llm.replies.extend([eval_reply(refs=()) for _ in range(3)] + [REPORT])

    response = complete(api_client, session_id)

    assert response.status_code == 201
    body = response.json()
    assert body["ungrounded_evaluations"] == 3
    assert all(q["answer"]["feedback"]["grounded"] is False and q["answer"]["feedback"]["source_chunks"] == [] for q in body["questions"])
    assert all(NO_PASSAGES_NOTE in p for p in llm.prompts[:3])
    assert '"evaluated_with_reference_passages": false' in llm.prompts[-1]


def test_a_reference_to_a_passage_that_was_never_supplied_is_not_accepted(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = direct_session(api_client, db, 2, with_text=False)
    llm.replies.extend([eval_reply(refs=(1,)), eval_reply(refs=(1,))])

    response = complete(api_client, session_id)

    assert response.status_code == 502
    assert all(f is None for f in feedback_rows(db, session_id)) and report_count(db, session_id) == 0


# --- Persistence and repetition ---


def test_the_report_and_feedback_can_be_read_again_with_new_requests(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = direct_session(api_client, db)
    llm.replies.extend([eval_reply(f"Evaluation {i}.") for i in range(1, 4)] + [REPORT])
    created = complete(api_client, session_id).json()

    report = api_client.get(f"/api/interviews/{session_id}/report")
    interview = api_client.get(f"/api/interviews/{session_id}").json()
    questions = api_client.get(f"/api/interviews/{session_id}/questions").json()

    assert report.status_code == 200 and report.json() == created
    assert interview["status"] == "completed" and interview["completed_at"]
    assert [q["answer"]["feedback"]["summary"] for q in questions] == ["Evaluation 1.", "Evaluation 2.", "Evaluation 3."]
    with SessionLocal() as fresh:  # a different connection
        row = fresh.scalars(select(InterviewReport).where(InterviewReport.session_id == uuid.UUID(session_id))).one()
        assert row.summary == REPORT["summary"] and row.recommendations == REPORT["recommendations"]


def test_completing_twice_returns_the_same_report_without_new_model_calls(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = direct_session(api_client, db)
    llm.replies.extend([eval_reply() for _ in range(3)] + [REPORT])
    first = complete(api_client, session_id)
    calls = len(llm.prompts)

    second = complete(api_client, session_id)

    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == first.json()
    assert len(llm.prompts) == calls and llm.replies == []
    assert report_count(db, session_id) == 1


def test_an_existing_report_with_a_stale_status_is_reconciled(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = direct_session(api_client, db, 2)
    db.add(InterviewReport(session_id=uuid.UUID(session_id), summary="saved earlier", strengths=[], improvement_topics=[], recommendations=["x"]))
    db.commit()
    db.expire_all()

    response = complete(api_client, session_id)

    assert response.status_code == 200 and response.json()["summary"] == "saved earlier"
    assert session_state(db, session_id)[0] == "completed" and session_state(db, session_id)[1] is not None
    assert llm.prompts == []


# --- Failures and retries ---


def test_a_provider_failure_midway_keeps_finished_work_and_the_retry_continues(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = direct_session(api_client, db, 3)
    before = session_state(db, session_id)
    llm.replies.extend([eval_reply("First."), LLMProviderError("provider is down")])

    failed = complete(api_client, session_id)

    assert failed.status_code == 502
    assert "1 of 3 answers evaluated" in failed.json()["detail"] and "provider is down" in failed.json()["detail"]
    saved = feedback_rows(db, session_id)
    assert saved[0] is not None and saved[0]["summary"] == "First." and saved[1:] == [None, None]
    assert answer_texts(db, session_id) == ["my answer 1", "my answer 2", "my answer 3"]
    assert report_count(db, session_id) == 0 and session_state(db, session_id) == before

    llm.replies.extend([eval_reply("Second."), eval_reply("Third."), REPORT])
    retried = complete(api_client, session_id)

    assert retried.status_code == 201
    assert len(llm.prompts) == 2 + 3  # the retry made 2 evaluations and 1 report call; answer 1 was not evaluated again
    assert "my answer 1" not in llm.prompts[2] and "my answer 2" in llm.prompts[2]
    assert [f["summary"] for f in feedback_rows(db, session_id)] == ["First.", "Second.", "Third."]  # type: ignore[index]
    assert report_count(db, session_id) == 1


def test_invalid_model_output_is_never_saved(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = direct_session(api_client, db, 3)
    # answer 2: a grounded reply with no references, then one with an out-of-range reference
    llm.replies.extend([eval_reply("Valid."), eval_reply(refs=()), eval_reply(refs=(9,))])

    response = complete(api_client, session_id)

    assert response.status_code == 502
    saved = feedback_rows(db, session_id)
    assert saved[0] is not None and saved[1] is None and saved[2] is None
    assert report_count(db, session_id) == 0
    assert answer_texts(db, session_id) == ["my answer 1", "my answer 2", "my answer 3"]


def test_a_failed_report_call_keeps_all_evaluations_and_the_retry_only_writes_the_report(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = direct_session(api_client, db, 3)
    llm.replies.extend([eval_reply() for _ in range(3)] + [LLMTimeout("too slow")])

    failed = complete(api_client, session_id)

    assert failed.status_code == 504 and "All 3 answers are evaluated and saved" in failed.json()["detail"]
    assert all(f is not None for f in feedback_rows(db, session_id)) and report_count(db, session_id) == 0
    assert session_state(db, session_id)[0] != "completed"
    calls = len(llm.prompts)

    llm.replies.append(REPORT)
    retried = complete(api_client, session_id)

    assert retried.status_code == 201 and len(llm.prompts) == calls + 1
    assert report_count(db, session_id) == 1


def test_an_invalid_report_is_never_saved(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = direct_session(api_client, db, 2)
    llm.replies.extend([eval_reply(), eval_reply(), {"summary": ""}, {"summary": "ok", "recommendations": []}])

    response = complete(api_client, session_id)

    assert response.status_code == 502
    assert report_count(db, session_id) == 0 and session_state(db, session_id)[0] != "completed"
    assert all(f is not None for f in feedback_rows(db, session_id))


def test_a_missing_api_key_returns_a_clear_503_and_writes_nothing(api_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = direct_session(api_client, db, 2)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()
    try:
        response = complete(api_client, session_id)
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503 and "OPENROUTER_API_KEY" in response.json()["detail"]
    assert all(f is None for f in feedback_rows(db, session_id)) and report_count(db, session_id) == 0
    assert answer_texts(db, session_id) == ["my answer 1", "my answer 2"]


# --- Concurrent requests ---


def test_feedback_saved_by_another_request_during_an_evaluation_is_kept(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = direct_session(api_client, db, 2)
    winner = {
        "assessment": "incorrect_or_off_topic", "summary": "RACER", "strengths": [], "gaps": [], "suggestions": [],
        "grounded": True, "source_chunks": [{"chunk_id": "c1", "source_file": "f.pdf", "source_title": "Synthetic Book", "page": 1}],
    }

    class RacingLLM(FakeLLM):
        raced = False

        def complete_json(self, system: str, user: str, temperature: float = 0.2) -> dict:
            if not self.raced:
                RacingLLM.raced = True
                with SessionLocal() as other:  # another request saves feedback for answer 1 first
                    first = other.scalars(
                        select(CandidateAnswer).join(InterviewQuestion).where(InterviewQuestion.session_id == uuid.UUID(session_id)).order_by(InterviewQuestion.position)
                    ).first()
                    other.execute(update(CandidateAnswer).where(CandidateAnswer.id == first.id).values(feedback=winner))  # type: ignore[union-attr]
                    other.commit()
            return super().complete_json(system, user, temperature)

    racing = RacingLLM(eval_reply("MINE"), eval_reply("Second."), REPORT)
    app.dependency_overrides[get_llm] = lambda: racing

    response = complete(api_client, session_id)

    assert response.status_code == 201
    assert feedback_rows(db, session_id)[0]["summary"] == "RACER"  # type: ignore[index]  # not overwritten
    assert response.json()["questions"][0]["answer"]["feedback"]["summary"] == "RACER"
    assert "RACER" in racing.prompts[-1] and "MINE" not in racing.prompts[-1]


def test_a_report_created_by_another_request_is_returned_without_a_duplicate(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = direct_session(api_client, db, 2)

    class RacingLLM(FakeLLM):
        def complete_json(self, system: str, user: str, temperature: float = 0.2) -> dict:
            if "INTERVIEW_DATA" in user:  # the report call: another request finishes first
                with SessionLocal() as other:
                    other.add(InterviewReport(session_id=uuid.UUID(session_id), summary="other request", strengths=[], improvement_topics=[], recommendations=["x"]))
                    other.commit()
            return super().complete_json(system, user, temperature)

    racing = RacingLLM(eval_reply(), eval_reply(), REPORT)
    app.dependency_overrides[get_llm] = lambda: racing

    response = complete(api_client, session_id)

    assert response.status_code == 200 and response.json()["summary"] == "other request"
    assert report_count(db, session_id) == 1
    assert session_state(db, session_id)[0] == "completed"
