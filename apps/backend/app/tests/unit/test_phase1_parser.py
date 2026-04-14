from __future__ import annotations

from pathlib import Path
import json
import sys
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from resume_optimizer.ai_service import analyze_job_description, parse_job_description
from resume_optimizer.job_models import ParsedJobAnalysisResponse

FIXTURE_DIR = REPO_ROOT / "backend" / "app" / "tests" / "fixtures" / "phase1"
CASES = json.loads((FIXTURE_DIR / "deterministic_jd_cases.json").read_text(encoding="utf-8"))


class _FakeResponsesClient:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **_kwargs):
        if not self._outputs:
            raise AssertionError("No fake outputs remaining.")
        return SimpleNamespace(output_text=self._outputs.pop(0))


def test_parser_merges_deterministic_artifact_and_drops_ungrounded_must_have() -> None:
    raw_jd = CASES["messy_jd"]["text"]
    payload = {
        "job_title": "Staff Platform Architect",
        "company_name": "Acme Payments",
        "functional_role_family": "backend",
        "organizational_role_mode": "senior_individual_contributor",
        "seniority_level": "senior",
        "primary_responsibility_clusters": [
            "Build Python APIs",
            "Improve reliability for our fintech platform"
        ],
        "must_have_skills": ["Python", "GraphQL"],
        "nice_to_have_skills": ["Kubernetes"],
        "required_tools_platforms": ["AWS", "PostgreSQL"],
        "required_domains": ["fintech"],
        "must_have_behaviors": ["Mentoring"],
        "business_goal_signals": ["Improve reliability and delivery quality"],
        "impact_signals": ["Production reliability"],
        "years_experience_requirement": 5,
        "education_requirement": {"required": False},
        "leadership_requirement": {"mentoring_expected": True},
        "delivery_scope_requirement": {"cross_functional_coordination_required": True},
        "constraint_signals": [],
        "work_model_signals": ["hybrid"],
        "industry_domain": "fintech",
        "key_action_verbs": ["build", "improve"],
        "jd_quality_score": 0.81,
        "parser_confidence": 0.79,
        "requirement_confidence_by_item": [
            {"item_type": "job_title", "item_value": "Staff Platform Architect", "confidence": 0.6},
            {"item_type": "must_have_skill", "item_value": "Python", "confidence": 0.92},
            {"item_type": "must_have_skill", "item_value": "GraphQL", "confidence": 0.92}
        ],
        "extraction_notes": ["Recruiter likely cares about backend reliability."],
        "normalized_keywords": ["python", "aws", "graphql"],
        "prioritized_requirements": [
            {
                "requirement_text": "Python",
                "requirement_type": "must_have_skill",
                "priority_rank": 1,
                "priority_tier": "critical",
                "confidence": 0.92
            },
            {
                "requirement_text": "GraphQL",
                "requirement_type": "must_have_skill",
                "priority_rank": 2,
                "priority_tier": "must_have",
                "confidence": 0.92
            }
        ]
    }
    client = _FakeResponsesClient([json.dumps(payload)])

    result = parse_job_description(raw_jd, client=client, model="fake-phase1")

    assert result.deterministic_extraction.title_candidates
    assert result.llm_enrichment_payload["job_title"] == "Staff Platform Architect"
    assert result.merged_analysis is not None
    assert result.enriched_analysis.job_title == "Senior Backend Engineer"
    assert "Python" in result.enriched_analysis.must_have_skills
    assert "GraphQL" not in result.enriched_analysis.must_have_skills
    assert "GraphQL" not in [item.requirement_text for item in result.enriched_analysis.prioritized_requirements]


def test_parser_retries_after_malformed_json() -> None:
    raw_jd = CASES["startup_jd"]["text"]
    valid_payload = {
        "job_title": "Founding Full-Stack Engineer",
        "company_name": "BrightSeed",
        "functional_role_family": "fullstack",
        "organizational_role_mode": "founder_or_generalist",
        "seniority_level": "senior",
        "primary_responsibility_clusters": ["Work across frontend, backend, infra, and product"],
        "must_have_skills": [],
        "nice_to_have_skills": ["React Native"],
        "required_tools_platforms": [],
        "required_domains": [],
        "must_have_behaviors": [],
        "business_goal_signals": ["Operate as a startup generalist"],
        "impact_signals": ["Delivery breadth"],
        "years_experience_requirement": None,
        "education_requirement": {},
        "leadership_requirement": {},
        "delivery_scope_requirement": {},
        "constraint_signals": ["Must work within the US"],
        "work_model_signals": ["remote"],
        "industry_domain": None,
        "key_action_verbs": [],
        "jd_quality_score": 0.66,
        "parser_confidence": 0.72,
        "requirement_confidence_by_item": [
            {"item_type": "job_title", "item_value": "Founding Full-Stack Engineer", "confidence": 0.98},
            {"item_type": "company_name", "item_value": "BrightSeed", "confidence": 0.9}
        ],
        "extraction_notes": ["Founding/generalist mode is inferred from startup wording."],
        "normalized_keywords": ["founding", "fullstack", "remote"],
        "prioritized_requirements": []
    }
    client = _FakeResponsesClient(["{not valid json", json.dumps(valid_payload)])

    result = parse_job_description(raw_jd, client=client, model="fake-phase1")

    assert result.llm_enrichment_payload["company_name"] == "BrightSeed"
    assert result.enriched_analysis.company_name == "BrightSeed"
    assert result.enriched_analysis.organizational_role_mode.value == "founder_or_generalist"


def test_parser_repairs_partial_invalid_payload_safely() -> None:
    raw_jd = CASES["enterprise_jd"]["text"]
    payload = {
        "job_title": "Engineering Manager, Platform",
        "company_name": "Northstar Cloud",
        "functional_role_family": "platform",
        "organizational_role_mode": "people_manager",
        "seniority_level": "director",
        "primary_responsibility_clusters": ["Lead platform engineers"],
        "must_have_skills": ["AWS", "AWS"],
        "nice_to_have_skills": ["AWS", "Fintech"],
        "required_tools_platforms": "AWS",
        "required_domains": ["fintech", "fintech"],
        "must_have_behaviors": ["Stakeholder"],
        "business_goal_signals": "Improve platform reliability",
        "impact_signals": ["Delivery velocity"],
        "years_experience_requirement": 8,
        "education_requirement": {"minimum_level": "bachelors"},
        "leadership_requirement": {"scope": "people_management", "people_management_required": True},
        "delivery_scope_requirement": {"scope_level": "multi_team", "cross_functional_coordination_required": True},
        "constraint_signals": [],
        "work_model_signals": ["onsite", "onsite"],
        "industry_domain": "fintech",
        "key_action_verbs": ["lead", "lead"],
        "jd_quality_score": 1.4,
        "parser_confidence": 0.2,
        "requirement_confidence_by_item": [
            {"item_type": "job_title", "item_value": "Engineering Manager, Platform", "confidence": 1.5},
            {"item_type": "required_tool_platform", "item_value": "AWS", "confidence": 0.7},
            {"item_type": "required_tool_platform", "item_value": "AWS", "confidence": 0.9}
        ],
        "extraction_notes": [],
        "normalized_keywords": ["aws", "aws"],
        "prioritized_requirements": [
            {
                "requirement_text": "AWS",
                "requirement_type": "required_tool_platform",
                "priority_rank": 1,
                "priority_tier": "critical",
                "confidence": 0.4
            },
            {
                "requirement_text": "Bachelor's degree",
                "requirement_type": "education_requirement",
                "priority_rank": 1,
                "priority_tier": "important",
                "confidence": 0.7
            }
        ]
    }
    client = _FakeResponsesClient([json.dumps(payload)])

    result = parse_job_description(raw_jd, client=client, model="fake-phase1")

    assert result.enriched_analysis.jd_quality_score == 1.0
    assert result.enriched_analysis.parser_confidence == 0.2
    assert result.enriched_analysis.extraction_notes
    assert result.enriched_analysis.required_tools_platforms == ["AWS", "Kubernetes", "Terraform"]
    assert [item.priority_rank for item in result.enriched_analysis.prioritized_requirements] == [1, 2]
    assert result.enriched_analysis.prioritized_requirements[0].priority_tier.value == "must_have"


def test_legacy_ai_service_wrapper_returns_legacy_raw_response() -> None:
    raw_jd = CASES["messy_jd"]["text"]
    payload = {
        "job_title": "Senior Backend Engineer",
        "company_name": "Acme Payments",
        "functional_role_family": "backend",
        "organizational_role_mode": "senior_individual_contributor",
        "seniority_level": "senior",
        "primary_responsibility_clusters": ["Build Python APIs"],
        "must_have_skills": ["Python"],
        "nice_to_have_skills": ["Kubernetes"],
        "required_tools_platforms": ["AWS", "PostgreSQL"],
        "required_domains": ["fintech"],
        "must_have_behaviors": ["Mentoring"],
        "business_goal_signals": ["Improve reliability"],
        "impact_signals": ["Production reliability"],
        "years_experience_requirement": 5,
        "education_requirement": {},
        "leadership_requirement": {},
        "delivery_scope_requirement": {},
        "constraint_signals": [],
        "work_model_signals": ["hybrid"],
        "industry_domain": "fintech",
        "key_action_verbs": ["build", "improve"],
        "jd_quality_score": 0.8,
        "parser_confidence": 0.8,
        "requirement_confidence_by_item": [
            {"item_type": "job_title", "item_value": "Senior Backend Engineer", "confidence": 0.98}
        ],
        "extraction_notes": [],
        "normalized_keywords": ["python", "aws"],
        "prioritized_requirements": []
    }
    client = _FakeResponsesClient([json.dumps(payload)])

    legacy = analyze_job_description(raw_jd, client=client, model="fake-phase1")

    assert isinstance(legacy, ParsedJobAnalysisResponse)
    assert "Python" in legacy.technical_skills
    assert legacy.role_type == "backend"
    assert legacy.seniority_level == "senior"
