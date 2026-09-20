"""
LLM client -- wraps Groq for structured JD extraction.

Fallback chain:
    1. Groq returns valid JSON -> normalise + regex override.
    2. Groq returns JSON wrapped in markdown -> strip fences, retry parse.
    3. JSON parse still fails -> full regex fallback.
"""
from __future__ import annotations
import json, logging, os, re
from typing import Any
from groq import Groq
logger = logging.getLogger(__name__)
_client = None
def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client
_EXPERIENCE_RE = re.compile(r"(\d+)\s*\+?\s*(?:years|yrs|year)(?:\s+of)?(?:\s+experience)?", re.IGNORECASE)
_KNOWN_SKILLS = ("python","fastapi","aws","azure","gcp","docker","kubernetes","javascript","typescript","java","go","rust","react","node.js","sql","postgresql","mysql","mongodb","redis","terraform","git","graphql","pandas","numpy","pytorch","tensorflow","jenkins")
_SYSTEM_PROMPT = """You are a strict JSON extractor. Given a Job Description, extract:\n{\n "must_have_skills": [skills marked as required/must have],\n "nice_have_skills": [preferred/bonus skills],\n "min_experience_years": int (0 if not found),\n "location": str,\n "role_title": str\n}\nRules: Return ONLY JSON. Lowercase all skills. If ambiguous, put in must_have. Never invent."""
_USER_TEMPLATE = "Extract the structured information from the following job description:\n\n{jd_text}"
def _call_llm(system_prompt: str, user_content: str) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=1024,
    )
    return response.choices[0].message.content
def extract_jd(jd_text: str) -> dict[str, Any]:
    try:
        raw_response = _call_llm(_SYSTEM_PROMPT, _USER_TEMPLATE.format(jd_text=jd_text))
        return _parse_claude_response(raw_response, jd_text)
    except Exception as exc:
        logger.warning("Groq unavailable: %s. Using regex fallback.", exc)
        return _regex_fallback(jd_text)
extract_jd_with_claude = extract_jd
def _parse_claude_response(raw: str, jd_text: str) -> dict[str, Any]:
    cleaned = _strip_markdown_fences(raw).strip()
    try:
        data = json.loads(cleaned)
        return _normalise(data, jd_text)
    except json.JSONDecodeError:
        return _regex_fallback(jd_text)
def _strip_markdown_fences(text: str) -> str:
    fence_re = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)
    match = fence_re.search(text.strip())
    return match.group(1) if match else text
def _normalise(data: dict[str, Any], jd_text: str) -> dict[str, Any]:
    llm_years = int(data.get("min_experience_years") or 0)
    min_years = _regex_override_experience(jd_text, llm_years)
    return {"must_have_skills": [s.lower() for s in (data.get("must_have_skills") or [])], "nice_have_skills": [s.lower() for s in (data.get("nice_have_skills") or [])], "min_experience_years": min_years, "location": str(data.get("location") or ""), "role_title": str(data.get("role_title") or "")}
def _regex_override_experience(jd_text: str, llm_years: int) -> int:
    if llm_years != 0: return llm_years
    match = _EXPERIENCE_RE.search(jd_text)
    return int(match.group(1)) if match else 0
def _regex_fallback(jd_text: str) -> dict[str, Any]:
    match = _EXPERIENCE_RE.search(jd_text)
    min_years = int(match.group(1)) if match else 0
    lowered = jd_text.lower()
    skills = [skill for skill in _KNOWN_SKILLS if skill in lowered]
    return {"must_have_skills": skills, "nice_have_skills": [], "min_experience_years": min_years, "location": "", "role_title": ""}
