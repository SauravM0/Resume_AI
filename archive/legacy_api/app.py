"""Minimal FastAPI app for Phase 1, Phase 2, and Phase 3 testing endpoints."""

from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, HTTPException
from starlette.requests import Request
from backend.app.api.routes.artifacts import router as artifact_router
from backend.app.api.routes.generate_resume import router as generate_resume_router
from backend.app.api.routes.progress_stream import router as progress_stream_router
from backend.app.api.routes.resume import router as resume_router
from backend.app.observability import bind_run_id, configure_logging, generate_request_id, log_event, reset_trace_context, set_request_id
from backend.app.privacy import sanitize_exception_message
from backend.app.services.template_registry import get_active_template, TemplateRegistryError
from resume_optimizer.config import DEFAULT_SETTINGS

from .ai_service import JobAnalysisError, analyze_job_description
from .job_models import NormalizedJobAnalysis, RawJobDescriptionRequest
from .job_normalizers import normalize_job_analysis
from .phase3_generation_service import Phase3GenerationError
from .phase3_models import Phase3AssemblerInput, Phase3GenerationResult
from .ranking_models import RankingResponse
from .services.phase2_service import DEFAULT_PHASE2_SERVICE
from .services.phase3_service import DEFAULT_PHASE3_SERVICE

configure_logging()

app = FastAPI(title="Resume Optimizer API")
app.include_router(artifact_router)
app.include_router(generate_resume_router)
app.include_router(progress_stream_router)
app.include_router(resume_router)
request_logger = logging.getLogger("resume_optimizer.api")


@app.middleware("http")
async def add_request_tracing(request: Request, call_next):
    """Attach a request id to the request context and emit API boundary logs."""

    request_id = request.headers.get("X-Request-ID") or generate_request_id()
    run_token = bind_run_id(None)
    request_token = set_request_id(request_id)
    request.state.request_id = request_id
    log_event(
        request_logger,
        service="resume_optimizer.api",
        event_name="request_received",
        outcome="started",
        metadata={
            "method": request.method,
            "path": request.url.path,
        },
    )
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = int((perf_counter() - started) * 1000)
        log_event(
            request_logger,
            service="resume_optimizer.api",
            event_name="response_failed",
            outcome="failure",
            duration_ms=duration_ms,
            metadata={
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
            },
        )
        raise
    else:
        duration_ms = int((perf_counter() - started) * 1000)
        response.headers["X-Request-ID"] = request_id
        event_name = "response_sent" if response.status_code < 400 else "response_failed"
        outcome = "success" if response.status_code < 400 else "failure"
        log_event(
            request_logger,
            service="resume_optimizer.api",
            event_name=event_name,
            outcome=outcome,
            duration_ms=duration_ms,
            metadata={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
        return response
    finally:
        reset_trace_context(run_token, request_token)


@app.post("/api/analyze-job", response_model=NormalizedJobAnalysis)
def analyze_job(request: RawJobDescriptionRequest) -> NormalizedJobAnalysis:
    """Analyze a raw job description and return normalized Phase 1 output."""

    try:
        raw_analysis = analyze_job_description(request.job_description_text)
        return normalize_job_analysis(raw_analysis, request.job_description_text)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Prompt loading failed: {exc}",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Prompt loading failed: {exc}",
        ) from exc
    except JobAnalysisError as exc:
        raise HTTPException(
            status_code=502,
            detail=sanitize_exception_message(str(exc)),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"AI service setup failed: {sanitize_exception_message(str(exc))}",
        ) from exc


@app.get("/api/health")
def health() -> dict[str, bool]:
    """Return a small runtime health summary for frontend readiness checks."""

    profile_path_configured = Path(DEFAULT_SETTINGS.default_profile_path).exists()
    try:
        get_active_template()
    except (TemplateRegistryError, FileNotFoundError, OSError, ValueError):
        template_configured = False
    else:
        template_configured = True

    return {
        "ok": profile_path_configured and template_configured,
        "api": True,
        "profile_path_configured": profile_path_configured,
        "template_configured": template_configured,
    }


@app.post("/api/rank-resume-content", response_model=RankingResponse)
def rank_resume_content(job_analysis: NormalizedJobAnalysis) -> RankingResponse:
    """Rank normalized resume evidence against a normalized Phase 1 job analysis."""

    try:
        return DEFAULT_PHASE2_SERVICE.run_for_default_profile(job_analysis).ranking_response
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Master profile loading failed: {exc}",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Master profile loading failed: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Master profile validation failed: {exc}",
        ) from exc
    except TypeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Master profile validation failed: {exc}",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Phase 2 execution failed: {sanitize_exception_message(str(exc))}",
        ) from exc


@app.post("/api/generate-resume-structure", response_model=Phase3GenerationResult)
def generate_resume_structure(request: Phase3AssemblerInput) -> Phase3GenerationResult:
    """Generate strict Phase 3 structured resume content from upstream artifacts."""

    try:
        service_result = DEFAULT_PHASE3_SERVICE.run(
            request.job_analysis,
            phase2_selection=request.phase2_selection,
            phase2_ranking=request.phase2_ranking,
            source_profile=request.source_profile,
            generation_preferences=request.generation_preferences,
        )
        return service_result.phase3_result
    except Phase3GenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail=sanitize_exception_message(str(exc)),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Phase 3 assembly failed: {exc}",
        ) from exc
    except TypeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Phase 3 assembly failed: {exc}",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Phase 3 execution failed: {sanitize_exception_message(str(exc))}",
        ) from exc
