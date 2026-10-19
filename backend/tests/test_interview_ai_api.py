import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import InterviewQuestion, InterviewSession
from app.openrouter import LLMProviderError, LLMRateLimited, LLMTimeout, get_llm
from app.rag.store import KnowledgeBaseError, get_collection
from tests.test_openrouter_client import FakeLLM

# Every role, profile, resume and model reply here is synthetic and exists only inside these tests.
ROLE = "synthetic backend role"
PROFILE = {"summary": None, "skills": ["query tuning"], "technologies": ["postgres", "caching"], "experience": []}
EXTRACTED = {"summary": "Synthetic summary.", "skills": ["skill-a"], "technologies": ["tech-a"], "experience": ["did thing-a"]}
QUESTIONS = {
    "questions": [
        {"question": f"Synthetic question number {i} about the passages?", "topic": f"topic {i}", "difficulty": "medium", "source_refs": [1, 2]}
        for i in range(1, 6)
    ]
}


@pytest.fixture
def llm(api_client: TestClient) -> FakeLLM:
    fake = FakeLLM()
    app.dependency_overrides[get_llm] = lambda: fake
    yield fake  # type: ignore[misc]
    app.dependency_overrides.pop(get_llm, None)


def create(client: TestClient, profile: dict | None = PROFILE, role: str = ROLE) -> str:
    body: dict = {"role": role}
    if profile is not None:
        body["candidate_profile"] = profile
    return client.post("/api/interviews", json=body).json()["id"]


def question_rows(db: Session, session_id: str) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(InterviewQuestion).where(InterviewQuestion.session_id == uuid.UUID(session_id))) or 0


def stored_profile(db: Session, session_id: str) -> dict | None:
    db.expire_all()
    return db.get(InterviewSession, uuid.UUID(session_id)).candidate_profile  # type: ignore[union-attr]


def upload(client: TestClient, session_id: str, name: str = "resume.txt", content: bytes = b"Synthetic resume text with some content.") :  # type: ignore[no-untyped-def]
    return client.post(f"/api/interviews/{session_id}/resume", files={"file": (name, content, "application/octet-stream")})


# --- Resume upload ---


def test_resume_upload_saves_the_extracted_profile(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = create(api_client, profile=None)
    llm.replies.append(EXTRACTED)

    response = upload(api_client, session_id, content=b"UNIQUE-RESUME-CONTENT-123")

    assert response.status_code == 200
    assert response.json()["candidate_profile"] == EXTRACTED
    assert stored_profile(db, session_id) == EXTRACTED
    assert "UNIQUE-RESUME-CONTENT-123" in llm.prompts[0]  # the actual resume reached the model...
    assert "UNIQUE-RESUME-CONTENT-123" not in str(stored_profile(db, session_id))  # ...but is not stored


def test_resume_upload_replaces_an_earlier_profile_before_questions_exist(api_client: TestClient, db: Session, llm: FakeLLM) -> None:
    session_id = create(api_client)
    llm.replies.append(EXTRACTED)

    assert upload(api_client, session_id).status_code == 200
    assert stored_profile(db, session_id) == EXTRACTED


def test_resume_upload_for_an_unknown_session_returns_404(api_client: TestClient, llm: FakeLLM) -> None:
    assert upload(api_client, str(uuid.uuid4())).status_code == 404


@pytest.mark.parametrize(
    "name, content, status_code",
    [("resume.docx", b"x", 415), ("resume.txt", b"", 422), ("resume.txt", b"  \n ", 422), ("resume.pdf", b"plain text", 422), ("resume.txt", b"\x80\x81bad", 422)],
)
def test_bad_uploads_are_rejected_and_leave_the_profile_unchanged(
    api_client: TestClient, db: Session, llm: FakeLLM, name: str, content: bytes, status_code: int
) -> None:
    session_id = create(api_client)

    response = upload(api_client, session_id, name, content)

    assert response.status_code == status_code
    assert response.json()["detail"]
    assert stored_profile(db, session_id) == PROFILE
    assert llm.prompts == []


def test_oversize_upload_returns_413(api_client: TestClient, llm: FakeLLM, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_RESUME_BYTES", "10")
    get_settings.cache_clear()
    try:
        assert upload(api_client, create(api_client), content=b"x" * 11).status_code == 413
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_resume_upload_without_a_key_returns_a_clear_503(api_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()
    try:
        session_id = create(api_client)
        response = upload(api_client, session_id)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]
    assert stored_profile(db, session_id) == PROFILE


@pytest.mark.parametrize(
    "queued, status_code",
    [
        ([{"skills": "wrong"}, {"skills": "still wrong"}], 502),
        ([{"summary": None, "skills": [], "technologies": [], "experience": []}] * 2, 422),
        ([LLMRateLimited("slow down")], 429),
        ([LLMTimeout("timed out")], 504),
        ([LLMProviderError("provider down")], 502),
    ],
)
def test_model_failures_map_to_http_errors_and_keep_the_old_profile(
    api_client: TestClient, db: Session, llm: FakeLLM, queued: list, status_code: int
) -> None:
    session_id = create(api_client)
    llm.replies.extend(queued)

    response = upload(api_client, session_id)

    assert response.status_code == status_code
    assert stored_profile(db, session_id) == PROFILE


# --- Question generation ---


def test_generation_persists_validated_questions_with_real_source_references(
    api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str
) -> None:
    session_id = create(api_client)
    llm.replies.append(QUESTIONS)

    response = api_client.post(f"/api/interviews/{session_id}/questions")

    assert response.status_code == 201
    questions = response.json()
    assert [q["position"] for q in questions] == [1, 2, 3, 4, 5]
    assert questions[0]["difficulty"] == "medium" and questions[0]["topic"] == "topic 1"
    collection = get_collection(seeded_knowledge)
    assert collection is not None
    for q in questions:
        assert len(q["source_chunks"]) == 2
        for ref in q["source_chunks"]:
            stored = collection.get(ids=[ref["chunk_id"]], include=["metadatas"])
            assert stored["ids"] == [ref["chunk_id"]]  # the chunk really exists in the knowledge base
            assert stored["metadatas"][0]["page"] == ref["page"]
            assert stored["metadatas"][0]["source_file"] == ref["source_file"]
    assert question_rows(db, session_id) == 5
    assert api_client.get(f"/api/interviews/{session_id}").json()["status"] == "in_progress"
    assert api_client.get(f"/api/interviews/{session_id}/questions").json() == questions
    prompt = llm.prompts[0]
    assert "query tuning" in prompt and ROLE in prompt  # built from the session's own data
    assert "Database indexes speed up queries" in prompt  # and from passages retrieved at runtime


def test_the_cited_passage_text_is_saved_but_never_returned_by_the_api(
    api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str
) -> None:
    session_id = create(api_client)
    llm.replies.append(QUESTIONS)

    post = api_client.post(f"/api/interviews/{session_id}/questions")
    listing = api_client.get(f"/api/interviews/{session_id}/questions")

    assert post.status_code == 201
    for response in (post, listing):
        for q in response.json():
            assert all("text" not in ref for ref in q["source_chunks"])  # metadata only
    collection = get_collection(seeded_knowledge)
    assert collection is not None
    db.expire_all()
    saved = db.scalars(select(InterviewQuestion).where(InterviewQuestion.session_id == uuid.UUID(session_id))).all()
    for row in saved:
        for ref in row.source_chunks:
            stored = collection.get(ids=[ref["chunk_id"]], include=["documents"])
            assert ref["text"] == stored["documents"][0]  # the snapshot equals the retrieved passage
            assert ref["text"] in llm.prompts[0]  # and it is what the model was shown


def test_generating_twice_returns_409_and_adds_nothing(api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str) -> None:
    session_id = create(api_client)
    llm.replies.append(QUESTIONS)
    assert api_client.post(f"/api/interviews/{session_id}/questions").status_code == 201

    response = api_client.post(f"/api/interviews/{session_id}/questions")

    assert response.status_code == 409
    assert question_rows(db, session_id) == 5
    assert len(llm.prompts) == 1


def test_generation_requires_a_candidate_profile(api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str) -> None:
    session_id = create(api_client, profile=None)

    response = api_client.post(f"/api/interviews/{session_id}/questions")

    assert response.status_code == 409
    assert "Upload a resume" in response.json()["detail"]
    assert llm.prompts == []


def test_unknown_session_returns_404_for_both_question_routes(api_client: TestClient, llm: FakeLLM) -> None:
    unknown = uuid.uuid4()

    assert api_client.post(f"/api/interviews/{unknown}/questions").status_code == 404
    assert api_client.get(f"/api/interviews/{unknown}/questions").status_code == 404


def test_listing_questions_for_a_new_session_returns_an_empty_list(api_client: TestClient, llm: FakeLLM) -> None:
    assert api_client.get(f"/api/interviews/{create(api_client)}/questions").json() == []


def test_empty_knowledge_base_blocks_generation_with_an_actionable_message(
    api_client: TestClient, db: Session, llm: FakeLLM, rag_collection: str
) -> None:
    session_id = create(api_client)

    response = api_client.post(f"/api/interviews/{session_id}/questions")

    assert response.status_code == 422
    assert "knowledge base is empty" in response.json()["detail"]
    assert "ingest" in response.json()["detail"]
    assert question_rows(db, session_id) == 0
    assert llm.prompts == []  # the model was never called, so nothing ungrounded was generated


def test_insufficient_relevant_knowledge_blocks_generation(api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str) -> None:
    session_id = create(api_client, profile={"technologies": ["xylophone"]}, role="zzz qqq")

    response = api_client.post(f"/api/interviews/{session_id}/questions")

    assert response.status_code == 422
    assert "sufficiently relevant" in response.json()["detail"]
    assert question_rows(db, session_id) == 0
    assert llm.prompts == []


def test_unreachable_knowledge_base_returns_503(api_client: TestClient, db: Session, llm: FakeLLM, monkeypatch: pytest.MonkeyPatch) -> None:
    def down() -> int:
        raise KnowledgeBaseError("Cannot connect to Chroma")

    monkeypatch.setattr("app.question_generation.indexed_chunk_count", down)
    session_id = create(api_client)

    response = api_client.post(f"/api/interviews/{session_id}/questions")

    assert response.status_code == 503
    assert question_rows(db, session_id) == 0


@pytest.mark.parametrize(
    "queued, status_code",
    [
        ([LLMProviderError("down")], 502),
        ([LLMRateLimited("slow")], 429),
        ([LLMTimeout("slow")], 504),
        ([{"questions": []}, {"questions": []}], 502),  # invalid twice
        ([{"questions": [{**QUESTIONS["questions"][0], "source_refs": [99]}] * 5}] * 2, 502),  # invented reference
    ],
)
def test_model_failures_leave_no_partial_interview(
    api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str, queued: list, status_code: int
) -> None:
    session_id = create(api_client)
    llm.replies.extend(queued)

    response = api_client.post(f"/api/interviews/{session_id}/questions")

    assert response.status_code == status_code
    assert question_rows(db, session_id) == 0
    assert api_client.get(f"/api/interviews/{session_id}").json()["status"] == "created"


def test_a_failed_attempt_can_be_retried(api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str) -> None:
    session_id = create(api_client)
    llm.replies.extend([LLMProviderError("down"), QUESTIONS])

    assert api_client.post(f"/api/interviews/{session_id}/questions").status_code == 502
    assert api_client.post(f"/api/interviews/{session_id}/questions").status_code == 201
    assert question_rows(db, session_id) == 5


def test_generation_without_a_key_returns_a_clear_503(
    api_client: TestClient, db: Session, seeded_knowledge: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = create(api_client)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()
    try:
        response = api_client.post(f"/api/interviews/{session_id}/questions")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.json()["detail"]
    assert question_rows(db, session_id) == 0


def test_invented_source_ids_from_the_model_are_never_stored(
    api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str
) -> None:
    session_id = create(api_client)
    forged = {
        "questions": [
            {**q, "chunk_id": "forged-chunk", "source_chunks": [{"chunk_id": "forged-chunk", "page": 999, "source_title": "Forged"}]}
            for q in QUESTIONS["questions"]
        ]
    }
    llm.replies.append(forged)

    response = api_client.post(f"/api/interviews/{session_id}/questions")

    assert response.status_code == 201
    assert "forged" not in response.text.lower()
    db.expire_all()
    assert "forged" not in str([q.source_chunks for q in db.scalars(select(InterviewQuestion))]).lower()


def test_a_concurrent_generation_cannot_create_duplicate_questions(
    api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str
) -> None:
    session_id = create(api_client)

    class RacingLLM(FakeLLM):
        def complete_json(self, system: str, user: str, temperature: float = 0.2) -> dict:
            with SessionLocal() as other:  # another request finishes while this one waits for the model
                other.add_all(
                    InterviewQuestion(session_id=uuid.UUID(session_id), position=i, question_text=f"concurrent {i}") for i in range(1, 6)
                )
                other.commit()
            return super().complete_json(system, user, temperature)

    racing = RacingLLM(QUESTIONS)
    app.dependency_overrides[get_llm] = lambda: racing

    response = api_client.post(f"/api/interviews/{session_id}/questions")

    assert response.status_code == 409
    assert question_rows(db, session_id) == 5  # only the concurrent set exists


def test_resume_upload_after_questions_exist_returns_409(api_client: TestClient, db: Session, llm: FakeLLM, seeded_knowledge: str) -> None:
    session_id = create(api_client)
    llm.replies.append(QUESTIONS)
    api_client.post(f"/api/interviews/{session_id}/questions")

    response = upload(api_client, session_id)

    assert response.status_code == 409
    assert stored_profile(db, session_id) == PROFILE
