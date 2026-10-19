import uuid
from datetime import datetime
from typing import Annotated

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
