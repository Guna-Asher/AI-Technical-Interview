import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import InterviewSession

# Synthetic values used only to exercise the API.
PROFILE = {
    "summary": "synthetic summary",
    "skills": ["skill-a", "skill-b"],
    "technologies": ["tech-a"],
    "experience": ["did thing-a at company-a"],
}


def test_create_interview_with_role_and_profile(api_client: TestClient) -> None:
    response = api_client.post("/api/interviews", json={"role": "synthetic role", "candidate_profile": PROFILE})

    assert response.status_code == 201
    body = response.json()
    uuid.UUID(body["id"])
    assert body["role"] == "synthetic role"
    assert body["status"] == "created"
    assert body["candidate_profile"] == PROFILE
    assert body["completed_at"] is None


def test_create_interview_with_role_only(api_client: TestClient) -> None:
    response = api_client.post("/api/interviews", json={"role": "synthetic role"})

    assert response.status_code == 201
    assert response.json()["candidate_profile"] is None


@pytest.mark.parametrize("role", ["zz-not-a-known-role", "Ünïcödé rôle ✓", "x" * 100])
def test_any_role_is_accepted(api_client: TestClient, role: str) -> None:
    response = api_client.post("/api/interviews", json={"role": role})

    assert response.status_code == 201
    assert response.json()["role"] == role


def test_get_interview_returns_saved_session(api_client: TestClient) -> None:
    created = api_client.post("/api/interviews", json={"role": "synthetic role", "candidate_profile": PROFILE}).json()

    response = api_client.get(f"/api/interviews/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_unknown_interview_returns_404(api_client: TestClient) -> None:
    response = api_client.get(f"/api/interviews/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Interview session not found"}


def test_get_malformed_id_returns_422(api_client: TestClient) -> None:
    assert api_client.get("/api/interviews/not-a-uuid").status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"role": ""},
        {"role": "   "},
        {"role": "x" * 101},
        {"role": 123},
        {"role": "r", "unexpected": True},
        {"role": "r", "candidate_profile": {"skills": "not-a-list"}},
        {"role": "r", "candidate_profile": {"skills": [""]}},
        {"role": "r", "candidate_profile": {"unknown_field": 1}},
    ],
)
def test_invalid_create_requests_are_rejected(api_client: TestClient, db: Session, payload: dict) -> None:
    response = api_client.post("/api/interviews", json=payload)

    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(InterviewSession)) == 0


def test_created_interview_is_persisted_in_postgres(api_client: TestClient) -> None:
    created = api_client.post(
        "/api/interviews", json={"role": "  synthetic role  ", "candidate_profile": PROFILE}
    ).json()

    with SessionLocal() as fresh_session:  # a different connection than the request used
        row = fresh_session.get(InterviewSession, uuid.UUID(created["id"]))

        assert row is not None
        assert row.role == "synthetic role"
        assert row.status == "created"
        assert row.candidate_profile == PROFILE
