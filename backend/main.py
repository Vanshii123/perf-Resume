"""
FastAPI application — Resume & JD extraction API.

Endpoints:
  POST /upload-resume  — upload a PDF, get back resume_id + raw_text
  POST /extract-jd     — send JD text, get structured JSON via Bedrock Claude
  
"""

from __future__ import annotations
from dotenv import load_dotenv
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

load_dotenv(Path(__file__).with_name(".env"))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.models import AnalyzeRequest, AnalyzeResponse, JDRequest, JDResponse, ResumeUploadResponse
from backend.services.bedrock_client import extract_jd as extract_jd_service
from backend.services.pdf_extractor import extract_text_from_pdf

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("backend.services.tailor").setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Resume-JD API starting up.")
    yield
    logger.info("Resume-JD API shut down.")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Resume & JD Extraction API",
    description=(
        "Upload a PDF resume to extract raw text, "
        "or submit a job description to receive structured skill/experience data."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PDF_SIZE_MB = 10
MAX_PDF_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post(
    "/upload-resume",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload a PDF resume and extract its text",
    tags=["Resume"],
)
async def upload_resume(
    file: UploadFile = File(..., description="PDF resume file"),
) -> ResumeUploadResponse:
    """
    Accept a PDF resume, extract plain text with PyMuPDF, and return a
    unique ``resume_id`` along with the ``raw_text``.

    - **file**: multipart/form-data PDF upload (max 10 MB).

    Raises HTTP 400 if the file is not a PDF or cannot be parsed.
    Raises HTTP 413 if the file exceeds the size limit.
    """
    # --- Content-type guard ---
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Expected a PDF file, got '{file.content_type}'.",
        )

    pdf_bytes = await file.read()

    # --- Size guard ---
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the {MAX_PDF_SIZE_MB} MB limit.",
        )

    logger.info("Received PDF '%s' (%d bytes).", file.filename, len(pdf_bytes))

    # --- Extract text ---
    try:
        raw_text = extract_text_from_pdf(pdf_bytes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    resume_id = str(uuid.uuid4())
    logger.info("Extracted %d chars from PDF. resume_id=%s", len(raw_text), resume_id)

    return ResumeUploadResponse(resume_id=resume_id, raw_text=raw_text)


@app.post(
    "/extract-jd",
    response_model=JDResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract structured data from a job description",
    tags=["Job Description"],
)
async def extract_jd(payload: JDRequest) -> JDResponse:
    """
    Accept raw job-description text and return structured fields extracted
    by **Claude Haiku** via AWS Bedrock.

    Falls back to local extraction if Anthropic is
    unavailable or returns malformed JSON.

    - **jd_text**: The full job-description text (minimum 10 characters).
    """
    logger.info("Extracting JD — text length: %d chars.", len(payload.jd_text))

    structured = extract_jd_service(payload.jd_text)

    logger.info(
        "JD extraction complete. role='%s', min_exp=%d yrs.",
        structured.get("role_title"),
        structured.get("min_experience_years", 0),
    )

    return JDResponse(**structured)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"], summary="Liveness probe")
async def health() -> dict:
    return {"status": "ok"}
from backend.services.resume_parser import parse_resume
from backend.services.scorer import score_fit
from backend.services.tailor import generate_tailored_bullets
from backend.services.verify_bullet import verify_bullet

# ... (baaki imports/routes waise hi rehne do)

@app.post(
    "/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload resume PDF + JD text, get full analysis",
    tags=["Analyze"],
)
async def analyze(
    jd_text: str = Form(..., min_length=10),
    resume_file: UploadFile = File(..., description="PDF resume file"),
) -> AnalyzeResponse:
    logger.info("Starting full analyze pipeline.")

    if resume_file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Expected a PDF file, got '{resume_file.content_type}'.",
        )

    pdf_bytes = await resume_file.read()
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the {MAX_PDF_SIZE_MB} MB limit.",
        )

    try:
        resume_text = extract_text_from_pdf(pdf_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    jd_json = extract_jd_service(jd_text)
    resume_json = parse_resume(resume_text)
    score_result = score_fit(jd_json, resume_json)

    logger.info("Calling generate_tailored_bullets with jd_json and resume_text.")
    raw_bullets = generate_tailored_bullets(jd_json, resume_text)
    logger.info("generate_tailored_bullets returned %d bullets: %r", len(raw_bullets), raw_bullets)
    bullet_results = []
    for bullet in raw_bullets:
        verdict = verify_bullet(bullet, resume_text)
        bullet_results.append({
            "bulletText": bullet,
            "approved": verdict["approved"],
            "unsupported_claims": verdict["unsupported_claims"],
            "claim_matches": verdict["claim_matches"],
        })

    response = AnalyzeResponse(scoreResult=score_result, bulletResults=bullet_results)
    logger.info("/analyze response: score=%r bulletResults=%r", score_result, bullet_results)
    return response