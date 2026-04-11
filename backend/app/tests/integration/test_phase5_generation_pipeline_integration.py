from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.tests.fixtures.phase2_candidate_profiles import (
    strong_backend_engineer_profile,
    strong_backend_job_analysis,
)
from resume_optimizer.models import PartialDate
from resume_optimizer.phase3_models import GenerationPreferences
from resume_optimizer.phase3_output_validation import Phase3FallbackActionType
from resume_optimizer.services.phase2_service import Phase2Service
from resume_optimizer.services.phase3_service import Phase3Service
from resume_optimizer.generation.summary_service import SummaryGenerationService
from resume_optimizer.generation.bullet_rewrite_service import BulletRewriteService


class _FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _FakeResponses:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._outputs[min(len(self.calls) - 1, len(self._outputs) - 1)])


class _FakeClient:
    def __init__(self, outputs: list[str]) -> None:
        self.responses = _FakeResponses(outputs)


def test_phase5_generation_pipeline_happy_path() -> None:
    profile = strong_backend_engineer_profile()
    job_analysis = strong_backend_job_analysis()
    phase2 = Phase2Service().run(job_analysis, source_profile=profile)
    service = Phase3Service(
        summary_service=SummaryGenerationService(
            client=_FakeClient(
                [
                    '{"summary_text":"Backend engineer building Python services on AWS with a focus on reliability.","evidence_ids_used":["fixture.backend.exp.current"],"themes_used":["Improve reliability and delivery for platform services"]}'
                ]
            ),
            model="test-model",
            prompt_template="summary prompt",
        ),
        bullet_rewrite_service=BulletRewriteService(
            client=_FakeClient(
                [
                    '{"rewritten_text":"Architected AWS and Kubernetes platform services with Terraform, reducing deployment time by 68%.","evidence_ids_used":["fixture.backend.exp.current"],"rewrite_strategy":"condensed"}',
                    '{"rewritten_text":"Led Python and PostgreSQL API reliability work, reducing Sev-1 incidents by 42% and improving p95 latency by 33%.","evidence_ids_used":["fixture.backend.exp.current"],"rewrite_strategy":"light_rewrite"}',
                    '{"rewritten_text":"Owned CI/CD automation and self-serve provisioning used by 14 engineering teams.","evidence_ids_used":["fixture.backend.exp.current"],"rewrite_strategy":"light_rewrite"}',
                    '{"rewritten_text":"Built Go payment services with Redis caching, increasing checkout throughput by 27%.","evidence_ids_used":["fixture.backend.exp.prev"],"rewrite_strategy":"condensed"}',
                    '{"rewritten_text":"Built Python APIs and React workflows that cut environment setup time by 80%.","evidence_ids_used":["fixture.backend.project"],"rewrite_strategy":"condensed"}',
                ]
            ),
            model="test-model",
            prompt_template="rewrite prompt",
        ),
    )

    result = service.run(
        job_analysis,
        phase2_selection=phase2.phase2_result,
        phase2_ranking=phase2.ranking_response,
        source_profile=profile,
        generation_preferences=GenerationPreferences(),
    )

    assert result.phase3_result.summary is not None
    assert result.phase3_result.selected_experiences
    assert result.phase3_result.skills_to_highlight
    assert result.bounded_generation_artifacts["section_assembly_output"]["assembled_experience_sections"]
    assert "generation_quality_signals" in result.bounded_generation_artifacts


def test_phase5_generation_pipeline_records_summary_fallback() -> None:
    profile = strong_backend_engineer_profile()
    job_analysis = strong_backend_job_analysis()
    phase2 = Phase2Service().run(job_analysis, source_profile=profile)
    service = Phase3Service(
        summary_service=SummaryGenerationService(
            client=_FakeClient(
                [
                    '{"summary_text":"Results-driven dynamic professional with 10 years leading global teams.","evidence_ids_used":["fixture.backend.exp.current"],"themes_used":["Improve reliability and delivery for platform services"]}'
                ]
            ),
            model="test-model",
            prompt_template="summary prompt",
        ),
        bullet_rewrite_service=BulletRewriteService(
            client=_FakeClient(
                [
                    '{"rewritten_text":"Architected AWS and Kubernetes platform services with Terraform, reducing deployment time by 68%.","evidence_ids_used":["fixture.backend.exp.current"],"rewrite_strategy":"condensed"}'
                ]
            ),
            model="test-model",
            prompt_template="rewrite prompt",
        ),
    )

    result = service.run(
        job_analysis,
        phase2_selection=phase2.phase2_result,
        phase2_ranking=phase2.ranking_response,
        source_profile=profile,
    )

    assert result.phase3_result.summary is not None
    assert "results-driven" not in result.phase3_result.summary.text.casefold()
    assert any(
        action.action_type == Phase3FallbackActionType.SUMMARY_FALLBACK
        for action in result.validation_report.applied_fallbacks
    )


def test_phase5_generation_pipeline_records_invalid_rewrite_fallback() -> None:
    profile = strong_backend_engineer_profile()
    job_analysis = strong_backend_job_analysis()
    phase2 = Phase2Service().run(job_analysis, source_profile=profile)
    service = Phase3Service(
        summary_service=SummaryGenerationService(
            client=_FakeClient(
                [
                    '{"summary_text":"Backend engineer building Python services on AWS.","evidence_ids_used":["fixture.backend.exp.current"],"themes_used":["Improve reliability and delivery for platform services"]}'
                ]
            ),
            model="test-model",
            prompt_template="summary prompt",
        ),
        bullet_rewrite_service=BulletRewriteService(
            client=_FakeClient(
                [
                    '{"rewritten_text":"Owned global platform architecture in Python and AWS, reducing latency by 50%.","evidence_ids_used":["fixture.backend.exp.current"],"rewrite_strategy":"condensed"}'
                ]
            ),
            model="test-model",
            prompt_template="rewrite prompt",
        ),
    )

    result = service.run(
        job_analysis,
        phase2_selection=phase2.phase2_result,
        phase2_ranking=phase2.ranking_response,
        source_profile=profile,
    )

    assert any(
        action.action_type == Phase3FallbackActionType.BULLET_SOURCE_FALLBACK
        for action in result.validation_report.applied_fallbacks
    )
    assert result.phase3_result.selected_experiences[0].generated_bullets


def test_phase5_generation_pipeline_constrained_budget_tracks_assembly_omissions() -> None:
    profile = _expanded_backend_profile()
    job_analysis = strong_backend_job_analysis()
    phase2 = Phase2Service().run(job_analysis, source_profile=profile)
    service = Phase3Service(
        summary_service=SummaryGenerationService(
            client=_FakeClient(
                [
                    '{"summary_text":"Backend engineer with platform and reliability experience across Python services on AWS.","evidence_ids_used":["fixture.backend.exp.current"],"themes_used":["Improve reliability and delivery for platform services"]}'
                ]
            ),
            model="test-model",
            prompt_template="summary prompt",
        ),
        bullet_rewrite_service=BulletRewriteService(
            client=_FakeClient(
                ['{"rewritten_text":"Built backend services on AWS with measurable reliability impact.","evidence_ids_used":["fixture.backend.exp.current"],"rewrite_strategy":"light_rewrite"}']
            ),
            model="test-model",
            prompt_template="rewrite prompt",
        ),
    )

    result = service.run(
        job_analysis,
        phase2_selection=phase2.phase2_result,
        phase2_ranking=phase2.ranking_response,
        source_profile=profile,
    )

    assembly = result.bounded_generation_artifacts["section_assembly_output"]
    assert assembly["budget_signals"]["target_page_count"] == 1
    assert assembly["omitted_items_with_reasons"]


def _expanded_backend_profile():
    profile = strong_backend_engineer_profile()
    extra_experience = profile.experience[1].model_copy(
        update={
            "id": "fixture.backend.exp.extra",
            "organization": "ScaleGrid",
            "title": "Platform Engineer",
            "start_date": PartialDate(raw_value="2018-01"),
            "end_date": PartialDate(raw_value="2018-12"),
            "bullets": [
                bullet.model_copy(
                    update={
                        "id": f"fixture.backend.exp.extra.b{index + 1}",
                        "metrics": [
                            metric.model_copy(
                                update={"id": f"fixture.backend.exp.extra.metric.{index + 1}.{metric_index + 1}"}
                            )
                            for metric_index, metric in enumerate(bullet.metrics)
                        ],
                    }
                )
                for index, bullet in enumerate(profile.experience[0].bullets)
            ],
        }
    )
    extra_project = profile.projects[0].model_copy(
        update={
            "id": "fixture.backend.project.extra",
            "name": "Service Catalog",
            "bullets": [
                bullet.model_copy(
                    update={
                        "id": "fixture.backend.project.extra.b1",
                        "metrics": [
                            metric.model_copy(update={"id": "fixture.backend.project.extra.metric.1"})
                            for metric in bullet.metrics
                        ],
                    }
                )
                for bullet in profile.projects[0].bullets
            ],
        }
    )
    return profile.model_copy(
        update={
            "experience": [*profile.experience, extra_experience],
            "projects": [*profile.projects, extra_project],
        }
    )
