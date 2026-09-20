"""
Resume parser — converts raw extracted text into the structured dict
that scorer.py expects.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any

from google import genai

logger = logging.getLogger(__name__)

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client

_SKILLS_SYSTEM_PROMPT = """\
You are a strict JSON extractor for resumes.
Given raw resume text, extract only a flat list of technical skills (tools, \
languages, frameworks, platforms, methodologies).
Return ONLY this JSON with no extra text:
{"skills": ["skill1", "skill2"]}
Rules: lowercase everything. No soft skills. No job titles. Never invent."""

_SKILLS_USER_TEMPLATE = "Extract skills from this resume:\n\n{text}"

_MONTHS = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
    r"|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_YEAR = r"((?:19|20)\d{2})"

_RE_MONTH_YEAR_RANGE = re.compile(
    rf"{_MONTHS}\s*{_YEAR}\s*[-–—to]+\s*(?:{_MONTHS}\s*)?{_YEAR}|"
    rf"{_MONTHS}\s*{_YEAR}\s*[-–—to]+\s*(present|current|now)",
    re.IGNORECASE,
)
_RE_YEAR_RANGE = re.compile(
    rf"\b{_YEAR}\s*[-–—to]+\s*{_YEAR}|\b{_YEAR}\s*[-–—to]+\s*(present|current|now)",
    re.IGNORECASE,
)
_RE_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_KNOWN_SKILLS = (
    "python", "fastapi", "aws", "azure", "gcp", "docker", "kubernetes",
    "javascript", "typescript", "java", "go", "rust", "react", "node.js",
    "sql", "postgresql", "mysql", "mongodb", "redis", "terraform", "git",
    "graphql", "pandas", "numpy", "pytorch", "tensorflow", "jenkins",
)
_DIRECT_YEARS_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years|yrs|year)\b",
    re.IGNORECASE,
)

def _call_llm(system_prompt: str, user_content: str) -> str:
    client = _get_client()
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=user_content,
        config={"system_instruction": system_prompt},
    )
    return response.text

def parse_resume(raw_text: str) -> dict[str, Any]:
    raw_sentences = _split_sentences(raw_text)
    total_years = _extract_total_years(raw_text)
    skills = _extract_skills(raw_text)

    logger.info(
        "parse_resume: %d sentences, %.1f total_years, %d skills detected.",
        len(raw_sentences), total_years, len(skills),
    )

    return {
        "skills": skills,
        "raw_sentences": raw_sentences,
        "total_years": total_years,
    }

def _split_sentences(text: str) -> list[str]:
    parts = _RE_SENTENCE.split(text)
    return [p.strip() for p in parts if len(p.strip()) >= 5]

def _extract_total_years(text: str) -> float:
    current_year = datetime.now().year
    total: float = 0.0

    for m in _RE_MONTH_YEAR_RANGE.finditer(text):
        groups = [g for g in m.groups() if g is not None]
        years = []
        for g in groups:
            if g.lower() in ("present", "current", "now"):
                years.append(current_year)
            elif re.match(r"^\d{4}$", g):
                years.append(int(g))
        if len(years) >= 2:
            total += max(0, years[-1] - years[0])

    if total == 0.0:
        for m in _RE_YEAR_RANGE.finditer(text):
            groups = [g for g in m.groups() if g is not None]
            years = []
            for g in groups:
                if g.lower() in ("present", "current", "now"):
                    years.append(current_year)
                elif re.match(r"^\d{4}$", g):
                    years.append(int(g))
            if len(years) >= 2:
                total += max(0, years[-1] - years[0])

    if total == 0.0:
        direct_years = _DIRECT_YEARS_RE.search(text)
        if direct_years:
            total = float(direct_years.group(1))

    return round(total, 2)

def _extract_skills(raw_text: str) -> list[str]:
    try:
        raw = _call_llm(_SKILLS_SYSTEM_PROMPT, _SKILLS_USER_TEMPLATE.format(text=raw_text[:8000]))
    except Exception as exc:
        logger.warning("Gemini skill extraction failed (%s). Using local fallback.", exc)
        lowered = raw_text.lower()
        return [skill for skill in _KNOWN_SKILLS if skill in lowered]

    fence = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)
    match = fence.search(raw.strip())
    cleaned = match.group(1) if match else raw

    try:
        data = json.loads(cleaned)
        return [s.lower() for s in (data.get("skills") or [])]
    except json.JSONDecodeError:
        logger.warning("Skill extraction response not valid JSON: %.200s", raw)
        return []
