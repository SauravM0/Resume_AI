"""Deterministic Phase 6 orchestration batch harness."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import tempfile
from typing import Any

from backend.app.models.render_models import (
    ArtifactKind as RenderArtifactKind,
    CompileResult,
    LatexCompiler,
    RenderJobInput,
    RenderPersonalInfo,
    RenderSection,
    RenderSectionType,
    RenderSourceProvenance,
    RenderArtifactMetadata,
)
from backend.app.orchestration.adapters.base import StageExecutionContext
from backend.app.orchestration.artifacts.artifact_manager import ArtifactManager
from backend.app.orchestration.artifacts.storage_backends import LocalArtifactStorageBackend
from backend.app.orchestration.enums import ArtifactKind, OrchestrationFailureType, PipelineStatus, StageName
from backend.app.orchestration.errors import OrchestrationError, StageExecutionError
from backend.app.orchestration.orchestrator import ResumeGenerationOrchestrator
from backend.app.orchestration.pipeline_models import (
    CompilePdfOutput,
    GenerateStructuredContentOutput,
    ParseJobDescriptionOutput,
    RankSelectEvidenceOutput,
    RenderDeterministicLatexOutput,
    VerifyGeneratedContentOutput,
)
from backend.app.orchestration.runner import PipelineRunRecorder
from backend.app.orchestration.stage_registry import StageRegistry
from backend.app.orchestration.types import PipelineArtifactRef
from backend.app.schemas.verification import Phase4RenderingOutput, VerificationReport
from backend.app.services.document_assembler import AssembledDocument, SectionInsertionDiagnostics
from backend.app.services.pdf_compiler import PdfCompileResult
from backend.app.services.verification.types import FallbackAction, VerificationStatus
from resume_optimizer.job_models import NormalizedJobAnalysis, ParsedJobAnalysisResponse
from resume_optimizer.loaders import load_and_normalize_master_profile
from resume_optimizer.models import ItemType
from resume_optimizer.phase2_models import (
    JobAnalysisInput,
    Phase2SelectionResult,
    RankingExplanation,
    ScoredEvidenceUnit,
    SelectedExperience,
)
from resume_optimizer.phase3_models import (
    GeneratedBullet,
    GeneratedExperience,
    GeneratedHeadline,
    GeneratedSkillHighlight,
    GeneratedSummary,
    GenerationMetadata,
    Phase3GenerationPayload,
    Phase3GenerationRequest,
    Phase3RoleContext,
    Phase3SelectedBulletPayload,
    Phase3SelectedExperiencePayload,
    Phase3SelectedSkillPayload,
    Phase3ValidationMetadata,
    SourceReference,
    SupportLevel,
)
from resume_optimizer.phase3_output_validation import Phase3ValidationReport
from resume_optimizer.phase3_section_planner import plan_phase3_sections
from resume_optimizer.ranking_models import RankingResponse, SummaryBriefTheme


@dataclass(frozen=True, slots=True)
class PipelineCase:
    """One deterministic pipeline regression case."""

    case_id: str
    scenario_type: str
    job_description_text: str
    expected_status: PipelineStatus = PipelineStatus.SUCCEEDED
    forced_failure_stage: StageName | None = None
    forced_failure_type: OrchestrationFailureType | None = None
    retry_once_stage: StageName | None = None
    expected_terminal_stage: StageName | None = None
    snapshot_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PipelineCaseResult:
    """Structured result emitted by the batch harness."""

    case_id: str
    scenario_type: str
    passed: bool
    status: str
    run_id: str | None
    failed_stage: str | None
    error_type: str | None
    stage_outcomes: list[dict[str, Any]]
    retry_attempts: list[dict[str, Any]]
    fallback_decisions: list[dict[str, Any]]
    artifact_kinds: list[str]
    snapshot: dict[str, Any]
    error_message: str | None = None


class _CapturingRecorderFactory:
    def __init__(self) -> None:
        self.recorders: list[PipelineRunRecorder] = []

    def __call__(self) -> PipelineRunRecorder:
        recorder = PipelineRunRecorder(event_emitter=None)
        self.recorders.append(recorder)
        return recorder


class FakePipelineStageRegistry(StageRegistry):
    """Fake registry that preserves stage contracts without live AI or LaTeX."""

    def __init__(self, case: PipelineCase) -> None:
        self.case = case
        self.calls: dict[StageName, int] = {}
        self.profile = load_and_normalize_master_profile("data/master_profile.example.json")
        self.job_analysis = NormalizedJobAnalysis(
            role_type="individual_contributor",
            seniority_level="senior",
            technical_skills=_skills_for_case(case),
            soft_skills=["Communication"],
            must_have_requirements=[case.job_description_text[:160]],
            key_action_verbs=["build", "improve"],
        )

    def get(self, stage_name: StageName):
        raise NotImplementedError("FakePipelineStageRegistry dispatches directly through execute.")

    def execute(self, stage_name: StageName, stage_input, context: StageExecutionContext):
        self.calls[stage_name] = self.calls.get(stage_name, 0) + 1
        self._current_recorder = context.recorder
        if self.case.retry_once_stage == stage_name and self.calls[stage_name] == 1:
            raise StageExecutionError(
                f"forced retry for {self.case.case_id}",
                failure_type=self.case.forced_failure_type or OrchestrationFailureType.GENERATION_SCHEMA,
                stage_name=stage_name,
                retryable=True,
            )
        if self.case.forced_failure_stage == stage_name and self.case.retry_once_stage != stage_name:
            raise StageExecutionError(
                f"forced failure for {self.case.case_id}",
                failure_type=self.case.forced_failure_type or OrchestrationFailureType.INTERNAL,
                stage_name=stage_name,
                http_status_code=409 if self.case.forced_failure_type == OrchestrationFailureType.VERIFICATION_BLOCKED else 500,
            )
        if stage_name == StageName.PARSE_JOB_DESCRIPTION:
            return self._parse_output()
        if stage_name == StageName.RANK_SELECT_EVIDENCE:
            return self._rank_output()
        if stage_name == StageName.GENERATE_STRUCTURED_CONTENT:
            return self._generation_output(stage_input.phase2_selection)
        if stage_name == StageName.VERIFY_GENERATED_CONTENT:
            return self._verification_output(stage_input.phase3_result)
        if stage_name == StageName.RENDER_DETERMINISTIC_LATEX:
            return self._render_output(context.run_id)
        if stage_name == StageName.COMPILE_PDF:
            return self._compile_output(context.run_id)
        raise ValueError(f"unsupported fake stage: {stage_name.value}")

    @property
    def stage_names(self) -> list[StageName]:
        return [
            StageName.PARSE_JOB_DESCRIPTION,
            StageName.RANK_SELECT_EVIDENCE,
            StageName.GENERATE_STRUCTURED_CONTENT,
            StageName.VERIFY_GENERATED_CONTENT,
            StageName.RENDER_DETERMINISTIC_LATEX,
            StageName.COMPILE_PDF,
        ]

    def _parse_output(self) -> ParseJobDescriptionOutput:
        return ParseJobDescriptionOutput(
            raw_analysis=ParsedJobAnalysisResponse(
                technical_skills=self.job_analysis.technical_skills,
                soft_skills=self.job_analysis.soft_skills,
                must_have_requirements=self.job_analysis.must_have_requirements,
            ),
            normalized_analysis=self.job_analysis,
        )

    def _rank_output(self) -> RankSelectEvidenceOutput:
        explanation = RankingExplanation(
            summary="Selected deterministic evidence matching regression case skills.",
            matched_keywords=self.job_analysis.technical_skills[:2],
            matched_required_skills=self.job_analysis.technical_skills[:2],
        )
        scored = ScoredEvidenceUnit(
            id="evidence.exp.northstar",
            item_type=ItemType.EXPERIENCE,
            title="Northstar Tech Sr Software Engineer",
            source_item_id="exp.northstar-tech",
            source_bullet_ids=["bullet.northstar-checkout"],
            bullets=["Redesigned checkout flow for SMB customers."],
            keywords=self.job_analysis.technical_skills[:2],
            relevance_score=_score_for_case(self.case),
            ranking_explanation=explanation,
            selected_bullet_ids=["bullet.northstar-checkout"],
        )
        selection = Phase2SelectionResult(
            job_analysis=JobAnalysisInput.model_validate(self.job_analysis.model_dump()),
            candidate_profile_id=self.profile.id,
            scored_evidence=[scored],
            selected_experiences=[
                SelectedExperience(
                    id="selected.exp.northstar",
                    source_item_id=scored.id,
                    relevance_score=scored.relevance_score,
                    selected_bullet_ids=["bullet.northstar-checkout"],
                    ranking_explanation=explanation,
                )
            ],
        )
        return RankSelectEvidenceOutput(
            ranking_response=RankingResponse(
                ranked_experiences=[scored],
                skills_to_highlight=self.job_analysis.technical_skills[:3],
                headline_suggestion="Senior Software Engineer",
                summary_brief_themes=[
                    SummaryBriefTheme(
                        theme="Relevant delivery experience",
                        supporting_keywords=self.job_analysis.technical_skills[:2],
                    )
                ],
            ),
            selection_result=selection,
        )

    def _generation_output(self, selection: Phase2SelectionResult) -> GenerateStructuredContentOutput:
        payload = Phase3GenerationPayload(
            role_context=Phase3RoleContext(
                target_role_title="Senior Software Engineer",
                must_have_skills=self.job_analysis.technical_skills[:3],
            ),
            selected_experiences=[
                Phase3SelectedExperiencePayload(
                    id="exp.northstar-tech",
                    evidence_unit_ids=["evidence.exp.northstar"],
                    organization="Northstar Tech",
                    title="Sr Software Engineer",
                    start_date={"raw_value": "2022-04"},
                    tools=self.job_analysis.technical_skills[:3],
                    bullets=[
                        Phase3SelectedBulletPayload(
                            id="bullet.northstar-checkout",
                            text="Redesigned checkout flow for SMB customers.",
                            tools=self.job_analysis.technical_skills[:2],
                            evidence_strength="strong",
                            verified_status="corroborated",
                        )
                    ],
                    relevance_score=_score_for_case(self.case),
                )
            ],
            matched_skills=[
                Phase3SelectedSkillPayload(
                    id=_skill_id(skill),
                    skill_name=skill,
                    relevance_score=0.9,
                    evidence_strength="strong",
                    verified_status="corroborated",
                )
                for skill in self.job_analysis.technical_skills[:2]
            ],
            validation_metadata=Phase3ValidationMetadata(
                profile_id=self.profile.id,
                allowed_experience_ids=["exp.northstar-tech"],
                allowed_bullet_ids=["bullet.northstar-checkout"],
                allowed_skill_ids=[_skill_id(skill) for skill in self.job_analysis.technical_skills[:2]],
            ),
        )
        result = _build_phase3_result(self.profile.id, self.case, payload)
        return GenerateStructuredContentOutput(
            request=Phase3GenerationRequest(
                job_analysis=self.job_analysis,
                phase2_selection=selection,
                source_profile=self.profile,
            ),
            generation_payload=payload,
            section_plan=plan_phase3_sections(payload),
            phase3_result=result,
            validation_report=Phase3ValidationReport(),
        )

    def _verification_output(self, phase3_result: Any) -> VerifyGeneratedContentOutput:
        report = VerificationReport(
            verification_run_id=f"verify.{self.case.case_id}",
            source_profile_id=self.profile.id,
            status=VerificationStatus.PASSED,
            renderable=True,
        )
        return VerifyGeneratedContentOutput(
            verification_run_id=report.verification_run_id,
            verification_report=report,
            rendering_output=Phase4RenderingOutput(
                source_profile_id=self.profile.id,
                verified_result=phase3_result,
                verification_report=report,
                renderable=True,
                fallback_action=FallbackAction.ACCEPT,
            ),
        )

    def _render_output(self, run_id: str) -> RenderDeterministicLatexOutput:
        render_input = RenderJobInput(
            render_job_id=f"render.{run_id}",
            source_profile_id=self.profile.id,
            template_id="ats_standard",
            personal_info=RenderPersonalInfo(
                full_name=self.profile.personal_profile.full_name,
                email=self.profile.personal_profile.email or "alex@example.com",
                provenance=RenderSourceProvenance(source_item_ids=[self.profile.personal_profile.id]),
            ),
            sections=[
                RenderSection(
                    id="section.personal_info",
                    section_type=RenderSectionType.PERSONAL_INFO,
                    title="Personal Info",
                    display_order=0,
                    visible=True,
                )
            ],
            section_visibility={RenderSectionType.PERSONAL_INFO: True},
        )
        assembled = AssembledDocument(
            template_id="ats_standard",
            template_version="regression",
            tex_content="\\documentclass{article}\\begin{document}Regression Resume\\end{document}",
            diagnostics=SectionInsertionDiagnostics(
                template_id="ats_standard",
                template_version="regression",
            ),
        )
        return RenderDeterministicLatexOutput(render_input=render_input, assembled_document=assembled)

    def _compile_output(self, run_id: str) -> CompilePdfOutput:
        workspace = Path(tempfile.mkdtemp(prefix="pipeline-regression-"))
        pdf_path = workspace / "resume.pdf"
        tex_path = workspace / "resume.tex"
        pdf_path.write_bytes(b"%PDF-1.4\n")
        tex_path.write_text("\\documentclass{article}\\begin{document}Regression Resume\\end{document}", encoding="utf-8")
        pdf_metadata = RenderArtifactMetadata(
            artifact_id=f"render.{run_id}.pdf",
            render_job_id=f"render.{run_id}",
            kind=RenderArtifactKind.PDF,
            template_id="ats_standard",
            content_type="application/pdf",
            path=str(pdf_path),
        )
        compile_result = PdfCompileResult(
            compile_success=True,
            render_job_id=f"render.{run_id}",
            workspace_path=str(workspace),
            tex_file_path=str(tex_path),
            pdf_file_path=str(pdf_path),
            return_code=0,
            elapsed_ms=1,
            compile_result=CompileResult(
                success=True,
                compiler=LatexCompiler.PDFLATEX,
                exit_code=0,
                pdf_artifact=pdf_metadata,
            ),
        )
        pdf_ref = PipelineArtifactRef(
            artifact_id=f"artifact.{run_id}.pdf",
            kind=ArtifactKind.PDF,
            stage_name=StageName.COMPILE_PDF,
            storage_backend="local_file",
            schema_version="phase6.regression.artifact.v1",
            uri=str(pdf_path),
            content_type="application/pdf",
        )
        context_recorder = getattr(self, "_current_recorder", None)
        if context_recorder is not None:
            pdf_ref = context_recorder.record_artifact(
                stage_name=StageName.COMPILE_PDF,
                artifact_type=ArtifactKind.PDF,
                storage_kind="local_file",
                storage_path_or_key=str(pdf_path),
                schema_version="phase6.regression.artifact.v1",
                content_type="application/pdf",
            )
            context_recorder.record_output(
                compile_status="succeeded",
                pdf_path_or_storage_key=str(pdf_path),
                latex_path_or_storage_key=str(tex_path),
                page_count=None,
                output_metadata_json={"regression": True},
            )
        return CompilePdfOutput(compile_result=compile_result, pdf_artifact_ref=pdf_ref)


def load_pipeline_cases(path: Path) -> list[PipelineCase]:
    """Load pipeline cases from a JSON fixture file."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        PipelineCase(
            case_id=item["case_id"],
            scenario_type=item["scenario_type"],
            job_description_text=item["job_description_text"],
            expected_status=PipelineStatus(item.get("expected_status", PipelineStatus.SUCCEEDED.value)),
            forced_failure_stage=StageName(item["forced_failure_stage"]) if item.get("forced_failure_stage") else None,
            forced_failure_type=(
                OrchestrationFailureType(item["forced_failure_type"])
                if item.get("forced_failure_type")
                else None
            ),
            retry_once_stage=StageName(item["retry_once_stage"]) if item.get("retry_once_stage") else None,
            expected_terminal_stage=StageName(item["expected_terminal_stage"]) if item.get("expected_terminal_stage") else None,
            snapshot_fields=item.get("snapshot_fields", []),
        )
        for item in raw["cases"]
    ]


def run_pipeline_case(case: PipelineCase, *, artifact_root: Path | None = None) -> PipelineCaseResult:
    """Run one deterministic case through the real orchestrator."""

    recorder_factory = _CapturingRecorderFactory()
    artifact_manager = ArtifactManager(LocalArtifactStorageBackend(artifact_root or Path(tempfile.mkdtemp(prefix="pipeline-regression-artifacts-"))))
    orchestrator = ResumeGenerationOrchestrator(
        recorder_factory=recorder_factory,
        stage_registry=FakePipelineStageRegistry(case),
        artifact_manager=artifact_manager,
    )
    run_id = f"run.regression.{case.case_id}"
    status = PipelineStatus.FAILED
    error: OrchestrationError | None = None
    response = None
    try:
        response = orchestrator.run(
            orchestrator_input(
                run_id=run_id,
                job_description_text=case.job_description_text,
            )
        )
        status = response.status
    except OrchestrationError as exc:
        error = exc
        status = PipelineStatus.BLOCKED if exc.http_status_code == 409 else PipelineStatus.FAILED

    recorder = recorder_factory.recorders[-1]
    failed_stage = _failed_stage(recorder.stage_events, error)
    snapshot = _build_snapshot(case, recorder, response)
    passed = status == case.expected_status and (
        case.expected_terminal_stage is None or failed_stage == case.expected_terminal_stage.value
    )
    return PipelineCaseResult(
        case_id=case.case_id,
        scenario_type=case.scenario_type,
        passed=passed,
        status=status.value,
        run_id=run_id,
        failed_stage=failed_stage,
        error_type=error.failure_type.value if error is not None else None,
        stage_outcomes=_stage_outcomes(recorder.stage_events),
        retry_attempts=recorder.retry_attempts,
        fallback_decisions=recorder.fallback_decisions,
        artifact_kinds=[artifact.kind.value for artifact in recorder.artifacts],
        snapshot=snapshot,
        error_message=str(error) if error is not None else None,
    )


def run_pipeline_cases(cases: list[PipelineCase], *, artifact_root: Path | None = None) -> dict[str, Any]:
    """Run a batch of cases and return a structured report."""

    results = [run_pipeline_case(case, artifact_root=artifact_root) for case in cases]
    return {
        "case_count": len(results),
        "passed_count": sum(1 for result in results if result.passed),
        "failed_count": sum(1 for result in results if not result.passed),
        "results": [asdict(result) for result in results],
    }


def orchestrator_input(*, run_id: str, job_description_text: str):
    from backend.app.orchestration.pipeline_models import PipelineInput

    return PipelineInput(
        pipeline_run_id=run_id,
        source_profile_path=Path("data/master_profile.example.json"),
        job_description_text=job_description_text,
        template_id="ats_standard",
    )


def _build_phase3_result(
    profile_id: str,
    case: PipelineCase,
    payload: Phase3GenerationPayload,
):
    source = SourceReference(
        source_item_id="exp.northstar-tech",
        source_item_type=ItemType.EXPERIENCE,
        source_bullet_id="bullet.northstar-checkout",
        support_level=SupportLevel.DIRECT,
    )
    return GeneratedResult(
        headline=GeneratedHeadline(
            text="Senior Software Engineer",
            source_item_ids=["exp.northstar-tech"],
            provenance=[
                SourceReference(
                    source_item_id="exp.northstar-tech",
                    source_item_type=ItemType.EXPERIENCE,
                    support_level=SupportLevel.DIRECT,
                )
            ],
            support_level=SupportLevel.SYNTHESIZED,
            confidence_score=0.9,
        ),
        summary=GeneratedSummary(
            text=_summary_for_case(case),
            source_item_ids=["exp.northstar-tech"],
            source_bullet_ids=["bullet.northstar-checkout"],
            provenance=[source],
            support_level=SupportLevel.SYNTHESIZED,
            confidence_score=0.85,
        ),
        selected_experiences=[
            GeneratedExperience(
                source_item_id="exp.northstar-tech",
                organization="Northstar Tech",
                title="Sr Software Engineer",
                start_date={"raw_value": "2022-04"},
                generated_bullets=[
                    GeneratedBullet(
                        id="gen.bullet.northstar.1",
                        source_item_id="exp.northstar-tech",
                        source_item_type=ItemType.EXPERIENCE,
                        source_bullet_ids=["bullet.northstar-checkout"],
                        rewritten_text=_bullet_for_case(case),
                        rewrite_strategy="light_rewrite",
                        provenance=[source],
                        support_level=SupportLevel.DIRECT,
                        confidence_score=0.9,
                    )
                ],
                ranking_relevance_score=_score_for_case(case),
                support_level=SupportLevel.DIRECT,
                confidence_score=0.9,
            )
        ],
        skills_to_highlight=[
            GeneratedSkillHighlight(
                skill_name=skill,
                source_item_ids=["skill.javascript"],
                provenance=[
                    SourceReference(
                        source_item_id="skill.javascript",
                        source_item_type=ItemType.SKILL,
                        support_level=SupportLevel.DIRECT,
                    )
                ],
                support_level=SupportLevel.DIRECT,
                confidence_score=0.9,
            )
            for skill in payload.role_context.must_have_skills[:1]
        ],
        metadata=GenerationMetadata(source_profile_id=profile_id),
    )


from resume_optimizer.phase3_models import Phase3GenerationResult as GeneratedResult


def _skills_for_case(case: PipelineCase) -> list[str]:
    if case.scenario_type == "weak_match":
        return ["Go", "Kubernetes"]
    if case.scenario_type == "latex_sensitive_content":
        return ["LaTeX", "C++", "50% reliability"]
    if case.scenario_type == "special_characters":
        return ["C#", "C++", "Node.js"]
    return ["TypeScript", "React", "Python"]


def _skill_id(skill: str) -> str:
    token = "".join(character.lower() if character.isalnum() else "-" for character in skill)
    token = "-".join(part for part in token.split("-") if part)
    return f"skill.{token or 'unknown'}"


def _score_for_case(case: PipelineCase) -> float:
    if case.scenario_type == "weak_match":
        return 0.42
    if case.scenario_type == "moderate_match":
        return 0.68
    return 0.91


def _summary_for_case(case: PipelineCase) -> str:
    if case.scenario_type == "latex_sensitive_content":
        return "Engineer with source-backed work handling 50% reliability signals and C++ content safely."
    if case.scenario_type == "special_characters":
        return "Engineer with source-backed C#, C++, and Node.js delivery experience."
    return "Engineer with source-backed software delivery experience."


def _bullet_for_case(case: PipelineCase) -> str:
    if case.scenario_type == "latex_sensitive_content":
        return "Improved checkout reliability while preserving 50% metric notation and C++ references."
    if case.scenario_type == "special_characters":
        return "Delivered C#, C++, and Node.js improvements without unsupported claims."
    return "Redesigned checkout flow for SMB customers using source-backed delivery evidence."


def _failed_stage(stage_events: list[dict[str, Any]], error: OrchestrationError | None) -> str | None:
    if error is not None and error.stage_name is not None:
        return error.stage_name.value
    for event in reversed(stage_events):
        if event["status"] in {"failed", "blocked"}:
            return event["stage_name"]
    return None


def _stage_outcomes(stage_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "stage_name": event["stage_name"],
            "status": event["status"],
            "attempt_number": event["attempt_number"],
            "failure_type": event.get("machine_payload_json", {}).get("failure_type"),
        }
        for event in stage_events
        if event["status"] in {"succeeded", "failed", "blocked", "retrying", "skipped", "fallback_applied"}
    ]


def _build_snapshot(case: PipelineCase, recorder: PipelineRunRecorder, response) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    if "stage_sequence" in case.snapshot_fields:
        snapshot["stage_sequence"] = [
            event["stage_name"]
            for event in recorder.stage_events
            if event["status"] == "succeeded"
        ]
    if "artifact_kinds" in case.snapshot_fields:
        snapshot["artifact_kinds"] = sorted({artifact.kind.value for artifact in recorder.artifacts})
    if "final_outputs" in case.snapshot_fields:
        snapshot["final_outputs"] = response.available_outputs if response is not None else []
    return snapshot
