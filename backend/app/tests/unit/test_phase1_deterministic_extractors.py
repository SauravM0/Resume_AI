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
    detect_job_description_sections,
    extract_deterministic_job_description_artifacts,
)
from resume_optimizer.phase1_deterministic_models import JDSectionKind, RequirementStrength

FIXTURE_PATH = (
    REPO_ROOT / "backend" / "app" / "tests" / "fixtures" / "phase1" / "deterministic_jd_cases.json"
)


def _cases() -> dict[str, dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_messy_jd_extraction_detects_sections_title_company_years_and_markers() -> None:
    case = _cases()["messy_jd"]
    extraction = extract_deterministic_job_description_artifacts(case["text"])

    assert extraction.title_candidates[0].canonical_value == case["expected_title"]
    assert extraction.company_name_candidates[0].canonical_value == case["expected_company"]
    assert any(section.kind is JDSectionKind.RESPONSIBILITIES for section in extraction.sections)
    assert any(section.kind is JDSectionKind.REQUIREMENTS for section in extraction.sections)
    assert any(finding.years == 5 for finding in extraction.years_experience_findings)
    assert any(
        item.strength is RequirementStrength.MUST_HAVE
        for item in extraction.requirement_markers
    )
    assert any(finding.canonical_value == "Python" for finding in extraction.tool_platform_findings)
    assert any(finding.canonical_value == case["expected_work_model"] for finding in extraction.work_model_findings)
    assert any(finding.canonical_value == case["expected_domain"] for finding in extraction.domain_findings)


def test_startup_jd_extraction_handles_startup_style_and_bonus_signals() -> None:
    case = _cases()["startup_jd"]
    extraction = extract_deterministic_job_description_artifacts(case["text"])

    assert extraction.title_candidates[0].canonical_value == case["expected_title"]
    assert extraction.company_name_candidates[0].canonical_value == case["expected_company"]
    assert any(finding.canonical_value == "remote" for finding in extraction.work_model_findings)
    assert any(
        item.strength is RequirementStrength.BONUS
        for item in extraction.requirement_markers
    )
    assert extraction.scope_indicator_findings


def test_enterprise_jd_extraction_handles_company_label_education_and_domains() -> None:
    case = _cases()["enterprise_jd"]
    extraction = extract_deterministic_job_description_artifacts(case["text"])

    assert extraction.title_candidates[0].canonical_value == case["expected_title"]
    assert extraction.company_name_candidates[0].canonical_value == case["expected_company"]
    assert any(section.kind is JDSectionKind.QUALIFICATIONS for section in extraction.sections)
    assert any(section.kind is JDSectionKind.PREFERRED for section in extraction.sections)
    assert any(finding.canonical_value == "bachelors" for finding in extraction.education_requirement_findings)
    assert any(finding.canonical_value == "onsite" for finding in extraction.work_model_findings)
    assert any(finding.canonical_value == case["expected_domain"] for finding in extraction.domain_findings)
    assert any(finding.canonical_value == "people_management" or finding.canonical_value == "lead" for finding in extraction.leadership_findings)


def test_vague_jd_extraction_still_returns_structured_artifact_safely() -> None:
    case = _cases()["vague_jd"]
    extraction = extract_deterministic_job_description_artifacts(case["text"])

    assert extraction.raw_job_text.startswith("Software Role")
    assert extraction.title_candidates
    assert not extraction.company_name_candidates
    assert not extraction.work_model_findings
    assert extraction.sections
    assert extraction.extraction_notes


def test_section_detection_handles_repeated_headings_and_bullets() -> None:
    raw = (
        "Responsibilities:\n"
        "- Build systems\n"
        "Responsibilities:\n"
        "- Improve delivery\n"
        "Preferred Qualifications:\n"
        "- AWS\n"
    )

    sections = detect_job_description_sections(raw)

    assert len(sections) >= 3
    assert sections[0].kind is JDSectionKind.RESPONSIBILITIES
    assert any(section.kind is JDSectionKind.PREFERRED for section in sections)


def test_repeated_keyword_and_action_verb_extraction_is_inspectable() -> None:
    extraction = extract_deterministic_job_description_artifacts(
        "Backend Engineer\nBuild backend APIs. Build reliable backend systems. Improve backend delivery."
    )

    assert any(item.keyword == "backend" and item.count >= 3 for item in extraction.repeated_keyword_findings)
    assert any(item.canonical_value == "build" for item in extraction.action_verb_findings)
    assert any(item.canonical_value == "optimize" for item in extraction.action_verb_findings)
