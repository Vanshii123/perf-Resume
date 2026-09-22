"""Generate JD-aligned resume bullets using Groq and verify every claim."""
from __future__ import annotations
import json, difflib, logging, os, re
from typing import Any
import httpx
from backend.services.verify_bullet import verify_bullet
logger = logging.getLogger(__name__)
_SYSTEM_PROMPT = """You are a resume-tailoring assistant. Given a job description's required skills and a candidate's raw resume text, rewrite up to 5 resume bullet points that emphasize relevant experience. CRITICAL PARAPHRASING RULES: Never output a sentence that shares more than 5 consecutive words with the original resume text. Do not copy the original sentence structure. STRICT RULES: Only use facts, skills, numbers, and tools that literally appear in the original resume text. Do not invent, assume, or add anything. Return ONLY this JSON, no extra text: {"bullets": ["bullet 1", "bullet 2",...]}"""
_USER_TEMPLATE = """Job description requires: {skills}\n\nOriginal resume text:\n{resume_text}\n\nGenerate tailored bullets using ONLY facts from the resume text above."""
def _call_llm(system_prompt: str, user_content: str) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")

    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    logger.info("Tailoring Groq call: model=%s", model)
    response = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        },
        timeout=60.0,
    )
    response.raise_for_status()
    payload = response.json()
    response_text = payload["choices"][0]["message"]["content"] or ""
    logger.info("Tailoring raw response: %r", response_text)
    return response_text
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
        verdict = None
        if ratio >= 0.85:
            logger.info("Rejecting initial bullet for copy similarity: ratio=%.3f", ratio)
        else:
            verdict = verify_bullet(candidate, resume_text)

        if ratio >= 0.85 or not verdict["approved"]:
            try:
                retry_reason = (
                    "too similar to the original resume"
                    if ratio >= 0.85
                    else f"unsupported claims: {verdict['unsupported_claims']}"
                )
                retry_raw = _call_llm(
                    f"{_SYSTEM_PROMPT}\n\nYour previous attempt was rejected for {retry_reason}. Rephrase it completely while using only supported resume facts.",
                    _USER_TEMPLATE.format(skills=", ".join(skills), resume_text=resume_text[:8000]),
                )
                retry_bullets = _parse_response(retry_raw)
                candidate = retry_bullets[0] if retry_bullets else ""
                ratio, _ = _closest_sentence_ratio(candidate, resume_text)
                verdict = verify_bullet(candidate, resume_text) if candidate and ratio < 0.85 else None
            except Exception as exc:
                logger.warning("Tailoring retry failed: %s", exc)
                candidate = ""
                verdict = None

        if not candidate or ratio >= 0.85:
            logger.info("Dropping bullet after validation: copy_ratio=%.3f", ratio)
            continue
        if verdict and verdict["approved"]:
            final.append(candidate)
        else:
            logger.info(
                "Dropping bullet after claim verification: unsupported=%s",
                (verdict or {}).get("unsupported_claims", []),
            )
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
        if not isinstance(data, dict):
            return []
        return [bullet.strip() for bullet in data.get("bullets", []) if isinstance(bullet, str) and bullet.strip()]
    except (TypeError, json.JSONDecodeError):
        return []
