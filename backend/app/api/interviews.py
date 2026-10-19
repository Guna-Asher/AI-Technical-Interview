import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.models import CandidateAnswer, InterviewQuestion, InterviewSession, InterviewStatus
from app.openrouter import (
    LLMBadResponse,
    LLMError,
    LLMNotConfigured,
    LLMProviderError,
    LLMRateLimited,
    LLMTimeout,
    OpenRouterClient,
    get_llm,
)
from app.question_generation import NoRelevantKnowledge, gather_context, generate_questions
from app.rag.store import KnowledgeBaseError
from app.resume import ResumeError, extract_profile, extract_resume_text
from app.schemas import AnswerCreate, AnswerRead, CandidateProfile, InterviewCreate, InterviewRead, QuestionRead

router = APIRouter(prefix="/interviews", tags=["interviews"])

_LLM_STATUS = {
    LLMNotConfigured: status.HTTP_503_SERVICE_UNAVAILABLE,
    LLMRateLimited: status.HTTP_429_TOO_MANY_REQUESTS,
    LLMTimeout: status.HTTP_504_GATEWAY_TIMEOUT,
    LLMProviderError: status.HTTP_502_BAD_GATEWAY,
    LLMBadResponse: status.HTTP_502_BAD_GATEWAY,
}


def _llm_http_error(exc: LLMError) -> HTTPException:
    return HTTPException(_LLM_STATUS.get(type(exc), status.HTTP_502_BAD_GATEWAY), detail=str(exc))


def _get_session_or_404(db: Session, session_id: uuid.UUID) -> InterviewSession:
    interview = db.get(InterviewSession, session_id)
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found")
    return interview


def _question_count(db: Session, session_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(InterviewQuestion).where(InterviewQuestion.session_id == session_id)) or 0


def _load_questions(db: Session, session_id: uuid.UUID) -> list[InterviewQuestion]:
    """A session's questions in order, each with its saved answer (if any), in two queries."""
    return list(
        db.scalars(
            select(InterviewQuestion)
            .where(InterviewQuestion.session_id == session_id)
            .options(selectinload(InterviewQuestion.answer))
            .order_by(InterviewQuestion.position)
            .execution_options(populate_existing=True)
        )
    )


def _existing_answer(db: Session, question_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(select(CandidateAnswer.id).where(CandidateAnswer.question_id == question_id))


def _lock_session(db: Session, session_id: uuid.UUID) -> InterviewSession:
    """Re-read the session row with a row lock, so concurrent writers to the same session are serialised."""
    return db.execute(
        select(InterviewSession).where(InterviewSession.id == session_id).with_for_update().execution_options(populate_existing=True)
    ).scalar_one()


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
    return _get_session_or_404(db, session_id)


@router.post("/{session_id}/resume", response_model=InterviewRead)
def upload_resume(
    session_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    llm: OpenRouterClient = Depends(get_llm),
) -> InterviewSession:
    """Extract a structured candidate profile from a PDF or TXT resume and save it on the session.

    The file is processed in memory; only the extracted profile is stored.
    """
    settings = get_settings()
    _get_session_or_404(db, session_id)
    if _question_count(db, session_id) > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Questions were already generated, so the resume can no longer be replaced")

    data = file.file.read(settings.max_resume_bytes + 1)
    try:
        text = extract_resume_text(file.filename, data, max_bytes=settings.max_resume_bytes, max_chars=settings.max_resume_chars)
        profile = extract_profile(llm, text)
    except ResumeError as exc:
        raise HTTPException(exc.status_code, detail=str(exc)) from exc
    except LLMError as exc:
        raise _llm_http_error(exc) from exc

    interview = _lock_session(db, session_id)
    if _question_count(db, session_id) > 0:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Questions were already generated, so the resume can no longer be replaced")
    interview.candidate_profile = profile.model_dump()
    db.commit()
    db.refresh(interview)
    return interview


@router.post("/{session_id}/questions", response_model=list[QuestionRead], status_code=status.HTTP_201_CREATED)
def generate_interview_questions(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    llm: OpenRouterClient = Depends(get_llm),
) -> list[InterviewQuestion]:
    """Generate questions from the session's role and profile, grounded in passages retrieved at runtime."""
    settings = get_settings()
    interview = _get_session_or_404(db, session_id)
    if _question_count(db, session_id) > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Questions have already been generated for this interview")
    if not interview.candidate_profile:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This interview has no candidate profile. Upload a resume first, or create the session with a candidate profile",
        )
    role = interview.role
    profile = CandidateProfile.model_validate(interview.candidate_profile)

    try:
        passages = gather_context(role, profile)
        questions = generate_questions(llm, role, profile, passages, settings.question_count)
    except NoRelevantKnowledge as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except KnowledgeBaseError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"The knowledge base is unavailable: {exc}") from exc
    except LLMError as exc:
        raise _llm_http_error(exc) from exc

    # Nothing has been written yet. Save the whole set in one transaction, or nothing.
    conflict = HTTPException(status.HTTP_409_CONFLICT, detail="Questions have already been generated for this interview")
    locked = _lock_session(db, session_id)
    if _question_count(db, session_id) > 0:
        db.rollback()
        raise conflict
    rows = [
        InterviewQuestion(
            session_id=session_id,
            position=q.position,
            question_text=q.question_text,
            topic=q.topic,
            difficulty=q.difficulty,
            source_chunks=q.source_chunks,
        )
        for q in questions
    ]
    db.add_all(rows)
    locked.status = InterviewStatus.IN_PROGRESS.value
    try:
        db.commit()
    except IntegrityError as exc:  # a concurrent request got there first (unique session_id + position)
        db.rollback()
        raise conflict from exc
    return _load_questions(db, session_id)


@router.get("/{session_id}/questions", response_model=list[QuestionRead])
def list_interview_questions(session_id: uuid.UUID, db: Session = Depends(get_db)) -> list[InterviewQuestion]:
    """The session's questions in order, each with its saved answer or `null`. Used to recover progress."""
    _get_session_or_404(db, session_id)
    return _load_questions(db, session_id)


@router.post(
    "/{session_id}/questions/{question_id}/answer",
    response_model=AnswerRead,
    status_code=status.HTTP_201_CREATED,
)
def submit_answer(
    session_id: uuid.UUID, question_id: uuid.UUID, payload: AnswerCreate, db: Session = Depends(get_db)
) -> CandidateAnswer:
    """Save the candidate's answer to one question. Answers are write-once; a second submission is a 409."""
    _get_session_or_404(db, session_id)
    question = db.get(InterviewQuestion, question_id)
    if question is None or question.session_id != session_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found in this interview")
    already_answered = HTTPException(status.HTTP_409_CONFLICT, detail="This question has already been answered")
    if _existing_answer(db, question_id) is not None:
        raise already_answered

    answer = CandidateAnswer(question_id=question_id, answer_text=payload.answer_text)
    db.add(answer)
    try:
        db.commit()
    except IntegrityError as exc:  # a concurrent request saved an answer first (unique question_id)
        db.rollback()
        raise already_answered from exc
    db.refresh(answer)
    return answer
