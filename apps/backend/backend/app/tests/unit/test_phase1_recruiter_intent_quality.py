from __future__ import annotations

from pathlib import Path
import json
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from resume_optimizer.phase1_deterministic_extractors import (
    extract_deterministic_job_description_artifacts,
)
from resume_optimizer.phase1_jd_quality import score_job_description_quality
from resume_optimizer.phase1_recruiter_intent import infer_recruiter_intent_profile
from resume_optimizer.phase1_role_modeling import infer_role_axes

FIXTURE_DIR = REPO_ROOT / "backend" / "app" / "tests" / "fixtures" / "phase1"
RAW_CASES = json.loads((FIXTURE_DIR / "deterministic_jd_cases.json").read_text(encoding="utf-8"))
EXPECTATIONS = json.loads((FIXTURE_DIR / "recruiter_intent_quality_examples.json").read_text(encoding="utf-8"))


def _deterministic_case(case_name: str):
    raw_jd = RAW_CASES[case_name]["text"]
    deterministic = extract_deterministic_job_description_artifacts(raw_jd)
    role_axes = infer_role_axes(
        job_title=deterministic.title_candidates[0].canonical_value if deterministic.title_candidates else None,
        raw_job_text=raw_jd,
    )
    return deterministic, infer_recruiter_intent_profile(deterministic, role_axes), score_job_description_quality(deterministic)[0]


def test_strong_jd_has_higher_intent_confidence_and_quality() -> None:
    strong_case = EXPECTATIONS["strong_jd"]
    deterministic, intent, quality = _deterministic_case(strong_case["name"])

    assert intent.breadth_preference.value == strong_case["expected"]["breadth_preference"]
    assert intent.confidence >= strong_case["expected"]["min_recruiter_intent_confidence"]
    assert quality.ambiguity_score <= strong_case["expected"]["max_ambiguity_score"]
    assert quality.completeness_score >= strong_case["expected"]["min_completeness_score"]
    assert deterministic.requirement_markers


def test_weak_jd_scores_lower_and_more_ambiguous() -> None:
    weak_case = EXPECTATIONS["weak_jd"]
    _deterministic, intent, quality = _deterministic_case(weak_case["name"])

    assert intent.breadth_preference.value == weak_case["expected"]["breadth_preference"]
    assert intent.confidence <= weak_case["expected"]["max_recruiter_intent_confidence"]
    assert quality.ambiguity_score >= weak_case["expected"]["min_ambiguity_score"]
    assert quality.completeness_score <= weak_case["expected"]["max_completeness_score"]


def test_ambiguous_jd_exposes_downstream_risk_and_notes() -> None:
    ambiguous_case = EXPECTATIONS["ambiguous_jd"]
    _deterministic, intent, quality = _deterministic_case(ambiguous_case["name"])

    assert quality.downstream_risk_score >= ambiguous_case["expected"]["min_downstream_risk_score"]
    assert any("ambiguous" in note.casefold() or "vague" in note.casefold() for note in quality.notes)
    assert any("weakly grounded" in note.casefold() for note in intent.notes)
