from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.orchestration.adapters.base import StageExecutionContext
from backend.app.orchestration.adapters.generator_adapter import GeneratorAdapter
from backend.app.orchestration.adapters.job_parser_adapter import JobParserAdapter
from backend.app.orchestration.adapters.latex_renderer_adapter import LatexRendererAdapter
from backend.app.orchestration.adapters.pdf_compile_adapter import PdfCompileAdapter
from backend.app.orchestration.adapters.ranker_adapter import RankerAdapter
from backend.app.orchestration.adapters.verifier_adapter import VerifierAdapter
from backend.app.orchestration.enums import OrchestrationFailureType, StageName
from backend.app.orchestration.errors import StageExecutionError
from backend.app.orchestration.stage_registry import StageRegistry
from backend.app.services.render_input_adapter import RenderInputAdapterError
from resume_optimizer.phase1_deterministic_extractors import (
    extract_deterministic_job_description_artifacts,
)
from resume_optimizer.phase1_models import Phase1JobAnalysis, Phase1ParseResult
from resume_optimizer.phase1_role_modeling import (
    FunctionalRoleFamily,
    OrganizationalRoleMode,
)


def _context(stage_name: StageName) -> StageExecutionContext:
    return StageExecutionContext(run_id="run.stage-adapter-test", stage_name=stage_name)


def test_job_parser_adapter_translates_analysis_errors() -> None:
    def parse_func(_job_description_text: str):
        raise RuntimeError("provider unavailable")

    adapter = JobParserAdapter(parse_func=parse_func)

    with pytest.raises(StageExecutionError) as exc_info:
        adapter.execute(
            SimpleNamespace(request=SimpleNamespace(job_description_text="Build Python APIs.")),
            _context(StageName.PARSE_JOB_DESCRIPTION),
        )

    assert exc_info.value.failure_type == OrchestrationFailureType.JOB_DESCRIPTION_PARSE
    assert exc_info.value.stage_name == StageName.PARSE_JOB_DESCRIPTION
    assert exc_info.value.retryable is True


def test_job_parser_adapter_preserves_rebuilt_phase1_and_legacy_projection() -> None:
    raw_jd = "Senior Backend Engineer\nBuild Python APIs on AWS.\nHybrid role."
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
    parse_result = Phase1ParseResult(
        deterministic_extraction=deterministic,
        llm_enrichment_payload={"job_title": "Senior Backend Engineer"},
        enriched_analysis=analysis,
    )

    adapter = JobParserAdapter(parse_func=lambda _text: parse_result)
    result = adapter.execute(
        SimpleNamespace(request=SimpleNamespace(job_description_text=raw_jd)),
        _context(StageName.PARSE_JOB_DESCRIPTION),
    )

    assert result.phase1_result is not None
    assert result.final_analysis is not None
    assert result.final_analysis.job_title == "Senior Backend Engineer"
    assert result.raw_analysis is not None
    assert "Python" in result.raw_analysis.technical_skills
    assert "Python" in result.normalized_analysis.technical_skills


def test_ranker_adapter_translates_selection_errors() -> None:
    def ranking_func(_job_analysis, _source_profile):
        raise RuntimeError("ranking failed")

    adapter = RankerAdapter(ranking_func=ranking_func)

    with pytest.raises(StageExecutionError) as exc_info:
        adapter.execute(
            SimpleNamespace(job_analysis=object(), source_profile=object()),
            _context(StageName.RANK_SELECT_EVIDENCE),
        )

    assert exc_info.value.failure_type == OrchestrationFailureType.RANKING_SELECTION
    assert exc_info.value.stage_name == StageName.RANK_SELECT_EVIDENCE


def test_generator_adapter_translates_generation_errors() -> None:
    class _FailingPhase3Service:
        def run(self, *_args, **_kwargs):
            raise RuntimeError("schema mismatch")

    adapter = GeneratorAdapter(phase3_service=_FailingPhase3Service())

    with pytest.raises(StageExecutionError) as exc_info:
        adapter.execute(
            SimpleNamespace(
                job_analysis=object(),
                phase2_selection=object(),
                phase2_ranking=object(),
                source_profile=object(),
                generation_preferences=None,
            ),
            _context(StageName.GENERATE_STRUCTURED_CONTENT),
        )

    assert exc_info.value.failure_type == OrchestrationFailureType.GENERATION_SCHEMA
    assert exc_info.value.stage_name == StageName.GENERATE_STRUCTURED_CONTENT
    assert exc_info.value.retryable is True
    assert exc_info.value.fallback_eligible is True


def test_verifier_adapter_translates_verification_errors() -> None:
    adapter = VerifierAdapter()

    with pytest.raises(StageExecutionError) as exc_info:
        adapter.execute(
            SimpleNamespace(
                source_profile_id="profile.stage-adapter-test",
                job_analysis=None,
                source_profile=None,
                generation_payload=None,
                phase3_result=None,
                phase3_validation_report=None,
            ),
            _context(StageName.VERIFY_GENERATED_CONTENT),
        )

    assert exc_info.value.failure_type == OrchestrationFailureType.VERIFICATION_RETRYABLE
    assert exc_info.value.stage_name == StageName.VERIFY_GENERATED_CONTENT
    assert exc_info.value.retryable is True


def test_latex_renderer_adapter_translates_render_contract_errors() -> None:
    def render_input_builder(**_kwargs):
        raise RenderInputAdapterError("not renderable")

    adapter = LatexRendererAdapter(render_input_builder=render_input_builder)

    with pytest.raises(StageExecutionError) as exc_info:
        adapter.execute(
            SimpleNamespace(
                source_profile=object(),
                rendering_output=object(),
                template_id="ats_standard",
                render_job_id="render.stage-adapter-test",
            ),
            _context(StageName.RENDER_DETERMINISTIC_LATEX),
        )

    assert exc_info.value.failure_type == OrchestrationFailureType.RENDER_CONTRACT
    assert exc_info.value.stage_name == StageName.RENDER_DETERMINISTIC_LATEX


def test_pdf_compile_adapter_translates_compile_errors() -> None:
    def compile_func(**_kwargs):
        raise RuntimeError("pdflatex missing")

    adapter = PdfCompileAdapter(compile_func=compile_func)

    with pytest.raises(StageExecutionError) as exc_info:
        adapter.execute(
            SimpleNamespace(
                assembled_document=SimpleNamespace(tex_content="\\documentclass{article}\\begin{document}x\\end{document}"),
                render_job_id="render.stage-adapter-test",
                template_id="ats_standard",
            ),
            _context(StageName.COMPILE_PDF),
        )

    assert exc_info.value.failure_type == OrchestrationFailureType.PDF_COMPILE
    assert exc_info.value.stage_name == StageName.COMPILE_PDF
    assert exc_info.value.retryable is True


def test_stage_registry_dispatches_to_standard_adapter_interface() -> None:
    class _FakeAdapter:
        stage_name = StageName.PARSE_JOB_DESCRIPTION

        def execute(self, stage_input, context):
            return {"input": stage_input, "run_id": context.run_id}

        def extract_artifacts(self, stage_output, context):
            return []

    registry = StageRegistry(adapters=[_FakeAdapter()])
    result = registry.execute(
        StageName.PARSE_JOB_DESCRIPTION,
        {"payload": True},
        _context(StageName.PARSE_JOB_DESCRIPTION),
    )

    assert result == {"input": {"payload": True}, "run_id": "run.stage-adapter-test"}
