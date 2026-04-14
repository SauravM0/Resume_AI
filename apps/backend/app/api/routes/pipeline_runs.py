"""Pipeline run summary route for Phase 6 observability."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from backend.app.orchestration.event_emitter import DEFAULT_PIPELINE_EVENT_EMITTER
from backend.app.orchestration.runner import build_default_pipeline_recorder

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["pipeline-runs"])


def _safe_str(value: Any) -> str:
    """Safely convert any value to string for JSON response."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _extract_keywords_from_parsed(parsed: Any) -> list[str]:
    """Extract keywords from parsed job analysis."""
    keywords = []

    final_analysis = getattr(parsed, "final_analysis", None)
    if final_analysis:
        role_type = getattr(final_analysis, "role_type", None)
        if role_type:
            keywords.append(role_type)
        seniority = getattr(final_analysis, "seniority_level", None)
        if seniority:
            keywords.append(seniority)
        skills = getattr(final_analysis, "required_skills", None) or []
        keywords.extend(skills)

    normalized = getattr(parsed, "normalized_analysis", None)
    if normalized:
        skills = getattr(normalized, "skills", None) or []
        for skill in skills[:20]:
            skill_name = getattr(skill, "skill_name", None) or skill
            if skill_name and skill_name not in keywords:
                keywords.append(skill_name)
        domain_signals = getattr(normalized, "domain_signals", None) or []
        keywords.extend(domain_signals[:10])

    return list(dict.fromkeys(keywords))[:30]


def _extract_selected_experiences(ranked: Any) -> list[dict[str, Any]]:
    """Extract selected experiences from ranking output."""
    selection = getattr(ranked, "selection_result", None)
    if selection is None:
        return []

    experiences = getattr(selection, "selected_experiences", None) or []
    return [
        {
            "id": _safe_str(getattr(item, "source_item_id", None)),
            "title": _safe_str(getattr(item, "title", None)),
            "company": _safe_str(getattr(item, "organization", None)),
            "score": getattr(item, "relevance_score", None),
            "rationale": _safe_str(getattr(item, "ranking_explanation", None)),
        }
        for item in experiences
    ]


def _extract_selected_projects(ranked: Any) -> list[dict[str, Any]]:
    """Extract selected projects from ranking output."""
    selection = getattr(ranked, "selection_result", None)
    if selection is None:
        return []

    projects = getattr(selection, "selected_projects", None) or []
    return [
        {
            "id": _safe_str(getattr(item, "source_item_id", None)),
            "name": _safe_str(getattr(item, "name", None)),
            "score": getattr(item, "relevance_score", None),
            "rationale": _safe_str(getattr(item, "ranking_explanation", None)),
        }
        for item in projects
    ]


def _extract_selected_skills(ranked: Any) -> list[dict[str, Any]]:
    """Extract selected skills from ranking output."""
    selection = getattr(ranked, "selection_result", None)
    if selection is None:
        return []

    skills = getattr(selection, "selected_skills", None) or []
    return [
        {
            "id": _safe_str(getattr(item, "source_item_id", None)),
            "name": _safe_str(getattr(item, "skill_name", None)),
            "score": getattr(item, "relevance_score", None),
            "rationale": _safe_str(getattr(item, "ranking_explanation", None)),
        }
        for item in skills
    ]


def _build_stage_outputs(stage_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Build structured stage outputs from stage events."""
    outputs: dict[str, Any] = {}

    for event in stage_events:
        stage_name = event.get("stage_name", "")
        status = event.get("status", "")
        machine_payload = event.get("machine_payload_json", {})

        if stage_name == "parse_job_description" and status == "succeeded":
            outputs["phase_1_job_analysis"] = {
                "status": "completed",
                "data": machine_payload,
            }
        elif stage_name == "rank_select_evidence" and status == "succeeded":
            outputs["phase_2_selection"] = {
                "status": "completed",
                "data": machine_payload,
            }
        elif stage_name == "generate_structured_content" and status == "succeeded":
            outputs["phase_3_generation_plan"] = {
                "status": "completed",
                "data": machine_payload,
            }
        elif stage_name == "verify_generated_content" and status == "succeeded":
            outputs["phase_4_verification"] = {
                "status": "completed",
                "data": machine_payload,
            }
        elif stage_name == "render_deterministic_latex" and status == "succeeded":
            outputs["phase_5_template_render"] = {
                "status": "completed",
                "data": machine_payload,
            }
        elif stage_name == "compile_pdf" and status == "succeeded":
            outputs["phase_6_pdf_artifact"] = {
                "status": "completed",
                "data": machine_payload,
            }

    return outputs


def _classify_failure(
    failure_type: str | None, failure_message: str | None
) -> dict[str, Any]:
    """Classify failure into transport, profile validation, AI config, parse, template, or PDF."""
    if not failure_type:
        return {
            "category": "unknown",
            "stage": "not_reported",
            "detail": "No failure type provided",
        }

    failure_lower = (failure_type or "").lower()
    message_lower = (failure_message or "").lower()

    if "transport" in failure_lower or "timeout" in failure_lower:
        return {"category": "transport", "stage": "network", "detail": failure_type}
    if "profile" in failure_lower and "load" in failure_lower:
        return {
            "category": "profile_validation",
            "stage": "load_source_profile",
            "detail": failure_type,
        }
    if "profile" in failure_lower and "normalization" in failure_lower:
        return {
            "category": "profile_validation",
            "stage": "normalize_source_data",
            "detail": failure_type,
        }
    if (
        "provider" in failure_lower
        or "api_key" in failure_lower
        or "config" in failure_lower
    ):
        return {
            "category": "ai_provider_config",
            "stage": "generation",
            "detail": failure_type,
        }
    if (
        "parse" in failure_lower
        or "schema" in failure_lower
        or "model_output" in failure_lower
    ):
        return {
            "category": "prompt_response_parse",
            "stage": "parse_job_description",
            "detail": failure_type,
        }
    if "generation" in failure_lower:
        return {
            "category": "prompt_response_parse",
            "stage": "generate_structured_content",
            "detail": failure_type,
        }
    if "render" in failure_lower or "latex" in failure_lower:
        return {
            "category": "template_fill",
            "stage": "render_deterministic_latex",
            "detail": failure_type,
        }
    if "compile" in failure_lower or "pdf" in failure_lower:
        return {
            "category": "pdf_compile",
            "stage": "compile_pdf",
            "detail": failure_type,
        }

    if "input_validation" in failure_lower:
        return {
            "category": "profile_validation",
            "stage": "validation",
            "detail": failure_type,
        }
    if "ingestion" in failure_lower:
        return {
            "category": "transport",
            "stage": "ingest_job_description",
            "detail": failure_type,
        }

    return {"category": "internal", "stage": "unknown", "detail": failure_type}


@router.get("/pipeline-runs/{run_id}/summary")
def get_pipeline_run_summary(run_id: str) -> JSONResponse:
    """Return a clean summary object for UI display and developer inspection."""

    if not run_id or not run_id.startswith("run."):
        raise HTTPException(status_code=404, detail="Run not found")

    recorder = build_default_pipeline_recorder()

    if hasattr(recorder, "repository") and recorder.repository is not None:
        try:
            run = recorder.repository.get_pipeline_run(run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="Run not found")

            stage_events = recorder.repository.get_stage_events(run_id)
            artifacts = recorder.repository.get_artifacts(run_id)

            parsed = None
            ranked = None
            generated = None

            for artifact in artifacts:
                inline_json = getattr(artifact, "inline_json", None)
                if inline_json:
                    if "phase_1_job_analysis" in str(artifact.artifact_type):
                        parsed = inline_json
                    elif "phase_2_selection" in str(artifact.artifact_type):
                        ranked = inline_json
                    elif "phase_3_result" in str(artifact.artifact_type):
                        generated = inline_json

            keywords = _extract_keywords_from_parsed(parsed) if parsed else []
            experiences = _extract_selected_experiences(ranked) if ranked else []
            projects = _extract_selected_projects(ranked) if ranked else []
            skills = _extract_selected_skills(ranked) if ranked else []
            stage_outputs = _build_stage_outputs(stage_events)

            failure_classification: dict[str, Any] | None = None
            if run.final_error_code:
                failure_classification = _classify_failure(
                    run.final_error_code,
                    run.final_error_message,
                )

            template_id = run.requested_template or "unknown"

            return JSONResponse(
                status_code=200,
                content={
                    "run_id": run.id,
                    "status": run.status,
                    "template_id": template_id,
                    "started_at": run.started_at.isoformat()
                    if run.started_at
                    else None,
                    "completed_at": run.completed_at.isoformat()
                    if run.completed_at
                    else None,
                    "duration_ms": run.duration_ms,
                    "keywords": keywords,
                    "selected_experiences": experiences,
                    "selected_projects": projects,
                    "selected_skills": skills,
                    "stage_outputs": stage_outputs,
                    "failure": failure_classification,
                    "fallback_count": sum(
                        1
                        for e in stage_events
                        if e.get("machine_payload_json", {}).get("fallback_class")
                    ),
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(
                "Failed to load run from repository",
                extra={"run_id": run_id, "error": str(exc)},
            )

    events = DEFAULT_PIPELINE_EVENT_EMITTER.history(run_id)

    if not events:
        raise HTTPException(status_code=404, detail="Run not found")

    stage_data: dict[str, Any] = {}
    for event in events:
        if event.stage_name:
            stage_data[event.stage_name.value] = {
                "status": event.machine_status,
                "metadata": event.metadata,
            }

    failed_stage = None
    failure_type = None
    for event in events:
        if event.event_type.value == "stage_failed":
            failed_stage = event.stage_name.value if event.stage_name else None
            failure_type = event.metadata.get("failure_type")
            break

    has_completed = any(e.event_type.value == "run_completed" for e in events)

    if has_completed:
        status = "succeeded"
    elif failed_stage:
        status = "failed"
    else:
        status = "running"

    return JSONResponse(
        status_code=200,
        content={
            "run_id": run_id,
            "status": status,
            "failed_stage": failed_stage,
            "failure_type": failure_type,
            "stage_events_count": len(events),
            "last_event": events[-1].machine_status if events else None,
        },
    )
