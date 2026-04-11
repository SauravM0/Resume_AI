from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.scripts.run_phase4_eval import DEFAULT_FIXTURE_DIR, load_eval_cases
from backend.app.services.verification.extractors import (
    detect_escalation_phrases,
    extract_named_technologies,
    extract_numeric_tokens,
    extract_unsupported_leadership_terms,
)
from backend.app.services.verification.rules import DEFAULT_RULE_SET


def test_phase4_fixture_categories_are_present() -> None:
    categories = {case.category for case in load_eval_cases(DEFAULT_FIXTURE_DIR)}

    assert categories == {
        "safe_bullet_rewrite",
        "unsupported_metric_inflation",
        "unsupported_tool_insertion",
        "leadership_inflation",
        "scope_inflation",
        "domain_inflation",
        "safe_summary",
        "unsafe_summary",
        "repairable_output",
        "unrepairable_output",
        "semantic_verifier_degraded_mode",
        "mixed_issue_severity_case",
    }


def test_numeric_extractor_covers_resume_risky_values() -> None:
    tokens = [
        token.normalized
        for token in extract_numeric_tokens(
            "Reduced latency by 25%, saved $1.2M, served 3 teams, shipped in 2024, and improved speed 2x."
        )
    ]

    assert "25%" in tokens
    assert "$1.2m" in tokens
    assert "3teams" in tokens
    assert "2024" in tokens
    assert "2x" in tokens


def test_technology_extractor_covers_configured_tool_names() -> None:
    tokens = [
        token.normalized
        for token in extract_named_technologies(
            "Built Python and PostgreSQL services with FastAPI.",
            DEFAULT_RULE_SET,
        )
    ]

    assert tokens == ["python", "postgresql", "fastapi"]


def test_role_and_leadership_inflation_rules_remain_configured() -> None:
    escalation = detect_escalation_phrases(
        generated_text="Owned PostgreSQL reliability improvements.",
        source_text="Contributed to PostgreSQL reliability improvements.",
        rules=DEFAULT_RULE_SET,
    )
    leadership = extract_unsupported_leadership_terms(
        generated_text="Mentored teams and led cross-functional strategy.",
        source_text="Implemented APIs.",
        rules=DEFAULT_RULE_SET,
    )

    assert escalation[0].rule.label == "contributed_to_owned"
    assert "mentored" in leadership
    assert "cross-functional strategy" in leadership
