"""Central Phase 6 resume generation orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import logging

from backend.app.cache.codecs import deserialize_normalize_source_data_output, serialize_model
from backend.app.cache.keys import build_cache_key, stable_code_hash, stable_model_hash
from backend.app.cache.storage import get_or_compute
from backend.app.observability import bind_run_id, get_request_id, log_event
from backend.app.orchestration.artifacts.artifact_manager import ArtifactManager, build_default_artifact_manager
from backend.app.orchestration.confidence import assess_run_confidence
from backend.app.orchestration.enums import (
    ArtifactKind,
    OrchestrationFailureType,
    PipelineStatus,
    StageName,
)
from backend.app.orchestration.errors import OrchestrationError, StageExecutionError
from backend.app.orchestration.fallbacks import (
    FallbackClass,
    phase3_fallback_class,
    should_use_deterministic_parse_fallback,
)
from backend.app.orchestration.pipeline_models import (
    CompilePdfInput,
    GenerateStructuredContentInput,
    IngestJobDescriptionOutput,
    LoadSourceProfileOutput,
    NormalizeSourceDataOutput,
    ParseJobDescriptionInput,
    ParseJobDescriptionOutput,
    PipelineInput,
    RankSelectEvidenceInput,
    RankSelectEvidenceOutput,
)
from backend.app.orchestration.result_builder import (
    GenerateResumePipelineResponse,
    build_pipeline_response,
)
from backend.app.orchestration.runner import PipelineRunRecorder, build_default_pipeline_recorder
from backend.app.orchestration.stage_executor import StageExecutor
from backend.app.orchestration.adapters.base import StageExecutionContext
from backend.app.orchestration.stage_registry import DEFAULT_STAGE_REGISTRY, StageRegistry
from backend.app.services.verification.audit_artifact import (
    VERIFICATION_AUDIT_ARTIFACT_SCHEMA_VERSION,
    build_verification_audit_artifact,
    serialize_verification_audit_artifact,
)
from backend.app.services.verification.types import VerificationDecisionOutcome
from resume_optimizer.job_models import RawJobDescriptionRequest
from resume_optimizer.loaders import load_and_normalize_master_profile
from resume_optimizer.normalizers import normalize_master_profile
from resume_optimizer.config import DEFAULT_SETTINGS
from resume_optimizer.validators import validate_master_profile

logger = logging.getLogger(__name__)
PROFILE_NORMALIZATION_CACHE_NAMESPACE = "profile_normalization"
PROFILE_NORMALIZATION_CACHE_TTL_SECONDS = 24 * 60 * 60


@dataclass(slots=True)
class ResumeGenerationOrchestrator:
    """Execute the full Phase 1-5 pipeline with Phase 6 persistence events."""

    recorder_factory: object = build_default_pipeline_recorder
    stage_registry: StageRegistry = field(default_factory=lambda: DEFAULT_STAGE_REGISTRY)
    artifact_manager: ArtifactManager = field(default_factory=build_default_artifact_manager)

    def run(self, request: PipelineInput) -> GenerateResumePipelineResponse:
        """Run the end-to-end resume generation pipeline."""

        recorder = self.recorder_factory()
        assert isinstance(recorder, PipelineRunRecorder)
        executor = StageExecutor(recorder)
        started_at = datetime.now(timezone.utc)
        jd_hash = _hash_text(request.job_description_text)
        run_id = recorder.create_run(
            run_id=request.pipeline_run_id,
            requested_template=request.template_id,
            requested_mode="resume_pdf",
            job_description_hash=jd_hash,
            source_profile_id=request.source_profile_id or (
                request.source_profile.id if request.source_profile is not None else None
            ),
        )
        bind_run_id(run_id)
        log_event(
            logger,
            service="resume_optimizer.orchestrator",
            event_name="pipeline_run_started",
            outcome="started",
            run_id=run_id,
            metadata={
                "template_id": request.template_id,
                "requested_mode": "resume_pdf",
                "request_id": get_request_id(),
            },
        )

        final_file_reference: str | None = None
        status = PipelineStatus.FAILED
        parsed = None
        ranked = None
        generated = None
        verified = None
        rendered = None
        compiled = None
        try:
            loaded = executor.execute(
                StageName.LOAD_SOURCE_PROFILE,
                lambda: self._load_source_profile(request),
            )
            self._record_model_artifact(recorder, StageName.LOAD_SOURCE_PROFILE, ArtifactKind.SOURCE_PROFILE, loaded)
            normalized = executor.execute(
                StageName.NORMALIZE_SOURCE_DATA,
                lambda: self._normalize_source_data(loaded),
            )
            self._record_model_artifact(recorder, StageName.NORMALIZE_SOURCE_DATA, ArtifactKind.NORMALIZED_PROFILE, normalized)
            ingested = executor.execute(
                StageName.INGEST_JOB_DESCRIPTION,
                lambda: self._ingest_job_description(request, jd_hash),
            )
            self._record_model_artifact(recorder, StageName.INGEST_JOB_DESCRIPTION, ArtifactKind.RAW_JOB_DESCRIPTION, ingested)
            parsed = executor.execute(
                StageName.PARSE_JOB_DESCRIPTION,
                lambda: self.stage_registry.execute(
                    StageName.PARSE_JOB_DESCRIPTION,
                    ParseJobDescriptionInput(request=ingested.request),
                    self._stage_context(run_id, recorder, StageName.PARSE_JOB_DESCRIPTION),
                ),
            )
            self._record_parse_fallbacks(recorder, parsed)
            self._record_parse_job_description_artifacts(recorder, parsed)
            ranked = executor.execute(
                StageName.RANK_SELECT_EVIDENCE,
                lambda: self.stage_registry.execute(
                    StageName.RANK_SELECT_EVIDENCE,
                    self._rank_select_evidence_input(parsed, normalized),
                    self._stage_context(run_id, recorder, StageName.RANK_SELECT_EVIDENCE),
                ),
            )
            self._record_model_artifact(recorder, StageName.RANK_SELECT_EVIDENCE, ArtifactKind.PHASE2_SELECTION, ranked)
            generated = executor.execute(
                StageName.GENERATE_STRUCTURED_CONTENT,
                lambda: self.stage_registry.execute(
                    StageName.GENERATE_STRUCTURED_CONTENT,
                    GenerateStructuredContentInput(
                        job_analysis=parsed.normalized_analysis,
                        phase1_final_analysis=parsed.final_analysis,
                        phase2_selection=ranked.selection_result,
                        phase2_ranking=ranked.ranking_response,
                        source_profile=normalized.normalized_profile,
                        generation_preferences=request.generation_preferences,
                    ),
                    self._stage_context(run_id, recorder, StageName.GENERATE_STRUCTURED_CONTENT),
                ),
            )
            self._record_generation_fallbacks(recorder, generated.validation_report)
            self._record_model_artifact(recorder, StageName.GENERATE_STRUCTURED_CONTENT, ArtifactKind.PHASE3_RESULT, generated)
            verified = executor.execute(
                StageName.VERIFY_GENERATED_CONTENT,
                lambda: self.stage_registry.execute(
                    StageName.VERIFY_GENERATED_CONTENT,
                    self._verify_generated_content_input(parsed, normalized, generated),
                    self._stage_context(run_id, recorder, StageName.VERIFY_GENERATED_CONTENT),
                ),
            )
            self._record_verification_artifacts(
                recorder=recorder,
                run_id=run_id,
                verified=verified,
            )
            rendered = executor.execute(
                StageName.RENDER_DETERMINISTIC_LATEX,
                lambda: self.stage_registry.execute(
                    StageName.RENDER_DETERMINISTIC_LATEX,
                    self._render_latex_input(request, normalized, verified, run_id),
                    self._stage_context(run_id, recorder, StageName.RENDER_DETERMINISTIC_LATEX),
                ),
            )
            self._record_model_artifact(recorder, StageName.RENDER_DETERMINISTIC_LATEX, ArtifactKind.LATEX_DOCUMENT, rendered)
            compiled = executor.execute(
                StageName.COMPILE_PDF,
                lambda: self.stage_registry.execute(
                    StageName.COMPILE_PDF,
                    CompilePdfInput(
                        render_job_id=request.render_job_id or f"render.{run_id}",
                        template_id=request.template_id,
                        assembled_document=rendered.assembled_document,
                    ),
                    self._stage_context(run_id, recorder, StageName.COMPILE_PDF),
                ),
            )
            executor.execute(
                StageName.PERSIST_ARTIFACTS,
                lambda: self._persist_artifacts(recorder),
            )
            final_file_reference = (
                compiled.pdf_artifact_ref.uri
                if compiled.pdf_artifact_ref is not None
                else compiled.compile_result.pdf_file_path
            )
            status = self._pipeline_status_from_verification(verified.verification_report.decision_outcome)
            recorder.set_confidence_assessment(
                assess_run_confidence(
                    parsed=parsed,
                    ranked=ranked,
                    generated=generated,
                    verified=verified,
                    rendered=rendered,
                    compiled=compiled,
                    retry_attempts=recorder.retry_attempts,
                    fallback_audits=recorder.fallback_audits,
                )
            )
            recorder.finalize_run(
                status=status,
                duration_ms=_duration_ms(started_at, datetime.now(timezone.utc)),
            )
            recorder.commit()
            log_event(
                logger,
                service="resume_optimizer.orchestrator",
                event_name="pipeline_run_completed",
                outcome="success",
                run_id=run_id,
                duration_ms=_duration_ms(started_at, datetime.now(timezone.utc)),
                metadata={
                    "status": status.value,
                    "final_confidence_level": recorder.run_diagnostics()["final_confidence_level"],
                },
            )
        except OrchestrationError as exc:
            exc.run_id = run_id
            status = PipelineStatus.BLOCKED if exc.http_status_code == 409 else PipelineStatus.FAILED
            recorder.set_confidence_assessment(
                assess_run_confidence(
                    parsed=parsed,
                    ranked=ranked,
                    generated=generated,
                    verified=verified,
                    rendered=rendered,
                    compiled=compiled,
                    retry_attempts=recorder.retry_attempts,
                    fallback_audits=recorder.fallback_audits,
                    terminal_failure_stage=exc.stage_name.value if exc.stage_name is not None else None,
                )
            )
            recorder.finalize_run(
                status=status,
                duration_ms=_duration_ms(started_at, datetime.now(timezone.utc)),
                final_error_code=exc.failure_type.value,
                final_error_message=str(exc),
            )
            recorder.commit()
            log_event(
                logger,
                level=logging.ERROR,
                service="resume_optimizer.orchestrator",
                event_name="pipeline_run_failed",
                outcome="failure",
                run_id=run_id,
                stage_name=exc.stage_name.value if exc.stage_name is not None else None,
                duration_ms=_duration_ms(started_at, datetime.now(timezone.utc)),
                error_code=exc.failure_type.value,
                metadata={
                    "status": status.value,
                    "final_confidence_level": recorder.run_diagnostics()["final_confidence_level"],
                },
            )
            raise

        return build_pipeline_response(
            run_id=run_id,
            status=status,
            artifact_manifest=recorder.artifacts,
            stage_events=recorder.stage_events,
            warnings=recorder.warnings,
            final_file_reference=final_file_reference,
        )

    def _pipeline_status_from_verification(
        self,
        decision_outcome: VerificationDecisionOutcome,
    ) -> PipelineStatus:
        """Map verification gate decisions to final pipeline status."""

        if decision_outcome == VerificationDecisionOutcome.PASS:
            return PipelineStatus.SUCCEEDED
        if decision_outcome in {
            VerificationDecisionOutcome.PASS_WITH_WARNINGS,
            VerificationDecisionOutcome.REPAIR_AND_PASS,
        }:
            return PipelineStatus.SUCCEEDED_WITH_WARNINGS
        return PipelineStatus.FAILED

    def _load_source_profile(self, request: PipelineInput) -> LoadSourceProfileOutput:
        if request.source_profile is not None:
            return LoadSourceProfileOutput(
                source_profile_id=request.source_profile.id,
                source_profile=request.source_profile,
                loaded_from="inline",
            )
        try:
            profile = load_and_normalize_master_profile(request.source_profile_path) if request.source_profile_path is not None else load_and_normalize_master_profile("data/master_profile.example.json")
        except Exception as exc:
            raise StageExecutionError(
                f"source profile loading failed: {exc}",
                failure_type=OrchestrationFailureType.SOURCE_PROFILE_LOAD,
                stage_name=StageName.LOAD_SOURCE_PROFILE,
                http_status_code=400,
            ) from exc
        if request.source_profile_id is not None and profile.id != request.source_profile_id:
            raise StageExecutionError(
                "loaded source profile id does not match requested source_profile_id",
                failure_type=OrchestrationFailureType.INPUT_VALIDATION,
                stage_name=StageName.LOAD_SOURCE_PROFILE,
                http_status_code=400,
            )
        return LoadSourceProfileOutput(
            source_profile_id=profile.id,
            source_profile=profile,
            loaded_from=str(request.source_profile_path or "data/master_profile.example.json"),
        )

    def _normalize_source_data(self, loaded: LoadSourceProfileOutput) -> NormalizeSourceDataOutput:
        cache_key = build_cache_key(
            PROFILE_NORMALIZATION_CACHE_NAMESPACE,
            {
                "source_profile_hash": stable_model_hash(loaded.source_profile),
                "normalizer_code_hash": stable_code_hash(normalize_master_profile, validate_master_profile),
            },
        )
        try:
            cached, _ = get_or_compute(
                namespace=PROFILE_NORMALIZATION_CACHE_NAMESPACE,
                key=cache_key,
                compute=lambda: self._compute_normalized_source_data(loaded),
                serialize=serialize_model,
                deserialize=deserialize_normalize_source_data_output,
                ttl_seconds=PROFILE_NORMALIZATION_CACHE_TTL_SECONDS,
                metadata={"source_profile_id": loaded.source_profile_id},
            )
            return cached
        except Exception as exc:
            raise StageExecutionError(
                f"source profile normalization failed: {exc}",
                failure_type=OrchestrationFailureType.SOURCE_PROFILE_NORMALIZATION,
                stage_name=StageName.NORMALIZE_SOURCE_DATA,
                http_status_code=400,
            ) from exc

    def _ingest_job_description(self, request: PipelineInput, jd_hash: str) -> IngestJobDescriptionOutput:
        try:
            raw_request = RawJobDescriptionRequest(
                job_description_text=request.job_description_text,
                job_posting_url=request.job_posting_url,
            )
        except Exception as exc:
            raise StageExecutionError(
                f"invalid job description input: {exc}",
                failure_type=OrchestrationFailureType.JOB_DESCRIPTION_INGESTION,
                stage_name=StageName.INGEST_JOB_DESCRIPTION,
                http_status_code=422,
            ) from exc
        return IngestJobDescriptionOutput(
            request=raw_request,
            jd_hash=jd_hash,
            source_url=request.job_posting_url,
        )

    def _rank_select_evidence_input(
        self,
        parsed: ParseJobDescriptionOutput,
        normalized: NormalizeSourceDataOutput,
    ):
        return RankSelectEvidenceInput(
            job_analysis=parsed.normalized_analysis,
            source_profile=normalized.normalized_profile,
        )

    def _verify_generated_content_input(
        self,
        parsed: ParseJobDescriptionOutput,
        normalized: NormalizeSourceDataOutput,
        generated,
    ):
        from backend.app.orchestration.pipeline_models import VerifyGeneratedContentInput

        return VerifyGeneratedContentInput(
            source_profile_id=normalized.source_profile_id,
            job_analysis=parsed.normalized_analysis,
            source_profile=normalized.normalized_profile,
            generation_payload=generated.generation_payload,
            phase3_result=generated.phase3_result,
            phase3_validation_report=generated.validation_report,
        )

    def _render_latex_input(
        self,
        request: PipelineInput,
        normalized: NormalizeSourceDataOutput,
        verified,
        run_id: str,
    ):
        from backend.app.orchestration.pipeline_models import RenderDeterministicLatexInput

        return RenderDeterministicLatexInput(
            source_profile=normalized.normalized_profile,
            rendering_output=verified.rendering_output,
            template_id=request.template_id,
            render_job_id=request.render_job_id or f"render.{run_id}",
        )

    def _stage_context(
        self,
        run_id: str,
        recorder: PipelineRunRecorder,
        stage_name: StageName,
    ) -> StageExecutionContext:
        return StageExecutionContext(
            run_id=run_id,
            stage_name=stage_name,
            recorder=recorder,
            metadata={"request_id": get_request_id()},
        )

    def _persist_artifacts(self, recorder: PipelineRunRecorder):
        recorder.record_artifact(
            stage_name=StageName.PERSIST_ARTIFACTS,
            artifact_type=ArtifactKind.PIPELINE_RESULT,
            storage_kind="inline",
            schema_version="phase6.pipeline.result.v1",
            inline_json={"artifact_count": len(recorder.artifacts)},
            metadata=recorder.run_diagnostics() | {
                "artifact_count": len(recorder.artifacts),
            },
        )
        return {
            "persisted": True,
            "artifact_count": len(recorder.artifacts),
            **recorder.run_diagnostics(),
        }

    def _record_model_artifact(
        self,
        recorder: PipelineRunRecorder,
        stage_name: StageName,
        artifact_type: ArtifactKind,
        model,
        *,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.artifact_manager.persist_inline_json(
            recorder=recorder,
            stage_name=stage_name,
            artifact_type=artifact_type,
            payload=model.model_dump(mode="json", exclude_none=True),
            metadata=metadata,
        )

    def _record_verification_artifacts(
        self,
        *,
        recorder: PipelineRunRecorder,
        run_id: str,
        verified,
    ) -> None:
        """Persist the full verification report plus a concise audit artifact."""

        self._record_model_artifact(
            recorder,
            StageName.VERIFY_GENERATED_CONTENT,
            ArtifactKind.VERIFICATION_REPORT,
            verified,
        )
        if not getattr(DEFAULT_SETTINGS, "phase6_audit_persistence_enabled", True):
            return
        audit_artifact = build_verification_audit_artifact(
            run_id=run_id,
            verification_timestamp=datetime.now(timezone.utc),
            report=verified.verification_report,
        )
        payload, _canonical_json, content_hash = serialize_verification_audit_artifact(
            audit_artifact
        )
        self.artifact_manager.persist_inline_json(
            recorder=recorder,
            stage_name=StageName.VERIFY_GENERATED_CONTENT,
            artifact_type=ArtifactKind.VERIFICATION_AUDIT,
            payload=payload,
            schema_version=VERIFICATION_AUDIT_ARTIFACT_SCHEMA_VERSION,
            content_hash=content_hash,
            metadata={
                "verification_run_id": verified.verification_run_id,
                "final_decision": verified.verification_report.decision_outcome.value,
                "final_confidence": verified.verification_report.decision_confidence,
                "internal_summary": audit_artifact.internal_summary,
            },
        )

    def _record_parse_job_description_artifacts(
        self,
        recorder: PipelineRunRecorder,
        parsed: ParseJobDescriptionOutput,
    ) -> None:
        """Persist the Parse stage output plus explicit rebuilt Phase 1 artifacts."""

        self._record_model_artifact(
            recorder,
            StageName.PARSE_JOB_DESCRIPTION,
            ArtifactKind.JOB_ANALYSIS,
            parsed,
        )
        if parsed.deterministic_extraction is not None:
            self._record_model_artifact(
                recorder,
                StageName.PARSE_JOB_DESCRIPTION,
                ArtifactKind.PHASE1_DETERMINISTIC_EXTRACTION,
                parsed.deterministic_extraction,
            )
        if parsed.llm_enrichment_payload:
            self.artifact_manager.persist_inline_json(
                recorder=recorder,
                stage_name=StageName.PARSE_JOB_DESCRIPTION,
                artifact_type=ArtifactKind.PHASE1_LLM_ENRICHMENT,
                payload=parsed.llm_enrichment_payload,
            )
        if parsed.final_analysis is not None:
            self._record_model_artifact(
                recorder,
                StageName.PARSE_JOB_DESCRIPTION,
                ArtifactKind.PHASE1_FINAL_ANALYSIS,
                parsed.final_analysis,
                metadata={
                    "parser_confidence": parsed.final_analysis.parser_confidence,
                    "jd_quality_score": parsed.final_analysis.jd_quality_score,
                },
            )

    def _record_parse_fallbacks(
        self,
        recorder: PipelineRunRecorder,
        parsed: ParseJobDescriptionOutput,
    ) -> None:
        """Audit weak-confidence parse runs that relied on deterministic signals."""

        parser_confidence = (
            parsed.final_analysis.parser_confidence
            if parsed.final_analysis is not None
            else None
        )
        if not should_use_deterministic_parse_fallback(
            parser_confidence=parser_confidence,
            has_deterministic_extraction=parsed.deterministic_extraction is not None,
        ):
            return
        recorder.record_safe_fallback(
            stage_name=StageName.PARSE_JOB_DESCRIPTION,
            fallback_class=FallbackClass.USE_DETERMINISTIC_PARSE_SIGNALS,
            reason="Parser confidence was weak; downstream stages relied on deterministic parse signals.",
            final_output_downgraded=True,
            machine_payload_json={
                "parser_confidence": parser_confidence,
            },
        )

    def _record_generation_fallbacks(self, recorder: PipelineRunRecorder, validation_report) -> None:
        """Translate existing Phase 3 conservative repairs into orchestration audits."""

        for action in validation_report.applied_fallbacks:
            fallback_class = phase3_fallback_class(action)
            if fallback_class is None:
                continue
            recorder.record_safe_fallback(
                stage_name=StageName.GENERATE_STRUCTURED_CONTENT,
                fallback_class=fallback_class,
                reason=action.message,
                final_output_downgraded=fallback_class != FallbackClass.REBUILD_GENERATION_METADATA,
                machine_payload_json={
                    "source_item_id": action.source_item_id,
                    "phase3_action_type": action.action_type.value,
                },
            )

    def _compute_normalized_source_data(
        self,
        loaded: LoadSourceProfileOutput,
    ) -> NormalizeSourceDataOutput:
        normalized = normalize_master_profile(loaded.source_profile)
        report = validate_master_profile(normalized)
        if not report.valid:
            messages = "; ".join(issue.message for issue in report.issues)
            raise ValueError(messages)
        return NormalizeSourceDataOutput(
            source_profile_id=normalized.id,
            normalized_profile=normalized,
            normalization_applied=True,
            validation_warnings=[
                issue.message
                for issue in report.issues
                if issue.severity.value != "error"
            ],
        )


def _hash_text(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


def _duration_ms(started_at: datetime, ended_at: datetime) -> int:
    return int((ended_at - started_at).total_seconds() * 1000)


DEFAULT_RESUME_GENERATION_ORCHESTRATOR = ResumeGenerationOrchestrator()
