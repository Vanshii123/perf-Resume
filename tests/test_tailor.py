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
