#verify_bullet.py" - Verify that a generated bullet point is supported by the original resume text.
from __future__ import annotations

import difflib
import logging
import re
from typing import Any

from backend.services.resume_parser import _split_sentences

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SUPPORT_THRESHOLD: float = 0.85   # fuzzy similarity to count as "supported"
COPY_PASTE_THRESHOLD: float = 0.85

# Stopwords to exclude from key-phrase extraction
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "their",
    "its", "it", "this", "that", "these", "those", "i", "we", "our",
    "my", "your", "his", "her", "them", "they", "which", "who", "what",
    "when", "where", "how", "than", "then", "so", "if",
    # Generic resume adjectives — excluded intentionally (not verifiable)
    "scalable", "robust", "efficient", "effective", "dynamic", "strategic",
    "experienced", "skilled", "proven", "strong", "excellent", "key",
    "significant", "innovative", "high", "large", "multiple", "various",
    "cross", "functional", "end", "based",
})

# Regex patterns
_RE_METRIC   = re.compile(r"\b\d[\d,]*(?:\.\d+)?(?:ms|gb|tb|%|[kxm])?\b", re.IGNORECASE)
_RE_PROPER   = re.compile(r"(?<!\.\s)(?<!\n)\b([A-Z][a-zA-Z0-9+#.]{1,})\b")
_RE_TOKENS   = re.compile(r"[a-zA-Z0-9#+.]{2,}")

_GENERIC_ACTIONS = {
    "led", "built", "worked", "developed", "deployed", "managed", "improved",
    "reduced", "increased", "optimized", "created", "delivered", "implemented",
    "achieved", "designed", "maintained", "supported", "scaled", "launched",
    "owned", "mentored", "hired", "trained", "coordinated", "engineered",
}
_GENERIC_NOUNS = {
    "service", "services", "project", "projects", "team", "teams", "system",
    "systems", "platform", "platforms", "product", "products", "workflow",
    "workflows", "process", "processes", "solution", "solutions", "infrastructure",
    "application", "applications", "component", "components", "feature", "features",
    "endpoint", "endpoints",
    "environment", "environments", "initiative", "initiatives", "work", "effort",
    "efforts", "business", "operations"
}
_TECHNICAL_HINTS = {
    "aws", "azure", "gcp", "python", "api", "apis", "kubernetes", "docker",
    "terraform", "sql", "postgres", "mysql", "mongodb", "redis", "node", "javascript",
    "java", "spring", "react", "typescript", "go", "rust", "csharp", "php", "linux",
    "graphql", "rest", "ci", "cd", "jenkins", "airflow", "spark", "hadoop", "pytorch",
    "tensorflow", "pandas", "numpy", "kafka", "snowflake", "dbt", "ml", "llm",
        "model", "models", "ai", "mlops", "restful", "endpoint", "endpoints",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_bullet(
    generated_bullet: str,
    original_resume_text: str,
) -> dict[str, Any]:
    copy_ratio, copy_sentence = _copy_paste_match(generated_bullet, original_resume_text)
    if copy_ratio >= COPY_PASTE_THRESHOLD:
        logger.info("verify_bullet: rejected copy-paste wording (ratio=%.3f).", copy_ratio)
        return {
            "approved": False,
            "unsupported_claims": ["Copied resume wording"],
            "supported_claims": [],
            "claims_checked": [],
            "claim_matches": [{
                "claim": "Copied resume wording",
                "supported": False,
                "best_match_sentence": copy_sentence,
            }],
        }

    claims = _extract_claims(generated_bullet)
    logger.debug("verify_bullet: claims extracted: %s", claims)

    supported: list[str] = []
    unsupported: list[str] = []
    claim_matches: list[dict[str, Any]] = []

    for claim in claims:
        is_supported, best_sentence = _is_supported(claim, original_resume_text)
        if is_supported:
            supported.append(claim)
            logger.debug("  [supported]   %r -> %s", claim, best_sentence)
        else:
            unsupported.append(claim)
            logger.debug("  [UNSUPPORTED] %r", claim)

        claim_matches.append({
            "claim": claim,
            "supported": is_supported,
            "best_match_sentence": best_sentence,
        })

    evidence_sentences = {
        " ".join(match["best_match_sentence"].lower().split())
        for match in claim_matches
        if match["supported"] and match["best_match_sentence"]
    }
    evidence_issue = None
    if not claims:
        evidence_issue = "No verifiable resume evidence"
        unsupported.append(evidence_issue)
        claim_matches.append({
            "claim": evidence_issue,
            "supported": False,
            "best_match_sentence": None,
        })
    elif len(evidence_sentences) > 1:
        evidence_issue = "Claims span multiple resume statements"
        unsupported.append(evidence_issue)
        claim_matches.append({
            "claim": evidence_issue,
            "supported": False,
            "best_match_sentence": None,
        })

    approved = len(unsupported) == 0 and evidence_issue is None

    logger.info(
        "verify_bullet: approved=%s, supported=%d, unsupported=%d, evidence_sources=%d",
        approved, len(supported), len(unsupported), len(evidence_sentences),
    )

    return {
        "approved": approved,
        "unsupported_claims": unsupported,
        "supported_claims": supported,
        "claims_checked": claims,
        "claim_matches": claim_matches,
    }


def _copy_paste_match(bullet: str, original: str) -> tuple[float, str | None]:
    normalized_bullet = " ".join(bullet.lower().split())
    best_ratio = 0.0
    best_sentence = None
    for sentence in _split_sentences(original):
        ratio = difflib.SequenceMatcher(
            None,
            normalized_bullet,
            " ".join(sentence.lower().split()),
            autojunk=False,
        ).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_sentence = sentence
    return best_ratio, best_sentence


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

def _normalize_metric_match(text: str, match: re.Match[str]) -> str:
    value = match.group(0)
    suffixes = ("ms", "gb", "tb", "x", "%", "s", "k", "m")
    pos = match.end()
    if pos < len(text):
        tail = text[pos:]
        for suffix in suffixes:
            if tail.startswith(suffix):
                value += suffix
                break
    return value


def _metric_value(value: str) -> float:
    normalized = value.lower().replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|gb|tb|%|k|x|m)?", normalized)
    if not match:
        return float("nan")
    number = float(match.group(1))
    multiplier = {"k": 1_000, "m": 1_000_000}.get(match.group(2), 1)
    return number * multiplier


def _looks_technical(token: str) -> bool:
    lowered = token.lower()
    if lowered in _TECHNICAL_HINTS:
        return True
    if bool(re.search(r"\d", token)):
        return True
    if token.isupper() and len(token) > 1:
        return True
    if any(ch in token for ch in (".", "#", "/", "+", "-")):
        return True
    return False


def _is_generic_bigram(left: str, right: str) -> bool:
    left_l = left.lower()
    right_l = right.lower()
    if left_l in _GENERIC_ACTIONS and not _looks_technical(right):
        return True
    if right_l in _GENERIC_ACTIONS and not _looks_technical(left):
        return True
    if left_l in _GENERIC_NOUNS or right_l in _GENERIC_NOUNS:
        return True
    if left_l in _STOPWORDS and right_l in _STOPWORDS:
        return True
    return False


def _extract_claims(bullet: str) -> list[str]:
    seen: set[str] = set()
    claims: list[str] = []

    def _add(c: str) -> None:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            claims.append(c)

    for m in _RE_METRIC.finditer(bullet):
        val = _normalize_metric_match(bullet, m)
        digits_only = re.sub(r"\D", "", val)
        if val not in ("0",) and len(digits_only) >= 2:  # skip single-digit noise like "5"
            _add(val)

    words = bullet.split()
    sentence_body = " ".join(words[1:]) if len(words) > 1 else ""
    for m in _RE_PROPER.finditer(sentence_body):
        word = m.group(1)
        if word.lower() not in _STOPWORDS and len(word) > 1:
            _add(word)

    tokens = []
    for token in _RE_TOKENS.findall(bullet):
        normalized = token.lower().strip(".,;:!?\")'")
        if (
            normalized
            and normalized not in _STOPWORDS
            and not _RE_METRIC.fullmatch(normalized)
        ):
            tokens.append(normalized)
    for i in range(len(tokens) - 1):
        left, right = tokens[i], tokens[i + 1]
        if _is_generic_bigram(left, right) or not (
            _looks_technical(left) and _looks_technical(right)
        ):
            continue
        bigram = f"{left} {right}"
        _add(bigram)

    return claims


# ---------------------------------------------------------------------------
# Support checking
# ---------------------------------------------------------------------------

def _sentence_containing(text: str, index: int) -> str | None:
    if not text or index < 0:
        return None

    sentences = _split_sentences(text)
    if not sentences:
        return text.strip() or None

    cursor = 0
    for sentence in sentences:
        start = text.lower().find(sentence.lower(), cursor)
        if start == -1:
            start = cursor
        end = start + len(sentence)
        if start <= index < end:
            return sentence
        cursor = max(cursor, end)

    return sentences[0] if not text.strip() else None


def _best_window_ratio_with_idx(claim: str, original: str) -> tuple[float, int]:
    if not claim or not original:
        return 0.0, 0

    text = original[:5000]
    best_ratio = 0.0
    best_idx = 0
    cl = len(claim)
    step = max(1, cl // 2)

    for start in range(0, max(1, len(text) - cl + 1), step):
        window = text[start:start + cl]
        ratio = difflib.SequenceMatcher(None, claim, window, autojunk=False).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = start
        if best_ratio >= SUPPORT_THRESHOLD:
            break

    return best_ratio, best_idx


def _best_window_ratio(claim: str, original: str) -> float:
    ratio, _ = _best_window_ratio_with_idx(claim, original)
    return ratio


def _is_supported(claim: str, original: str) -> tuple[bool, str | None]:
    claim_lower = claim.lower().strip()
    original_lower = original.lower()

    if not claim_lower or not original:
        return False, None

    aliases = {
        "restful": ("rest api", "rest apis"),
        "rest endpoints": ("rest api", "rest apis"),
        "endpoint": ("api", "apis", "endpoint", "endpoints"),
        "endpoints": ("api", "apis", "endpoint", "endpoints"),
    }
    for alias in aliases.get(claim_lower, ()):
        if alias in original_lower:
            return True, _sentence_containing(original, original_lower.find(alias))

    # Numeric claims (e.g. "20%", "5.7gb", "100") must match EXACTLY —
    # skip fuzzy window matching entirely for these, since short digit
    # strings give unreliable fuzzy ratios against unrelated digit-heavy
    # text (phone numbers, dates, IDs).
    is_numeric = bool(re.fullmatch(r"\d[\d,]*(?:\.\d+)?(?:%|x|gb|tb|k|m|ms|s)?", claim_lower))
    if is_numeric:
        claim_value = _metric_value(claim_lower)
        for match in _RE_METRIC.finditer(original_lower):
            if _metric_value(match.group(0)) == claim_value:
                return True, _sentence_containing(original, match.start())
        return False, None

    if claim_lower in original_lower:
        idx = original_lower.find(claim_lower)
        return True, _sentence_containing(original, idx)

    words = claim_lower.split()
    if len(words) <= 3:
        ratio, best_idx = _best_window_ratio_with_idx(claim_lower, original_lower)
        if ratio >= SUPPORT_THRESHOLD:
            return True, _sentence_containing(original, best_idx)

    if len(words) > 1:
        for sentence in _split_sentences(original):
            sent_tokens = set(re.findall(r"[a-z0-9#+.]{2,}", sentence.lower()))
            if all(w in sent_tokens for w in words):
                return True, sentence

    return False, None
