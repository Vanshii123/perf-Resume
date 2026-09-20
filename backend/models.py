"""
Pydantic models for Job Description and Resume domain objects.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Job Description models
# ---------------------------------------------------------------------------

class JDRequest(BaseModel):
    """Incoming payload for /extract-jd."""
    jd_text: str = Field(..., min_length=10, description="Raw job-description text")


class JDResponse(BaseModel):
    """Structured output returned after parsing a job description."""
    must_have_skills: List[str] = Field(default_factory=list)
    nice_have_skills: List[str] = Field(default_factory=list)
    min_experience_years: int = Field(default=0, ge=0)
    location: str = Field(default="")
    role_title: str = Field(default="")


# ---------------------------------------------------------------------------
# Resume models
# ---------------------------------------------------------------------------

class ExperienceEntry(BaseModel):
    """A single work-history entry inside a resume."""
    role: str = Field(default="")
    years: float = Field(default=0.0, ge=0)
    bullets: List[str] = Field(default_factory=list)


class ResumeUploadResponse(BaseModel):
    """Response returned after uploading and parsing a PDF resume."""
    resume_id: str = Field(..., description="UUID identifying this resume upload")
    raw_text: str = Field(..., description="Full extracted text from the PDF")


class ResumeStructured(BaseModel):
    """
    Optional: fully-structured resume payload (used if a /parse-resume
    endpoint is added later).
    """
    resume_id: str
    skills: List[str] = Field(default_factory=list)
    experience: List[ExperienceEntry] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)
    total_years: float = Field(default=0.0, ge=0)


# ---------------------------------------------------------------------------
# Generic error model
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    detail: str
class AnalyzeRequest(BaseModel):
    jd_text: str = Field(..., min_length=10)
    resume_text: str = Field(..., min_length=10)


class ClaimMatch(BaseModel):
    claim: str
    supported: bool
    best_match_sentence: Optional[str] = None


class BulletResult(BaseModel):
    bulletText: str
    approved: bool
    unsupported_claims: List[str] = Field(default_factory=list)
    claim_matches: List[ClaimMatch] = Field(default_factory=list)


class ScoreBreakdownItem(BaseModel):
    jd_requirement: str
    matched: bool
    matched_resume_line: Optional[str] = None
    confidence: Optional[float] = None


class ScoreResult(BaseModel):
    score: int
    breakdown: List[ScoreBreakdownItem]
    missing_skills: List[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    scoreResult: ScoreResult
    bulletResults: List[BulletResult]