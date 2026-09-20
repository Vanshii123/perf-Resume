"""
Resume-to-JD fit scorer — pure Python, zero LLM calls.

Public API
----------
score_fit(jd_json, resume_json) -> dict

Algorithm
---------
For each skill in jd_json["must_have_skills"]:
  1. Search every sentence in resume_json["raw_sentences"] using TWO strategies:
       a. difflib.SequenceMatcher ratio  (character-level similarity)
       b. token_set_ratio               (bag-of-words overlap, handles word order)
     The higher of the two is used as the confidence for that sentence.
  2. Take the sentence with the highest confidence across all sentences.
  3. Hit  if confidence > MATCH_THRESHOLD (0.7), miss otherwise.

Also checks resume_json["skills"] (plain list) as a secondary source before
scanning sentences, so pre-parsed skill lists are not wasted.

Score formula
-------------
  score = clamp((matched / total_must_have * 100) - (exp_gap * 5), 0, 100)

  exp_gap  = max(0, jd_min_years - resume_total_years)
  Both values default to 0 if missing from their respective dicts.
"""
from __future__ import annotations

import difflib
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MATCH_THRESHOLD: float = 0.70   # minimum confidence to count as a hit
EXP_PENALTY_PER_YEAR: int = 5   # score points deducted per year of exp gap


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_fit(jd_json: dict[str, Any], resume_json: dict[str, Any]) -> dict[str, Any]:
    """
    Score how well a parsed resume matches a parsed job description.

    Parameters
    ----------
    jd_json : dict
        Must contain ``"must_have_skills"`` (list[str]).
        May contain ``"min_experience_years"`` (int).
        All skills are expected lowercase (as produced by extract_jd).

    resume_json : dict
        Must contain ``"raw_sentences"`` (list[str]) — the original resume
        sentences used for exact citation.
        May contain:
          - ``"skills"``       (list[str]) — pre-parsed skill tokens
          - ``"total_years"``  (int | float) — total experience

    Returns
    -------
    dict with keys:
        score          : int   — 0-100 composite fit score
        breakdown      : list  — one entry per must-have skill (see below)
        missing_skills : list  — skills that had no match above threshold

    Each breakdown entry:
        {
            "jd_requirement"      : str,          # original JD skill
            "matched"             : bool,
            "matched_resume_line" : str | None,   # EXACT sentence from resume
            "confidence"          : float | None  # 0-1, None if no match
        }
    """
    must_haves: list[str] = jd_json.get("must_have_skills") or []
    raw_sentences: list[str] = resume_json.get("raw_sentences") or []
    resume_skills: list[str] = [s.lower() for s in (resume_json.get("skills") or [])]

    jd_min_years: int = int(jd_json.get("min_experience_years") or 0)
    resume_years: float = float(resume_json.get("total_years") or 0)
    exp_gap: float = max(0.0, jd_min_years - resume_years)

    breakdown: list[dict[str, Any]] = []
    missing: list[str] = []
    matched_count = 0

    for skill in must_haves:
        skill_lower = skill.lower()
        best = _best_match(skill_lower, raw_sentences, resume_skills)

        if best["confidence"] is not None and best["confidence"] >= MATCH_THRESHOLD:
            matched_count += 1
            breakdown.append(
                {
                    "jd_requirement": skill,
                    "matched": True,
                    "matched_resume_line": best["sentence"],
                    "confidence": round(best["confidence"], 4),
                }
            )
        else:
            missing.append(skill)
            breakdown.append(
                {
                    "jd_requirement": skill,
                    "matched": False,
                    "matched_resume_line": None,
                    "confidence": round(best["confidence"], 4) if best["confidence"] else None,
                }
            )

    total = len(must_haves)
    raw_score = (matched_count / total * 100) if total else 0.0
    penalty = exp_gap * EXP_PENALTY_PER_YEAR
    score = int(max(0, min(100, raw_score - penalty)))

    logger.info(
        "score_fit: matched=%d/%d, exp_gap=%.1f yrs, penalty=%.1f pts, score=%d",
        matched_count, total, exp_gap, penalty, score,
    )

    return {
        "score": score,
        "breakdown": breakdown,
        "missing_skills": missing,
    }


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def _best_match(
    skill: str,
    sentences: list[str],
    skill_list: list[str],
) -> dict[str, Any]:
    """
    Return the best-matching sentence for *skill* and its confidence score.

    Sources checked (in order of priority):
      1. Pre-parsed ``skill_list``  — if the skill appears verbatim, return
         a synthetic sentence with confidence 1.0 so it's always a hit.
      2. ``sentences``              — score every sentence; return the one
         with the highest confidence.

    Returns
    -------
    {"sentence": str | None, "confidence": float | None}
    """
    # Fast path: exact token in pre-parsed skill list
    if _token_in_list(skill, skill_list):
        synthetic = f"[skill list] {skill}"
        logger.debug("Skill '%s' found verbatim in resume skill list.", skill)
        return {"sentence": synthetic, "confidence": 1.0}

    best_conf: float = 0.0
    best_sent: str | None = None

    for sentence in sentences:
        conf = _match_confidence(skill, sentence)
        if conf > best_conf:
            best_conf = conf
            best_sent = sentence

    if best_sent is None or best_conf == 0.0:
        return {"sentence": None, "confidence": None}

    return {"sentence": best_sent, "confidence": best_conf}


def _token_in_list(skill: str, skill_list: list[str]) -> bool:
    """True if *skill* appears as a token or substring in *skill_list*."""
    for item in skill_list:
        if skill == item or skill in item.split():
            return True
    return False


def _match_confidence(skill: str, sentence: str) -> float:
    """
    Return the highest of:
      - SequenceMatcher ratio between *skill* and the full sentence
      - SequenceMatcher ratio between *skill* and any individual word token
      - token_set_ratio (pure-Python bag-of-words overlap)

    All comparisons are case-insensitive.
    """
    s_lower = skill.lower()
    sent_lower = sentence.lower()

    # 1. Full-sentence character similarity
    seq_full = difflib.SequenceMatcher(
        None, s_lower, sent_lower, autojunk=False
    ).ratio()

    # 2. Best per-token match (useful for short skills like "aws", "react")
    tokens = re.split(r"\W+", sent_lower)
    seq_token = max(
        (difflib.SequenceMatcher(None, s_lower, tok, autojunk=False).ratio()
         for tok in tokens if tok),
        default=0.0,
    )

    # 3. Token-set ratio (handles word-order variation)
    tsr = _token_set_ratio(s_lower, sent_lower)

    confidence = max(seq_full, seq_token, tsr)
    logger.debug(
        "  skill='%s'  sent='%.60s'  seq_full=%.2f  seq_tok=%.2f  tsr=%.2f  -> %.2f",
        skill, sentence, seq_full, seq_token, tsr, confidence,
    )
    return confidence


def _token_set_ratio(a: str, b: str) -> float:
    """
    Pure-Python equivalent of fuzzywuzzy/rapidfuzz token_set_ratio.

    Steps (mirrors the original algorithm):
      1. Tokenise both strings; compute intersection (sorted) and
         set-differences a-b, b-a.
      2. Build three comparison strings:
           t0 = sorted(intersection)
           t1 = t0 + sorted(a - b)
           t2 = t0 + sorted(b - a)
      3. Return max(ratio(t0, t1), ratio(t0, t2), ratio(t1, t2)).

    This rewards partial matches where all of *a*'s tokens appear in *b*
    even if *b* has many extra words (e.g. skill="python" vs
    sentence="Built API in Python and deployed to AWS").
    """
    def _tokens(s: str) -> list[str]:
        return sorted(re.split(r"\W+", s.strip()))

    tokens_a = set(_tokens(a)) - {""}
    tokens_b = set(_tokens(b)) - {""}

    intersection = tokens_a & tokens_b
    diff_ab = tokens_a - tokens_b
    diff_ba = tokens_b - tokens_a

    t0 = " ".join(sorted(intersection))
    t1 = (t0 + " " + " ".join(sorted(diff_ab))).strip()
    t2 = (t0 + " " + " ".join(sorted(diff_ba))).strip()

    if not t0:
        # No common tokens at all
        return difflib.SequenceMatcher(None, t1, t2, autojunk=False).ratio()

    r01 = difflib.SequenceMatcher(None, t0, t1, autojunk=False).ratio()
    r02 = difflib.SequenceMatcher(None, t0, t2, autojunk=False).ratio()
    r12 = difflib.SequenceMatcher(None, t1, t2, autojunk=False).ratio()

    return max(r01, r02, r12)
