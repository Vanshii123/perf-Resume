import difflib
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.tailor import generate_tailored_bullets
from backend.services.verify_bullet import verify_bullet


def test_generated_bullet_is_rephrased_and_verified():
    source_sentence = "Built REST APIs in Python."
    generated_bullet = "REST APIs built with Python."

    with patch(
        "backend.services.tailor._call_llm",
        return_value=json.dumps({"bullets": [generated_bullet]}),
    ):
        bullets = generate_tailored_bullets(
            {"must_have_skills": ["Python", "REST APIs"], "nice_have_skills": []},
            source_sentence,
        )

    assert bullets
    assert bullets[0] != source_sentence
    assert (
        difflib.SequenceMatcher(
            None,
            bullets[0],
            source_sentence,
            autojunk=False,
        ).ratio()
        < 0.75
    )
    assert verify_bullet(bullets[0], source_sentence)["approved"]


def test_rejected_bullet_is_retried_before_being_dropped():
    source_sentence = "Built REST APIs in Python."
    first_attempt = "Built REST APIs in Ruby."
    retry_attempt = "Created REST endpoints with Python."

    with patch(
        "backend.services.tailor._call_llm",
        side_effect=[
            json.dumps({"bullets": [first_attempt]}),
            json.dumps({"bullets": [retry_attempt]}),
        ],
    ):
        bullets = generate_tailored_bullets(
            {"must_have_skills": ["Python", "REST APIs"], "nice_have_skills": []},
            source_sentence,
        )

    assert bullets == [retry_attempt]


def test_comma_separated_metric_is_verified_as_one_claim():
    resume = "Developed REST APIs handling 10k+ RPS for payments."
    bullet = "Built REST services supporting 10,000 requests per second for payments."

    verdict = verify_bullet(bullet, resume)

    assert verdict["approved"]


def test_bullet_combining_claims_from_different_resume_lines_is_rejected():
    resume = (
        "Built a product for 500+ users.\n"
        "Implemented FastAPI services with Python."
    )
    bullet = "Developed Python FastAPI services supporting 500 active users."

    verdict = verify_bullet(bullet, resume)

    assert not verdict["approved"]
    assert "Claims span multiple resume statements" in verdict["unsupported_claims"]


def test_bullet_without_extractable_evidence_is_rejected():
    verdict = verify_bullet(
        "Delivered robust backend solutions for demanding environments.",
        "Built REST APIs in Python.",
    )

    assert not verdict["approved"]
    assert verdict["unsupported_claims"] == ["No verifiable resume evidence"]

