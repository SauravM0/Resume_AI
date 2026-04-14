"""FastAPI application entry point for ResumeAI backend."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from backend.app.services.template_registry import (
    get_active_template,
    TemplateRegistryError,
)

DEFAULT_PROFILE_PATH = "data/master_profile.example.json"

_ai_validation_errors: list[str] = []


def _validate_ai_config() -> list[str]:
    """Validate AI configuration at startup."""
    errors = []
    try:
        from resume_optimizer.config import Settings

        settings = Settings()

        provider = settings.ai.provider.lower()
        model = settings.ai.model

        if not model or not model.strip():
            errors.append("AI_MODEL is required")

        if provider != "gemini":
            errors.append(f"AI_PROVIDER must be 'gemini', got: {provider}")

        if provider == "gemini":
            if not settings.ai.gemini_api_key:
                errors.append("GEMINI_API_KEY is required when AI_PROVIDER=gemini")

    except Exception as e:
        errors.append(f"Failed to load AI configuration: {e}")

    return errors


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ai_validation_errors

    logger.info("ResumeAI backend running at http://127.0.0.1:8000")
    logger.info("Health check available at http://127.0.0.1:8000/api/health")
    logger.info(
        "Master profile API available at http://127.0.0.1:8000/api/master-profile"
    )

    _ai_validation_errors = _validate_ai_config()
    if _ai_validation_errors:
        for err in _ai_validation_errors:
            logger.error(f"AI configuration error: {err}")

    yield


app = FastAPI(
    title="ResumeAI Backend",
    description="Backend API for resume generation pipeline",
    version="0.1.0",
    lifespan=lifespan,
)

health_router = APIRouter(prefix="/api", tags=["health"])


@health_router.get("/health")
def health_check() -> JSONResponse:
    """Health check endpoint for backend verification."""
    from backend.app.services.master_profile_service import (
        load_master_profile,
        is_profile_valid,
        get_master_profile_path,
    )

    profile_path = get_master_profile_path()
    try:
        profile = load_master_profile()
        profile_valid = is_profile_valid(profile)
    except Exception:
        profile_valid = False

    try:
        get_active_template()
        template_configured = True
    except (TemplateRegistryError, FileNotFoundError, OSError, ValueError):
        template_configured = False

    return JSONResponse(
        status_code=200,
        content={
            "ok": profile_valid
            and template_configured
            and len(_ai_validation_errors) == 0,
            "api": True,
            "profile_path_configured": profile_valid,
            "profile_path": str(profile_path),
            "template_configured": template_configured,
            "ai_configured": len(_ai_validation_errors) == 0,
            "ai_errors": _ai_validation_errors,
        },
    )


@health_router.get("/diagnostics/ai")
def ai_diagnostics() -> JSONResponse:
    """AI provider diagnostics endpoint."""
    global _ai_validation_errors

    try:
        from resume_optimizer.config import Settings

        settings = Settings()

        provider = settings.ai.provider
        model = settings.ai.model

        gemini_key_configured = settings.ai.gemini_api_key is not None

        return JSONResponse(
            status_code=200,
            content={
                "provider": provider,
                "model": model,
                "gemini_api_key_configured": gemini_key_configured,
                "configured": len(_ai_validation_errors) == 0,
                "errors": _ai_validation_errors,
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "provider": "unknown",
                "model": "unknown",
                "configured": False,
                "errors": [f"Failed to load AI config: {e}"],
            },
        )


app.include_router(health_router)

app.include_router(
    router=__import__("backend.app.api.routes.artifacts", fromlist=["router"]).router
)

app.include_router(
    router=__import__(
        "backend.app.api.routes.pipeline_runs", fromlist=["router"]
    ).router
)

app.include_router(
    router=__import__(
        "backend.app.api.routes.generate_resume", fromlist=["router"]
    ).router
)
app.include_router(
    router=__import__("backend.app.api.routes.resume", fromlist=["router"]).router
)
app.include_router(
    router=__import__(
        "backend.app.api.routes.progress_stream", fromlist=["router"]
    ).router
)
app.include_router(
    router=__import__("backend.app.api.routes.artifacts", fromlist=["router"]).router
)

# Register master profile router
app.include_router(
    router=__import__(
        "backend.app.api.routes.master_profile", fromlist=["router"]
    ).router
)
