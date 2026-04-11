from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.cache.metrics import JsonlCacheMetricsStore, summarize_cache_metrics
from backend.app.cache.storage import LocalJsonCache, get_or_compute
from backend.app.models.render_models import LatexTemplateMetadata
from backend.app.orchestration.adapters.base import StageExecutionContext
from backend.app.orchestration.adapters.job_parser_adapter import JobParserAdapter
from backend.app.orchestration.enums import StageName
from backend.app.services.template_registry import REQUIRED_TEMPLATE_PLACEHOLDERS, load_template
from resume_optimizer.loaders import load_and_normalize_master_profile
from resume_optimizer.phase1_deterministic_extractors import extract_deterministic_job_description_artifacts
from resume_optimizer.phase1_models import Phase1JobAnalysis, Phase1ParseResult
from resume_optimizer.phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode
from resume_optimizer.phase2_artifacts import build_phase2_candidate_artifacts


def _install_cache(monkeypatch, tmp_path: Path) -> JsonlCacheMetricsStore:
    cache = LocalJsonCache(tmp_path / "cache", max_entries=32)
    metrics = JsonlCacheMetricsStore(tmp_path / "cache_metrics.jsonl")
    monkeypatch.setattr("backend.app.cache.storage.DEFAULT_SAFE_CACHE", cache)
    monkeypatch.setattr("backend.app.cache.metrics.DEFAULT_CACHE_METRICS_STORE", metrics)
    return metrics


def _parser_context() -> StageExecutionContext:
    return StageExecutionContext(run_id="run.cache-test", stage_name=StageName.PARSE_JOB_DESCRIPTION)


def _parse_result(raw_jd: str) -> Phase1ParseResult:
    deterministic = extract_deterministic_job_description_artifacts(raw_jd)
    analysis = Phase1JobAnalysis.model_validate(
        {
            "raw_job_text": raw_jd,
            "job_title": "Senior Backend Engineer",
            "company_name": None,
            "functional_role_family": FunctionalRoleFamily.BACKEND,
            "organizational_role_mode": OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR,
            "seniority_level": "senior",
            "primary_responsibility_clusters": ["Build backend APIs"],
            "must_have_skills": ["Python"],
            "nice_to_have_skills": ["AWS"],
            "required_tools_platforms": ["AWS"],
            "required_domains": [],
            "must_have_behaviors": ["mentoring"],
            "business_goal_signals": ["Improve delivery reliability"],
            "impact_signals": ["Reliability impact"],
            "years_experience_requirement": 5,
            "education_requirement": {"required": False},
            "leadership_requirement": {"mentoring_expected": True},
            "delivery_scope_requirement": {"cross_functional_coordination_required": False},
            "constraint_signals": [],
            "work_model_signals": ["hybrid"],
            "industry_domain": None,
            "key_action_verbs": ["build"],
            "recruiter_intent": {
                "likely_success_shape": "Backend engineer with strong execution and reliability focus.",
                "confidence": 0.7,
            },
            "jd_quality_breakdown": {
                "completeness_score": 0.7,
                "specificity_score": 0.7,
                "ambiguity_score": 0.2,
                "consistency_score": 0.8,
                "downstream_risk_score": 0.3,
            },
            "jd_quality_score": 0.7,
            "parser_confidence": 0.8,
            "requirement_confidence_by_item": [
                {"item_type": "job_title", "item_value": "Senior Backend Engineer", "confidence": 0.95}
            ],
            "extraction_notes": [],
            "normalized_keywords": ["python", "aws"],
            "prioritized_requirements": [],
        }
    )
    return Phase1ParseResult(
        deterministic_extraction=deterministic,
        llm_enrichment_payload={"job_title": "Senior Backend Engineer"},
        enriched_analysis=analysis,
    )


def test_get_or_compute_records_hit_miss_and_stale_metrics(monkeypatch, tmp_path: Path) -> None:
    metrics = _install_cache(monkeypatch, tmp_path)
    calls = {"count": 0}

    class _ValueWrapper:
        def __init__(self, value: int) -> None:
            self.value = value

        def model_dump(self) -> dict[str, int]:
            return {"value": self.value}

    def compute() -> _ValueWrapper:
        calls["count"] += 1
        return _ValueWrapper(calls["count"])

    deserialize = lambda payload: SimpleNamespace(value=payload["value"])

    first, first_hit = get_or_compute(
        namespace="unit_cache",
        key="alpha",
        compute=compute,
        serialize=lambda value: value.model_dump(),
        deserialize=deserialize,
        ttl_seconds=1,
    )
    second, second_hit = get_or_compute(
        namespace="unit_cache",
        key="alpha",
        compute=compute,
        serialize=lambda value: value.model_dump(),
        deserialize=deserialize,
        ttl_seconds=1,
    )

    cache = LocalJsonCache(tmp_path / "cache", max_entries=32)
    monkeypatch.setattr("backend.app.cache.storage.DEFAULT_SAFE_CACHE", cache)
    cache.set_entry(
        namespace="unit_cache",
        key="stale",
        payload={"value": 9},
        ttl_seconds=-1,
        compute_duration_ms=5,
        metadata=None,
    )
    third, third_hit = get_or_compute(
        namespace="unit_cache",
        key="stale",
        compute=compute,
        serialize=lambda value: value.model_dump(),
        deserialize=deserialize,
        ttl_seconds=1,
    )

    summary = summarize_cache_metrics(metrics.load())
    assert first.value == 1
    assert second.value == 1
    assert third.value == 2
    assert first_hit is False
    assert second_hit is True
    assert third_hit is False
    assert summary["hits"] == 1
    assert summary["misses"] == 2
    assert summary["stale_invalidations"] == 1


def test_job_parser_cache_hits_on_exact_match(monkeypatch, tmp_path: Path) -> None:
    metrics = _install_cache(monkeypatch, tmp_path)
    calls = {"count": 0}
    raw_jd = "Senior Backend Engineer\nBuild Python APIs on AWS.\nHybrid role."

    def parse_func(_job_description_text: str):
        calls["count"] += 1
        return _parse_result(raw_jd)

    monkeypatch.setattr(
        "backend.app.orchestration.adapters.job_parser_adapter.DEFAULT_SETTINGS",
        SimpleNamespace(phase1_job_analysis_model="gpt-cache-a"),
    )
    adapter = JobParserAdapter(parse_func=parse_func)
    request = SimpleNamespace(request=SimpleNamespace(job_description_text=raw_jd))

    first = adapter.execute(request, _parser_context())
    second = adapter.execute(request, _parser_context())
    summary = summarize_cache_metrics(metrics.load())

    assert first.final_analysis is not None
    assert second.final_analysis is not None
    assert calls["count"] == 1
    assert summary["namespaces"]["parse_job_description"]["hits"] == 1
    assert summary["namespaces"]["parse_job_description"]["misses"] == 1


def test_job_parser_cache_misses_when_parser_config_changes(monkeypatch, tmp_path: Path) -> None:
    metrics = _install_cache(monkeypatch, tmp_path)
    calls = {"count": 0}
    raw_jd = "Senior Backend Engineer\nBuild Python APIs on AWS.\nHybrid role."

    def parse_func(_job_description_text: str):
        calls["count"] += 1
        return _parse_result(raw_jd)

    request = SimpleNamespace(request=SimpleNamespace(job_description_text=raw_jd))
    monkeypatch.setattr(
        "backend.app.orchestration.adapters.job_parser_adapter.DEFAULT_SETTINGS",
        SimpleNamespace(phase1_job_analysis_model="gpt-cache-a"),
    )
    JobParserAdapter(parse_func=parse_func).execute(request, _parser_context())
    monkeypatch.setattr(
        "backend.app.orchestration.adapters.job_parser_adapter.DEFAULT_SETTINGS",
        SimpleNamespace(phase1_job_analysis_model="gpt-cache-b"),
    )
    JobParserAdapter(parse_func=parse_func).execute(request, _parser_context())

    summary = summarize_cache_metrics(metrics.load())
    assert calls["count"] == 2
    assert summary["namespaces"]["parse_job_description"]["hits"] == 0
    assert summary["namespaces"]["parse_job_description"]["misses"] == 2


def test_template_cache_misses_when_template_checksum_changes(monkeypatch, tmp_path: Path) -> None:
    metrics = _install_cache(monkeypatch, tmp_path)
    template_file = tmp_path / "template.tex"
    template_file.write_text(
        "\n".join(f"% PLACEHOLDER: {placeholder.value}" for placeholder in REQUIRED_TEMPLATE_PLACEHOLDERS)
        + "\n\\end{document}\n",
        encoding="utf-8",
    )
    metadata = LatexTemplateMetadata(
        template_id="test_template",
        version="1.0.0",
        display_name="Test",
        description="Test template",
        active=True,
        ats_safe=True,
        max_recommended_pages=1,
        filesystem_path=template_file,
        required_placeholders=list(REQUIRED_TEMPLATE_PLACEHOLDERS),
        optional_placeholders=[],
    )
    monkeypatch.setattr("backend.app.services.template_registry._REGISTERED_TEMPLATES", (metadata,))

    first = load_template("test_template", version="1.0.0")
    second = load_template("test_template", version="1.0.0")
    template_file.write_text(
        "\n".join(f"% PLACEHOLDER: {placeholder.value}" for placeholder in REQUIRED_TEMPLATE_PLACEHOLDERS)
        + "\n% changed\n\\end{document}\n",
        encoding="utf-8",
    )
    third = load_template("test_template", version="1.0.0")

    summary = summarize_cache_metrics(metrics.load())
    assert first.checksum_sha256 == second.checksum_sha256
    assert first.checksum_sha256 != third.checksum_sha256
    assert summary["namespaces"]["template_load"]["hits"] == 1
    assert summary["namespaces"]["template_load"]["misses"] == 2


def test_phase2_candidate_artifacts_cache_does_not_reuse_different_profiles(monkeypatch, tmp_path: Path) -> None:
    metrics = _install_cache(monkeypatch, tmp_path)
    profile_one = load_and_normalize_master_profile("data/master_profile.example.json")
    profile_two = profile_one.model_copy(update={"id": "profile.cache.variant"})

    first = build_phase2_candidate_artifacts(profile_one)
    second = build_phase2_candidate_artifacts(profile_one)
    third = build_phase2_candidate_artifacts(profile_two)

    summary = summarize_cache_metrics(metrics.load())
    assert first.source_profile.id == second.source_profile.id
    assert third.source_profile.id != first.source_profile.id
    assert summary["namespaces"]["phase2_candidate_artifacts"]["hits"] == 1
    assert summary["namespaces"]["phase2_candidate_artifacts"]["misses"] == 2
