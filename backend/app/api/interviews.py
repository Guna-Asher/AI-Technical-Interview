import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import InterviewSession
from app.schemas import InterviewCreate, InterviewRead

router = APIRouter(prefix="/interviews", tags=["interviews"])


@router.post("", response_model=InterviewRead, status_code=status.HTTP_201_CREATED)
def create_interview(payload: InterviewCreate, db: Session = Depends(get_db)) -> InterviewSession:
    """Create an interview session from the client-supplied role and optional profile."""
    profile = payload.candidate_profile
    interview = InterviewSession(
        role=payload.role,
        candidate_profile=profile.model_dump() if profile is not None else None,
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)
    return interview


@router.get("/{session_id}", response_model=InterviewRead)
def get_interview(session_id: uuid.UUID, db: Session = Depends(get_db)) -> InterviewSession:
    interview = db.get(InterviewSession, session_id)
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found")
    return interview
