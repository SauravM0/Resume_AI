"""Real end-to-end evaluation runner backed by the live orchestration stack."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import shutil

from backend.app.evaluation.artifact_models import ArtifactManifest
from backend.app.evaluation.case_models import (
    EvaluationActualOutputs,
    EvaluationCaseDefinition,
    EvaluationStageActualOutput,
)
from backend.app.evaluation.contracts import ArtifactStore
from backend.app.evaluation.enums import EvaluationRunStatus
from backend.app.evaluation.report_models import RunSummary
from backend.app.evaluation.runtime_models import (
    EvaluationDependencyStatus,
    EvaluationRunManifest,
    EvaluationRunnerConfig,
    EvaluationStageRunRecord,
)
from backend.app.orchestration.enums import (
    PipelineStatus,
    StageName,
    StageStatus,
)
from backend.app.orchestration.errors import OrchestrationError
from backend.app.orchestration.orchestrator import ResumeGenerationOrchestrator
from backend.app.orchestration.pipeline_models import (
    CompilePdfInput,
    GenerateStructuredContentInput,
    ParseJobDescriptionInput,
    PipelineInput,
)
from backend.app.orchestration.runner import PipelineRunRecorder
from backend.app.orchestration.stage_executor import StageExecutor
from backend.app.services.verification.audit_artifact import (
    build_verification_audit_artifact,
    serialize_verification_audit_artifact,
)
from resume_optimizer.config import DEFAULT_SETTINGS
from resume_optimizer.services.evidence_coverage_map_service import (
    CandidateEvidenceCoverageMapService,
)
from resume_optimizer.services.evidence_extraction_service import (
    CandidateEvidenceExtractionService,
)


STOP_AFTER_STAGE: dict[str, StageName] = {
    "parse": StageName.PARSE_JOB_DESCRIPTION,
    "selection": StageName.RANK_SELECT_EVIDENCE,
    "verification": StageName.VERIFY_GENERATED_CONTENT,
    "full": StageName.COMPILE_PDF,
}
LIVE_LLM_REQUIRED_FROM_STAGE = StageName.PARSE_JOB_DESCRIPTION


class RealPipelineRunResult:
    """Structured result bundle from the concrete real evaluation runner."""

    def __init__(
        self,
        *,
        actual_outputs: EvaluationActualOutputs,
        artifact_manifest: ArtifactManifest,
        run_manifest: EvaluationRunManifest,
        run_summary: RunSummary,
    ) -> None:
        self.actual_outputs = actual_outputs
        self.artifact_manifest = artifact_manifest
        self.run_manifest = run_manifest
        self.run_summary = run_summary


class OrchestratedRealPipelineRunner:
    """Run evaluation cases through the real backend orchestration path."""

    def __init__(
        self,
        *,
        orchestrator: ResumeGenerationOrchestrator | None = None,
    ) -> None:
        self.orchestrator = orchestrator or ResumeGenerationOrchestrator()

    def run_case(
        self,
        case: EvaluationCaseDefinition,
        *,
        artifact_store: ArtifactStore,
        config: EvaluationRunnerConfig | None = None,
    ) -> EvaluationActualOutputs:
        return self.run_case_with_details(
            case,
            artifact_store=artifact_store,
            config=config,
        ).actual_outputs

    def run_case_with_details(
        self,
        case: EvaluationCaseDefinition,
        *,
        artifact_store: ArtifactStore,
        config: EvaluationRunnerConfig | None = None,
    ) -> RealPipelineRunResult:
        resolved_config = config or EvaluationRunnerConfig()
        started_at = datetime.now(timezone.utc)
        run_id = self._deterministic_run_id(case, resolved_config)
        stop_stage = _resolve_stop_stage(resolved_config.stop_after, resolved_config.enable_render)
        dependency_checks = self._dependency_checks(
            stop_stage=stop_stage,
            config=resolved_config,
        )
        missing_dependencies = [check for check in dependency_checks if not check.available]
        stage_records: list[EvaluationStageRunRecord] = []
        recorder = PipelineRunRecorder(event_emitter=None)
        executor = StageExecutor(recorder)
        recorder.create_run(
            run_id=run_id,
            requested_template=str(case.input_payload.get("template_id", "ats_standard")),
            requested_mode="evaluation",
            job_description_hash=self._hash_text(str(case.input_payload.get("job_description_text", ""))),
            source_profile_id=str(case.input_payload.get("source_profile_id")) if case.input_payload.get("source_profile_id") else None,
        )

        if missing_dependencies and resolved_config.use_live_llm:
            message = "; ".join(check.message for check in missing_dependencies)
            artifact_manifest = artifact_store.build_manifest(run_id=run_id, case_id=case.metadata.case_id)
            manifest_path = None
            if hasattr(artifact_store, "write_json_document"):
                manifest_payload = {
                    "run_id": run_id,
                    "case_id": case.metadata.case_id,
                    "execution_mode": "real",
                    "run_status": EvaluationRunStatus.ERROR.value,
                    "missing_dependencies": [
                        item.model_dump(mode="json", exclude_none=True)
                        for item in missing_dependencies
                    ],
                    "message": message,
                }
                manifest_path = artifact_store.write_json_document(
                    run_id=run_id,
                    relative_name="run_manifest.json",
                    payload=manifest_payload,
                )
            run_manifest = EvaluationRunManifest(
                run_id=run_id,
                case_id=case.metadata.case_id,
                execution_mode="real",
                run_status=EvaluationRunStatus.ERROR,
                config=resolved_config,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                stage_records=[],
                dependency_checks=dependency_checks,
                missing_dependencies=missing_dependencies,
                final_message=message,
                report_path=str(manifest_path) if manifest_path is not None else None,
            )
            run_summary = RunSummary(
                run_id=run_id,
                case_id=case.metadata.case_id,
                pack_type=case.metadata.pack_type,
                status=EvaluationRunStatus.ERROR,
                started_at=started_at,
                finished_at=run_manifest.finished_at,
                report_path=str(manifest_path) if manifest_path is not None else None,
            )
            return RealPipelineRunResult(
                actual_outputs=EvaluationActualOutputs(
                    run_id=run_id,
                    case_id=case.metadata.case_id,
                    pipeline_status=PipelineStatus.FAILED,
                ),
                artifact_manifest=artifact_manifest,
                run_manifest=run_manifest,
                run_summary=run_summary,
            )

        request = PipelineInput.model_validate(case.input_payload)
        actual_stage_outputs: list[EvaluationStageActualOutput] = []
        final_artifact_refs = []
        pipeline_status = PipelineStatus.RUNNING
        final_message = "evaluation run completed"
        execution_mode = "real" if resolved_config.use_live_llm else "dry_run"

        try:
            loaded = executor.execute(
                StageName.LOAD_SOURCE_PROFILE,
                lambda: self.orchestrator._load_source_profile(request),
            )
            actual_stage_outputs.append(
                self._record_stage_output(
                    artifact_store=artifact_store,
                    case=case,
                    run_id=run_id,
                    stage_name=StageName.LOAD_SOURCE_PROFILE,
                    status=StageStatus.SUCCEEDED,
                    output=loaded,
                    artifact_payloads={"source_profile.json": loaded.model_dump(mode="json", exclude_none=True)},
                    stage_records=stage_records,
                    persist_artifacts=resolved_config.persist_artifacts,
                )
            )
            if stop_stage == StageName.LOAD_SOURCE_PROFILE:
                pipeline_status = PipelineStatus.SUCCEEDED
                final_message = "stopped after load_source_profile"
                raise _EarlyStop

            normalized = executor.execute(
                StageName.NORMALIZE_SOURCE_DATA,
                lambda: self.orchestrator._normalize_source_data(loaded),
            )
            actual_stage_outputs.append(
                self._record_stage_output(
                    artifact_store=artifact_store,
                    case=case,
                    run_id=run_id,
                    stage_name=StageName.NORMALIZE_SOURCE_DATA,
                    status=StageStatus.SUCCEEDED,
                    output=normalized,
                    artifact_payloads={"normalized_profile.json": normalized.model_dump(mode="json", exclude_none=True)},
                    stage_records=stage_records,
                    persist_artifacts=resolved_config.persist_artifacts,
                )
            )

            ingested = executor.execute(
                StageName.INGEST_JOB_DESCRIPTION,
                lambda: self.orchestrator._ingest_job_description(request, self._hash_text(request.job_description_text)),
            )
            actual_stage_outputs.append(
                self._record_stage_output(
                    artifact_store=artifact_store,
                    case=case,
                    run_id=run_id,
                    stage_name=StageName.INGEST_JOB_DESCRIPTION,
                    status=StageStatus.SUCCEEDED,
                    output=ingested,
                    artifact_payloads={"raw_job_description.json": ingested.model_dump(mode="json", exclude_none=True)},
                    stage_records=stage_records,
                    persist_artifacts=resolved_config.persist_artifacts,
                )
            )

            if not resolved_config.use_live_llm:
                pipeline_status = PipelineStatus.PENDING
                final_message = "dry-run stopped before live LLM stages"
                self._append_skipped_records(
                    stage_records,
                    actual_stage_outputs,
                    start_stage=StageName.PARSE_JOB_DESCRIPTION,
                    stop_stage=StageName.COMPILE_PDF,
                    message=final_message,
                )
                raise _EarlyStop

            parsed = executor.execute(
                StageName.PARSE_JOB_DESCRIPTION,
                lambda: self.orchestrator.stage_registry.execute(
                    StageName.PARSE_JOB_DESCRIPTION,
                    ParseJobDescriptionInput(request=ingested.request),
                    self.orchestrator._stage_context(run_id, recorder, StageName.PARSE_JOB_DESCRIPTION),
                ),
            )
            parse_payloads: dict[str, object] = {"parse_output.json": parsed.model_dump(mode="json", exclude_none=True)}
            if parsed.deterministic_extraction is not None:
                parse_payloads["deterministic_extraction.json"] = parsed.deterministic_extraction.model_dump(mode="json", exclude_none=True)
            if parsed.llm_enrichment_payload:
                parse_payloads["llm_enrichment.json"] = parsed.llm_enrichment_payload
            if parsed.final_analysis is not None:
                parse_payloads["final_analysis.json"] = parsed.final_analysis.model_dump(mode="json", exclude_none=True)
            actual_stage_outputs.append(
                self._record_stage_output(
                    artifact_store=artifact_store,
                    case=case,
                    run_id=run_id,
                    stage_name=StageName.PARSE_JOB_DESCRIPTION,
                    status=StageStatus.SUCCEEDED,
                    output=parsed,
                    artifact_payloads=parse_payloads,
                    stage_records=stage_records,
                    persist_artifacts=resolved_config.persist_artifacts,
                )
            )
            if stop_stage == StageName.PARSE_JOB_DESCRIPTION:
                pipeline_status = PipelineStatus.SUCCEEDED
                final_message = "stopped after parse"
                self._append_skipped_records(
                    stage_records,
                    actual_stage_outputs,
                    start_stage=StageName.RANK_SELECT_EVIDENCE,
                    stop_stage=stop_stage,
                    message="skipped because stop_after=parse",
                )
                raise _EarlyStop

            evidence_graph = CandidateEvidenceExtractionService().extract(normalized.normalized_profile)
            coverage_map = CandidateEvidenceCoverageMapService().build(evidence_graph.evidence_graph)
            ranked = executor.execute(
                StageName.RANK_SELECT_EVIDENCE,
                lambda: self.orchestrator.stage_registry.execute(
                    StageName.RANK_SELECT_EVIDENCE,
                    self.orchestrator._rank_select_evidence_input(parsed, normalized),
                    self.orchestrator._stage_context(run_id, recorder, StageName.RANK_SELECT_EVIDENCE),
                ),
            )
            actual_stage_outputs.append(
                self._record_stage_output(
                    artifact_store=artifact_store,
                    case=case,
                    run_id=run_id,
                    stage_name=StageName.RANK_SELECT_EVIDENCE,
                    status=StageStatus.SUCCEEDED,
                    output=ranked,
                    artifact_payloads={
                        "evidence_graph.json": evidence_graph.model_dump(mode="json", exclude_none=True),
                        "coverage_map.json": coverage_map.model_dump(mode="json", exclude_none=True),
                        "selection_output.json": ranked.selection_result.model_dump(mode="json", exclude_none=True),
                        "ranking_output.json": ranked.ranking_response.model_dump(mode="json", exclude_none=True),
                    },
                    stage_records=stage_records,
                    persist_artifacts=resolved_config.persist_artifacts,
                )
            )
            if stop_stage == StageName.RANK_SELECT_EVIDENCE:
                pipeline_status = PipelineStatus.SUCCEEDED
                final_message = "stopped after selection"
                self._append_skipped_records(
                    stage_records,
                    actual_stage_outputs,
                    start_stage=StageName.GENERATE_STRUCTURED_CONTENT,
                    stop_stage=stop_stage,
                    message="skipped because stop_after=selection",
                )
                raise _EarlyStop

            generated = executor.execute(
                StageName.GENERATE_STRUCTURED_CONTENT,
                lambda: self.orchestrator.stage_registry.execute(
                    StageName.GENERATE_STRUCTURED_CONTENT,
                    GenerateStructuredContentInput(
                        job_analysis=parsed.normalized_analysis,
                        phase1_final_analysis=parsed.final_analysis,
                        phase2_selection=ranked.selection_result,
                        phase2_ranking=ranked.ranking_response,
                        source_profile=normalized.normalized_profile,
                        generation_preferences=request.generation_preferences,
                    ),
                    self.orchestrator._stage_context(run_id, recorder, StageName.GENERATE_STRUCTURED_CONTENT),
                ),
            )
            actual_stage_outputs.append(
                self._record_stage_output(
                    artifact_store=artifact_store,
                    case=case,
                    run_id=run_id,
                    stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
                    status=StageStatus.SUCCEEDED,
                    output=generated,
                    artifact_payloads={
                        "phase3_request.json": generated.request.model_dump(mode="json", exclude_none=True),
                        "generation_payload.json": generated.generation_payload.model_dump(mode="json", exclude_none=True),
                        "section_plan.json": generated.section_plan.model_dump(mode="json", exclude_none=True),
                        "phase3_result.json": generated.phase3_result.model_dump(mode="json", exclude_none=True),
                        "validation_report.json": generated.validation_report.model_dump(mode="json", exclude_none=True),
                    },
                    stage_records=stage_records,
                    persist_artifacts=resolved_config.persist_artifacts,
                )
            )

            verified = executor.execute(
                StageName.VERIFY_GENERATED_CONTENT,
                lambda: self.orchestrator.stage_registry.execute(
                    StageName.VERIFY_GENERATED_CONTENT,
                    self.orchestrator._verify_generated_content_input(parsed, normalized, generated),
                    self.orchestrator._stage_context(run_id, recorder, StageName.VERIFY_GENERATED_CONTENT),
                ),
            )
            audit_artifact = build_verification_audit_artifact(
                run_id=run_id,
                verification_timestamp=datetime.now(timezone.utc),
                report=verified.verification_report,
            )
            audit_payload, _canonical_json, _content_hash = serialize_verification_audit_artifact(audit_artifact)
            verification_artifact_refs = self._record_stage_output(
                artifact_store=artifact_store,
                case=case,
                run_id=run_id,
                stage_name=StageName.VERIFY_GENERATED_CONTENT,
                status=StageStatus.SUCCEEDED,
                output=verified,
                artifact_payloads={
                    "verification_report.json": verified.verification_report.model_dump(mode="json", exclude_none=True),
                    "rendering_output.json": verified.rendering_output.model_dump(mode="json", exclude_none=True),
                    "verification_audit.json": audit_payload,
                },
                stage_records=stage_records,
                persist_artifacts=resolved_config.persist_artifacts,
            )
            actual_stage_outputs.append(verification_artifact_refs)
            if not resolved_config.enable_render or stop_stage == StageName.VERIFY_GENERATED_CONTENT:
                pipeline_status = self.orchestrator._pipeline_status_from_verification(
                    verified.verification_report.decision_outcome
                )
                final_message = (
                    "stopped after verification"
                    if stop_stage == StageName.VERIFY_GENERATED_CONTENT
                    else "render stages skipped by configuration"
                )
                self._append_skipped_records(
                    stage_records,
                    actual_stage_outputs,
                    start_stage=StageName.RENDER_DETERMINISTIC_LATEX,
                    stop_stage=stop_stage,
                    message=final_message,
                )
                raise _EarlyStop

            rendered = executor.execute(
                StageName.RENDER_DETERMINISTIC_LATEX,
                lambda: self.orchestrator.stage_registry.execute(
                    StageName.RENDER_DETERMINISTIC_LATEX,
                    self.orchestrator._render_latex_input(request, normalized, verified, run_id),
                    self.orchestrator._stage_context(run_id, recorder, StageName.RENDER_DETERMINISTIC_LATEX),
                ),
            )
            actual_stage_outputs.append(
                self._record_stage_output(
                    artifact_store=artifact_store,
                    case=case,
                    run_id=run_id,
                    stage_name=StageName.RENDER_DETERMINISTIC_LATEX,
                    status=StageStatus.SUCCEEDED,
                    output=rendered,
                    artifact_payloads={
                        "render_input.json": rendered.render_input.model_dump(mode="json", exclude_none=True),
                        "assembled_document.json": rendered.assembled_document.model_dump(mode="json", exclude_none=True),
                    },
                    stage_records=stage_records,
                    persist_artifacts=resolved_config.persist_artifacts,
                )
            )

            compiled = executor.execute(
                StageName.COMPILE_PDF,
                lambda: self.orchestrator.stage_registry.execute(
                    StageName.COMPILE_PDF,
                    CompilePdfInput(
                        render_job_id=request.render_job_id or f"render.{run_id}",
                        template_id=request.template_id,
                        assembled_document=rendered.assembled_document,
                    ),
                    self.orchestrator._stage_context(run_id, recorder, StageName.COMPILE_PDF),
                ),
            )
            compile_payloads = {
                "compile_result.json": compiled.compile_result.model_dump(mode="json", exclude_none=True),
                "compile_metadata.json": {
                    "run_id": run_id,
                    "case_id": case.metadata.case_id,
                    "stage_name": StageName.COMPILE_PDF.value,
                    "schema_version": "phase7.eval.compile_metadata.v1",
                    "compile_success": compiled.compile_result.compile_success,
                    "return_code": compiled.compile_result.return_code,
                    "pdf_file_path": compiled.compile_result.pdf_file_path,
                    "log_file_path": compiled.compile_result.log_file_path,
                    "tex_file_path": compiled.compile_result.tex_file_path,
                },
            }
            if compiled.compile_result.pdf_file_path is not None:
                compile_payloads["resume.pdf"] = Path(compiled.compile_result.pdf_file_path).read_bytes()
            if compiled.compile_result.log_file_path is not None:
                compile_payloads["compile.log"] = Path(compiled.compile_result.log_file_path).read_text(encoding="utf-8")
            if compiled.compile_result.tex_file_path is not None:
                compile_payloads["resume.tex"] = Path(compiled.compile_result.tex_file_path).read_text(encoding="utf-8")
            actual_stage_outputs.append(
                self._record_stage_output(
                    artifact_store=artifact_store,
                    case=case,
                    run_id=run_id,
                    stage_name=StageName.COMPILE_PDF,
                    status=StageStatus.SUCCEEDED,
                    output=compiled,
                    artifact_payloads=compile_payloads,
                    stage_records=stage_records,
                    persist_artifacts=resolved_config.persist_artifacts,
                )
            )
            pipeline_status = PipelineStatus.SUCCEEDED
        except _EarlyStop:
            pass
        except OrchestrationError as exc:
            pipeline_status = PipelineStatus.BLOCKED if exc.http_status_code == 409 else PipelineStatus.FAILED
            final_message = str(exc)
            stage_name = exc.stage_name or _guess_next_stage(stage_records)
            if stage_name is not None:
                stage_records.append(
                    EvaluationStageRunRecord(
                        stage_name=stage_name,
                        status=StageStatus.FAILED,
                        executed=True,
                        message=str(exc),
                    )
                )
                actual_stage_outputs.append(
                    EvaluationStageActualOutput(
                        stage_name=stage_name,
                        status=StageStatus.FAILED,
                        output_snapshot={
                            "failure_type": exc.failure_type.value,
                            "http_status_code": exc.http_status_code,
                            "retryable": exc.retryable,
                            "fallback_eligible": exc.fallback_eligible,
                        },
                    )
                )
            if not resolved_config.fail_fast:
                self._append_skipped_records(
                    stage_records,
                    actual_stage_outputs,
                    start_stage=stage_name,
                    stop_stage=stop_stage,
                    message="skipped after failure because downstream prerequisites were unavailable",
                )

        artifact_manifest = artifact_store.build_manifest(run_id=run_id, case_id=case.metadata.case_id)
        final_artifact_refs = [
            artifact_ref
            for stage_output in actual_stage_outputs
            for artifact_ref in stage_output.artifact_refs
        ]
        actual_outputs = EvaluationActualOutputs(
            run_id=run_id,
            case_id=case.metadata.case_id,
            pipeline_status=pipeline_status,
            stage_outputs=actual_stage_outputs,
            final_artifact_refs=final_artifact_refs,
            final_output_snapshot={
                "execution_mode": execution_mode,
                "stop_after": resolved_config.stop_after,
                "render_enabled": resolved_config.enable_render,
            },
        )
        run_status = _run_status_for_outputs(
            execution_mode=execution_mode,
            pipeline_status=pipeline_status,
            stage_records=stage_records,
        )
        run_manifest = EvaluationRunManifest(
            run_id=run_id,
            case_id=case.metadata.case_id,
            execution_mode=_execution_mode_for_run(
                requested_mode=execution_mode,
                stage_records=stage_records,
            ),
            run_status=run_status,
            pipeline_status=pipeline_status,
            config=resolved_config,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            stage_records=stage_records,
            dependency_checks=dependency_checks,
            missing_dependencies=missing_dependencies,
            final_message=final_message,
        )
        artifact_manifest_path = None
        summary_path = None
        if hasattr(artifact_store, "write_json_document"):
            artifact_manifest_path = artifact_store.write_manifest(artifact_manifest)
            run_manifest.artifact_manifest_path = str(artifact_manifest_path)
            summary_path = artifact_store.write_summary(run_manifest, artifact_manifest)
            run_manifest.summary_path = str(summary_path)
            run_manifest_path = artifact_store.write_json_document(
                run_id=run_id,
                relative_name="run_manifest.json",
                payload=run_manifest.model_dump(mode="json", exclude_none=True),
            )
            run_summary_report = str(run_manifest_path)
        else:
            run_summary_report = None
        run_summary = RunSummary(
            run_id=run_id,
            case_id=case.metadata.case_id,
            pack_type=case.metadata.pack_type,
            status=run_status,
            pipeline_status=pipeline_status,
            started_at=started_at,
            finished_at=run_manifest.finished_at,
            duration_ms=int((run_manifest.finished_at - started_at).total_seconds() * 1000) if run_manifest.finished_at is not None else None,
            artifact_manifest_path=str(artifact_manifest_path) if artifact_manifest_path is not None else None,
            summary_path=str(summary_path) if summary_path is not None else None,
            report_path=run_summary_report,
        )
        return RealPipelineRunResult(
            actual_outputs=actual_outputs,
            artifact_manifest=artifact_manifest,
            run_manifest=run_manifest,
            run_summary=run_summary,
        )

    def _record_stage_output(
        self,
        *,
        artifact_store: ArtifactStore,
        case: EvaluationCaseDefinition,
        run_id: str,
        stage_name: StageName,
        status: StageStatus,
        output,
        artifact_payloads: dict[str, object],
        stage_records: list[EvaluationStageRunRecord],
        persist_artifacts: bool,
    ) -> EvaluationStageActualOutput:
        artifact_refs = []
        if persist_artifacts and artifact_payloads:
            for artifact_name, payload in artifact_payloads.items():
                content_type = "application/json"
                serialized: bytes | str
                if isinstance(payload, bytes):
                    serialized = payload
                    content_type = "application/octet-stream" if not artifact_name.endswith(".pdf") else "application/pdf"
                elif isinstance(payload, str):
                    serialized = payload
                    content_type = "text/plain" if not artifact_name.endswith(".json") else "application/json"
                else:
                    serialized = payload
                entry = artifact_store.persist_stage_artifact(
                    run_id=run_id,
                    case_id=case.metadata.case_id,
                    stage_name=stage_name,
                    artifact_name=artifact_name,
                    payload=serialized,
                    content_type=content_type,
                )
                artifact_refs.append(
                    self._manifest_entry_to_artifact_ref(entry)
                )
        stage_records.append(
            EvaluationStageRunRecord(
                stage_name=stage_name,
                status=status,
                executed=True,
                artifact_count=len(artifact_refs),
                message=f"{stage_name.value} completed",
            )
        )
        return EvaluationStageActualOutput(
            stage_name=stage_name,
            status=status,
            artifact_refs=artifact_refs,
            output_snapshot=output.model_dump(mode="json", exclude_none=True) if hasattr(output, "model_dump") else output,
        )

    def _append_skipped_records(
        self,
        stage_records: list[EvaluationStageRunRecord],
        actual_outputs: list[EvaluationStageActualOutput],
        *,
        start_stage: StageName | None,
        stop_stage: StageName,
        message: str,
    ) -> None:
        if start_stage is None:
            return
        started = False
        for stage_name in [
            StageName.PARSE_JOB_DESCRIPTION,
            StageName.RANK_SELECT_EVIDENCE,
            StageName.GENERATE_STRUCTURED_CONTENT,
            StageName.VERIFY_GENERATED_CONTENT,
            StageName.RENDER_DETERMINISTIC_LATEX,
            StageName.COMPILE_PDF,
        ]:
            if stage_name == start_stage:
                started = True
            if not started:
                continue
            if any(record.stage_name == stage_name for record in stage_records):
                continue
            stage_records.append(
                EvaluationStageRunRecord(
                    stage_name=stage_name,
                    status=StageStatus.SKIPPED,
                    executed=False,
                    skipped=True,
                    message=message,
                )
            )
            actual_outputs.append(
                EvaluationStageActualOutput(
                    stage_name=stage_name,
                    status=StageStatus.SKIPPED,
                    output_snapshot={"skip_reason": message},
                )
            )
            if stage_name == stop_stage:
                break

    def _dependency_checks(
        self,
        *,
        stop_stage: StageName,
        config: EvaluationRunnerConfig,
    ) -> list[EvaluationDependencyStatus]:
        checks: list[EvaluationDependencyStatus] = []
        if config.use_live_llm and _stage_order_index(stop_stage) >= _stage_order_index(LIVE_LLM_REQUIRED_FROM_STAGE):
            key = DEFAULT_SETTINGS.get_openai_api_key()
            checks.append(
                EvaluationDependencyStatus(
                    dependency_name="openai_api_key",
                    available=bool(key),
                    message=(
                        "OPENAI_API_KEY is configured."
                        if key
                        else "Missing OPENAI_API_KEY for live job parsing and generation."
                    ),
                )
            )
        if config.enable_render and stop_stage == StageName.COMPILE_PDF:
            pdflatex_path = shutil.which("pdflatex")
            checks.append(
                EvaluationDependencyStatus(
                    dependency_name="pdflatex",
                    available=pdflatex_path is not None,
                    message=(
                        f"pdflatex available at {pdflatex_path}."
                        if pdflatex_path is not None
                        else "Missing pdflatex required for render/compile stages."
                    ),
                )
            )
        return checks

    def _manifest_entry_to_artifact_ref(self, entry) -> object:
        from backend.app.orchestration.enums import ArtifactStorageBackend
        from backend.app.orchestration.types import PipelineArtifactRef

        return PipelineArtifactRef(
            artifact_id=entry.artifact_id,
            kind=entry.artifact_kind,
            stage_name=entry.stage_name,
            storage_backend=ArtifactStorageBackend.LOCAL_FILE,
            schema_version=entry.schema_version,
            uri=entry.storage_path,
            sha256=entry.content_hash,
            size_bytes=entry.size_bytes,
            content_type=entry.content_type,
        )

    def _deterministic_run_id(
        self,
        case: EvaluationCaseDefinition,
        config: EvaluationRunnerConfig,
    ) -> str:
        digest = sha256(
            json.dumps(
                {
                    "case_id": case.metadata.case_id,
                    "input_payload": case.input_payload,
                    "config": config.model_dump(mode="json"),
                },
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:12]
        safe_case = "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in case.metadata.case_id)
        return f"eval.{safe_case}.{digest}"

    def _hash_text(self, value: str) -> str:
        return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


class _EarlyStop(Exception):
    pass


def _resolve_stop_stage(stop_after: str, enable_render: bool) -> StageName:
    try:
        stage = STOP_AFTER_STAGE[stop_after]
    except KeyError as exc:
        raise ValueError(f"unsupported stop_after value: {stop_after}") from exc
    if stop_after == "full" and not enable_render:
        return StageName.VERIFY_GENERATED_CONTENT
    return stage


def _run_status_for_outputs(
    *,
    execution_mode: str,
    pipeline_status: PipelineStatus,
    stage_records: list[EvaluationStageRunRecord],
) -> EvaluationRunStatus:
    if any(record.status == StageStatus.FAILED for record in stage_records):
        return EvaluationRunStatus.FAILED
    if execution_mode == "dry_run" or any(record.status == StageStatus.SKIPPED for record in stage_records):
        return EvaluationRunStatus.PASSED
    return EvaluationRunStatus.PASSED


def _execution_mode_for_run(
    *,
    requested_mode: str,
    stage_records: list[EvaluationStageRunRecord],
) -> str:
    if requested_mode == "dry_run":
        return "dry_run"
    if any(record.status == StageStatus.SKIPPED for record in stage_records):
        return "partially_skipped"
    return "real"


def _guess_next_stage(stage_records: list[EvaluationStageRunRecord]) -> StageName | None:
    executed = {record.stage_name for record in stage_records}
    for stage_name in [
        StageName.LOAD_SOURCE_PROFILE,
        StageName.NORMALIZE_SOURCE_DATA,
        StageName.INGEST_JOB_DESCRIPTION,
        StageName.PARSE_JOB_DESCRIPTION,
        StageName.RANK_SELECT_EVIDENCE,
        StageName.GENERATE_STRUCTURED_CONTENT,
        StageName.VERIFY_GENERATED_CONTENT,
        StageName.RENDER_DETERMINISTIC_LATEX,
        StageName.COMPILE_PDF,
    ]:
        if stage_name not in executed:
            return stage_name
    return None


def _stage_order_index(stage_name: StageName) -> int:
    ordered = [
        StageName.LOAD_SOURCE_PROFILE,
        StageName.NORMALIZE_SOURCE_DATA,
        StageName.INGEST_JOB_DESCRIPTION,
        StageName.PARSE_JOB_DESCRIPTION,
        StageName.RANK_SELECT_EVIDENCE,
        StageName.GENERATE_STRUCTURED_CONTENT,
        StageName.VERIFY_GENERATED_CONTENT,
        StageName.RENDER_DETERMINISTIC_LATEX,
        StageName.COMPILE_PDF,
    ]
    return ordered.index(stage_name)
