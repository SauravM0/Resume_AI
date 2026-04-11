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

from backend.app.orchestration.artifacts.artifact_manager import ArtifactManager
from backend.app.orchestration.artifacts.storage_backends import LocalArtifactStorageBackend
from backend.app.orchestration.enums import ArtifactKind, PipelineStatus, StageName
from backend.app.orchestration.orchestrator import ResumeGenerationOrchestrator
from backend.app.orchestration.pipeline_models import PipelineInput
from backend.app.orchestration.runner import PipelineRunRecorder
from backend.tests.orchestration.pipeline_harness import FakePipelineStageRegistry, PipelineCase
from resume_optimizer.ai_service import parse_job_description

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


class _CapturingRecorderFactory:
    def __init__(self) -> None:
        self.recorders: list[PipelineRunRecorder] = []

    def __call__(self) -> PipelineRunRecorder:
        recorder = PipelineRunRecorder(event_emitter=None)
        self.recorders.append(recorder)
        return recorder


class _RepositoryRecorderFactory:
    def __init__(self, repository: OrchestrationRepository) -> None:
        self.repository = repository
        self.recorders: list[PipelineRunRecorder] = []

    def __call__(self) -> PipelineRunRecorder:
        recorder = PipelineRunRecorder(repository=self.repository, event_emitter=None)
        self.recorders.append(recorder)
        return recorder


class _Phase1IntegratedRegistry(FakePipelineStageRegistry):
    def __init__(self, case: PipelineCase, parsed_result) -> None:
        super().__init__(case)
        self._parsed_result = parsed_result
        self.seen_rank_job_analysis = None

    def execute(self, stage_name: StageName, stage_input, context):
        if stage_name == StageName.RANK_SELECT_EVIDENCE:
            self.seen_rank_job_analysis = stage_input.job_analysis
        return super().execute(stage_name, stage_input, context)

    def _parse_output(self):
        from backend.app.orchestration.adapters.phase1_contract_adapter import (
            build_parse_job_description_output,
        )

        return build_parse_job_description_output(self._parsed_result)


def test_orchestrator_persists_explicit_phase1_artifacts_and_preserves_legacy_downstream_input(
    tmp_path: Path,
) -> None:
    raw_jd = CASES["messy_jd"]["text"]
    payload = {
        "job_title": "Senior Backend Engineer",
        "company_name": "Acme Payments",
        "functional_role_family": "backend",
        "organizational_role_mode": "senior_individual_contributor",
        "seniority_level": "senior",
        "primary_responsibility_clusters": ["Build Python APIs", "Improve reliability for payment systems"],
        "must_have_skills": ["Python"],
        "nice_to_have_skills": ["Kubernetes"],
        "required_tools_platforms": ["AWS", "PostgreSQL"],
        "required_domains": ["fintech"],
        "must_have_behaviors": ["Mentoring"],
        "business_goal_signals": ["Improve platform reliability"],
        "impact_signals": ["Production reliability"],
        "years_experience_requirement": 5,
        "education_requirement": {"required": False},
        "leadership_requirement": {"mentoring_expected": True},
        "delivery_scope_requirement": {"cross_functional_coordination_required": True},
        "constraint_signals": [],
        "work_model_signals": ["hybrid"],
        "industry_domain": "fintech",
        "key_action_verbs": ["build", "improve"],
        "jd_quality_score": 0.84,
        "parser_confidence": 0.82,
        "requirement_confidence_by_item": [
            {"item_type": "job_title", "item_value": "Senior Backend Engineer", "confidence": 0.98}
        ],
        "extraction_notes": ["Reliability emphasis inferred from repeated ownership language."],
        "normalized_keywords": ["python", "aws", "reliability"],
        "prioritized_requirements": [
            {
                "requirement_text": "Python",
                "requirement_type": "must_have_skill",
                "priority_rank": 1,
                "priority_tier": "critical",
                "confidence": 0.95,
            }
        ],
    }
    parsed = parse_job_description(
        raw_jd,
        client=_FakeResponsesClient([json.dumps(payload)]),
        model="fake-phase1",
    )
    case = PipelineCase(
        case_id="phase1_pipeline_integration",
        scenario_type="strong_match",
        job_description_text=raw_jd,
    )
    registry = _Phase1IntegratedRegistry(case, parsed)
    recorder_factory = _CapturingRecorderFactory()
    orchestrator = ResumeGenerationOrchestrator(
        recorder_factory=recorder_factory,
        stage_registry=registry,
        artifact_manager=ArtifactManager(LocalArtifactStorageBackend(tmp_path / "artifacts")),
    )

    response = orchestrator.run(
        PipelineInput(
            source_profile_path=Path("data/master_profile.example.json"),
            job_description_text=raw_jd,
            template_id="ats_standard",
        )
    )

    assert response.status == PipelineStatus.SUCCEEDED
    assert registry.seen_rank_job_analysis is not None
    assert "Python" in registry.seen_rank_job_analysis.technical_skills
    assert registry.seen_rank_job_analysis.role_type.value == "individual_contributor"

    recorder = recorder_factory.recorders[0]
    artifact_kinds = [artifact.kind.value for artifact in recorder.artifacts]
    assert "raw_job_description" in artifact_kinds
    assert "job_analysis" in artifact_kinds
    assert "phase1_deterministic_extraction" in artifact_kinds
    assert "phase1_llm_enrichment" in artifact_kinds
    assert "phase1_final_analysis" in artifact_kinds
    assert "verification_audit" in artifact_kinds

    final_analysis_artifact = next(
        artifact for artifact in recorder.artifacts if artifact.kind == ArtifactKind.PHASE1_FINAL_ANALYSIS
    )
    assert final_analysis_artifact.metadata["parser_confidence"] == parsed.enriched_analysis.parser_confidence
    assert final_analysis_artifact.metadata["jd_quality_score"] == parsed.enriched_analysis.jd_quality_score

    verification_audit_artifact = next(
        artifact for artifact in recorder.artifacts if artifact.kind == ArtifactKind.VERIFICATION_AUDIT
    )
    assert verification_audit_artifact.schema_version == "phase6.verification.audit.v1"
    assert verification_audit_artifact.sha256 is not None
    assert verification_audit_artifact.metadata["final_decision"] == "pass"
    assert "status=passed; decision=pass" in verification_audit_artifact.metadata["internal_summary"]


def test_orchestrator_persists_verification_audit_artifact_in_repository(tmp_path: Path) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("sqlalchemy")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from backend.app.db.models import Base
    from backend.app.db.repositories.orchestration_repository import OrchestrationRepository

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    case = PipelineCase(
        case_id="verification_audit_storage",
        scenario_type="strong_match",
        job_description_text=CASES["messy_jd"]["text"],
    )
    registry = FakePipelineStageRegistry(case)

    with Session(engine) as session:
        repository = OrchestrationRepository(session)
        recorder_factory = _RepositoryRecorderFactory(repository)
        orchestrator = ResumeGenerationOrchestrator(
            recorder_factory=recorder_factory,
            stage_registry=registry,
            artifact_manager=ArtifactManager(LocalArtifactStorageBackend(tmp_path / "artifacts")),
        )

        response = orchestrator.run(
            PipelineInput(
                source_profile_path=Path("data/master_profile.example.json"),
                job_description_text=case.job_description_text,
                template_id="ats_standard",
            )
        )
        session.commit()
        run = repository.get_pipeline_run(response.run_id)

    assert run is not None
    verification_audit = next(
        artifact for artifact in run.artifacts if artifact.artifact_type == ArtifactKind.VERIFICATION_AUDIT.value
    )
    assert verification_audit.inline_json is not None
    assert verification_audit.inline_json["schema_version"] == "phase6.verification.audit.v1"
    assert verification_audit.inline_json["final_decision"] == "pass"
    assert verification_audit.inline_json["verifier_coverage"]["semantic_coverage"] == 1.0


def test_orchestrator_can_disable_verification_audit_persistence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from backend.app.orchestration import orchestrator as pipeline_orchestrator_module

    monkeypatch.setattr(
        pipeline_orchestrator_module,
        "DEFAULT_SETTINGS",
        SimpleNamespace(phase6_audit_persistence_enabled=False),
    )
    case = PipelineCase(
        case_id="verification_audit_disabled",
        scenario_type="strong_match",
        job_description_text=CASES["messy_jd"]["text"],
    )
    registry = FakePipelineStageRegistry(case)
    recorder_factory = _CapturingRecorderFactory()
    orchestrator = ResumeGenerationOrchestrator(
        recorder_factory=recorder_factory,
        stage_registry=registry,
        artifact_manager=ArtifactManager(LocalArtifactStorageBackend(tmp_path / "artifacts")),
    )

    response = orchestrator.run(
        PipelineInput(
            source_profile_path=Path("data/master_profile.example.json"),
            job_description_text=case.job_description_text,
            template_id="ats_standard",
        )
    )

    assert response.status == PipelineStatus.SUCCEEDED
    recorder = recorder_factory.recorders[0]
    artifact_kinds = [artifact.kind.value for artifact in recorder.artifacts]
    assert "verification_report" in artifact_kinds
    assert "verification_audit" not in artifact_kinds
