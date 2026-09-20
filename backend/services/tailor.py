"""
Tailoring agent — generates JD-aligned resume bullets using Claude,
constrained to ONLY rephrase facts already present in the original resume.
"""
from __future__ import annotations

import json
import difflib
import logging
import os
import re
from typing import Any

from google import genai
from backend.services.verify_bullet import verify_bullet

logger = logging.getLogger(__name__)

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client

_SYSTEM_PROMPT = """You are a resume-tailoring assistant.
Given a job description's required skills and a candidate's raw resume text,
rewrite up to 5 resume bullet points that emphasize relevant experience.

CRITICAL PARAPHRASING RULES:
- Never output a sentence that shares more than 5 consecutive words with the
    original resume text.
- Do not copy the original sentence structure. Change the subject, verb,
    order, and phrasing while preserving every fact.
- A bullet that is near-verbatim is invalid and must be rewritten before output.

Examples of acceptable paraphrasing:
- Resume: "Built REST APIs in Python using FastAPI."
    JD-aligned: "Delivered FastAPI-powered Python services for RESTful endpoints."
- Resume: "Reduced deployment time by 30% with Docker."
    JD-aligned: "Cut release turnaround 30% by containerizing deployments with Docker."
- Resume: "Managed PostgreSQL databases on AWS."
    JD-aligned: "Operated AWS-hosted PostgreSQL data stores as part of the platform."

STRICT RULES:
- Only use facts, skills, numbers, and tools that literally appear in the
  original resume text. Do not invent, assume, or add anything.
- Do not add metrics/percentages that are not in the original text.
- Do not claim a technology was used unless it is explicitly mentioned.
- Rephrase and reorder wording to align with the JD's language, but never
  introduce new factual content.

Return ONLY this JSON, no extra text:
{"bullets": ["bullet 1", "bullet 2",...]}"""

_USER_TEMPLATE = """Job description requires: {skills}

Original resume text:
{resume_text}

Generate tailored bullets using ONLY facts from the resume text above."""

def _call_llm(system_prompt: str, user_content: str) -> str:
    logger.info("Tailoring Gemini call: model=gemini-flash-latest")
    logger.info("Tailoring system prompt: %s", system_prompt)
    logger.info("Tailoring user prompt: %s", user_content)
    client = _get_client()
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=user_content,
        config={"system_instruction": system_prompt},
    )
    logger.info("Tailoring raw Gemini response: %r", response.text)
    return response.text

def generate_tailored_bullets(
    jd_json: dict[str, Any],
    resume_text: str,
    max_bullets: int = 5,
) -> list[str]:
    logger.info("generate_tailored_bullets called: jd_json=%r, max_bullets=%d", jd_json, max_bullets)
    skills = jd_json.get("must_have_skills", []) + jd_json.get("nice_have_skills", [])
    logger.info("Tailoring skills: %r", skills)
    logger.info("Tailoring resume text length: %d", len(resume_text))
    try:
        user_prompt = _USER_TEMPLATE.format(
            skills=", ".join(skills),
            resume_text=resume_text[:8000],
        )
        logger.info("Tailoring prompt prepared: %s", user_prompt)
        raw = _call_llm(
            _SYSTEM_PROMPT,
            user_prompt,
        )
        logger.info("Tailoring raw response received: %r", raw)
        bullets = _parse_response(raw)[:max_bullets]
        logger.info("Tailoring parsed bullets before validation: %r", bullets)
        final = _validate_and_retry_bullets(bullets, skills, resume_text, max_bullets)
        logger.info("Tailoring final bullets before return: %r", final)
        return final
    except Exception as exc:
        logger.exception("Tailoring unavailable: %s", exc)
        return []

def _validate_and_retry_bullets(
    bullets: list[str],
    skills: list[str],
    resume_text: str,
    max_bullets: int,
) -> list[str]:
    final: list[str] = []
    logger.info("Validating %d generated bullets", len(bullets))
    for bullet in bullets:
        candidate = bullet
        ratio, source_sentence = _closest_sentence_ratio(candidate, resume_text)
        logger.info(
            "Bullet similarity: bullet=%r ratio=%.4f source_sentence=%r",
            candidate,
            ratio,
            source_sentence,
        )
        if ratio >= 0.75:
            retry_system = (
                f"{_SYSTEM_PROMPT}\n\nYour previous attempt was too similar to the original text: "
                f"'{candidate}'. Rephrase it completely differently while keeping the same facts."
            )
            try:
                retry_raw = _call_llm(
                    retry_system,
                    _USER_TEMPLATE.format(
                        skills=", ".join(skills),
                        resume_text=resume_text[:8000],
                    ),
                )
                logger.info("Tailoring retry raw response: %r", retry_raw)
                retry_bullets = _parse_response(retry_raw)
                logger.info("Tailoring retry parsed bullets: %r", retry_bullets)
                candidate = retry_bullets[0] if retry_bullets else ""
                ratio, source_sentence = _closest_sentence_ratio(candidate, resume_text)
                logger.info("Retry bullet similarity: candidate=%r ratio=%.4f", candidate, ratio)
            except Exception as exc:
                logger.exception("Bullet regeneration failed (%s). Dropping copied bullet.", exc)
                candidate = ""

        if not candidate or ratio >= 0.75:
            logger.info("Dropping bullet that failed paraphrasing: %r", candidate)
            continue

        if verify_bullet(candidate, resume_text)["approved"]:
            final.append(candidate)
            logger.info("Bullet approved: %r", candidate)
        else:
            logger.info("Dropping bullet that failed fabrication verification: %r", candidate)

        if len(final) >= max_bullets:
            break

    logger.info("Validated final bullets: %r", final)
    return final

def _closest_sentence_ratio(bullet: str, resume_text: str) -> tuple[float, str | None]:
    normalized_bullet = " ".join(bullet.lower().split())
    best_ratio = 0.0
    best_sentence = None
    for sentence in re.split(r"\n+|(?<=[.!?])\s+", resume_text):
        normalized_sentence = " ".join(sentence.lower().split())
        if not normalized_sentence:
            continue
        ratio = difflib.SequenceMatcher(
            None,
            normalized_bullet,
            normalized_sentence,
            autojunk=False,
        ).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_sentence = sentence.strip()
    return best_ratio, best_sentence

def _parse_response(raw: str) -> list[str]:
    logger.info("Parsing tailoring response raw text: %r", raw)
    fence = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)
    match = fence.search(raw.strip())
    cleaned = match.group(1) if match else raw
    logger.info("Parsing tailoring response after markdown stripping: %r", cleaned)
    try:
        data = json.loads(cleaned)
        logger.info("Parsing tailoring response after json.loads: %r", data)
        bullets = list(data.get("bullets") or [])
        logger.info("Parsing tailoring bullets list: %r", bullets)
        return bullets
    except Exception as exc:
        logger.exception("Tailoring response parsing failed: %s", exc)
        return []
