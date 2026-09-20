"""
Tailoring agent — generates JD-aligned resume bullets using Claude,
constrained to ONLY rephrase facts already present in the original resume.
"""
from __future__ import annotations
import json, difflib, logging, os, re
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
_SYSTEM_PROMPT = """You are a resume-tailoring assistant. Given a job description's required skills and a candidate's raw resume text, rewrite up to 5 resume bullet points that emphasize relevant experience. CRITICAL PARAPHRASING RULES: Never output a sentence that shares more than 5 consecutive words with the original resume text. Do not copy the original sentence structure. STRICT RULES: Only use facts, skills, numbers, and tools that literally appear in the original resume text. Do not invent, assume, or add anything. Return ONLY this JSON, no extra text: {"bullets": ["bullet 1", "bullet 2",...]}"""
_USER_TEMPLATE = """Job description requires: {skills}\n\nOriginal resume text:\n{resume_text}\n\nGenerate tailored bullets using ONLY facts from the resume text above."""
def _call_llm(system_prompt: str, user_content: str) -> str:
    logger.info("Tailoring Gemini call: model=gemini-2.0-flash")
    client = _get_client()
    response = client.models.generate_content(model="gemini-2.0-flash", contents=user_content, config={"system_instruction": system_prompt})
    logger.info("Tailoring raw response: %r", response.text)
    return response.text
def generate_tailored_bullets(jd_json, resume_text, max_bullets=5):
    skills = jd_json.get("must_have_skills", []) + jd_json.get("nice_have_skills", [])
    try:
        user_prompt = _USER_TEMPLATE.format(skills=", ".join(skills), resume_text=resume_text[:8000])
        raw = _call_llm(_SYSTEM_PROMPT, user_prompt)
        bullets = _parse_response(raw)[:max_bullets]
        final = _validate_and_retry_bullets(bullets, skills, resume_text, max_bullets)
        return final
    except Exception as exc:
        logger.exception("Tailoring unavailable: %s", exc)
        return []
def _validate_and_retry_bullets(bullets, skills, resume_text, max_bullets):
    final = []
    for bullet in bullets:
        candidate = bullet
        ratio, _ = _closest_sentence_ratio(candidate, resume_text)
        if ratio >= 0.85:
            try:
                retry_raw = _call_llm(f"{_SYSTEM_PROMPT}\n\nYour previous attempt was too similar: '{candidate}'. Rephrase completely.", _USER_TEMPLATE.format(skills=", ".join(skills), resume_text=resume_text[:8000]))
                retry_bullets = _parse_response(retry_raw)
                candidate = retry_bullets[0] if retry_bullets else ""
                ratio, _ = _closest_sentence_ratio(candidate, resume_text)
            except:
                candidate = ""
        if not candidate or ratio >= 0.85:
            continue
        if verify_bullet(candidate, resume_text)["approved"]:
            final.append(candidate)
        if len(final) >= max_bullets:
            break
    return final
def _closest_sentence_ratio(bullet, resume_text):
    normalized_bullet = " ".join(bullet.lower().split())
    best_ratio = 0.0; best_sentence = None
    for sentence in re.split(r"\n+|(?<=[.!?])\s+", resume_text):
        normalized_sentence = " ".join(sentence.lower().split())
        if not normalized_sentence: continue
        ratio = difflib.SequenceMatcher(None, normalized_bullet, normalized_sentence, autojunk=False).ratio()
        if ratio > best_ratio:
            best_ratio = ratio; best_sentence = sentence.strip()
    return best_ratio, best_sentence
def _parse_response(raw: str):
    fence = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)
    match = fence.search(raw.strip())
    cleaned = match.group(1) if match else raw
    try:
        data = json.loads(cleaned)
        return list(data.get("bullets") or [])
    except:
        return []
