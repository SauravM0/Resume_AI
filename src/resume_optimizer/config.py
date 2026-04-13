"""Central validated runtime configuration for the resume-generation system."""

from __future__ import annotations

from enum import StrEnum
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

from .constants import DEFAULT_PROFILE_ENCODING, MASTER_PROFILE_EXAMPLE_PATH


class RuntimeEnvironment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"


class LoggingSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    redact_sensitive_fields: bool = True
    additional_redacted_fields: list[str] = Field(default_factory=list)
    additional_redacted_suffixes: list[str] = Field(
        default_factory=lambda: ["_text", "_content", "_payload"]
    )


class MetricsSettings(BaseModel):
    enabled: bool = True
    stage_metrics_path: Path = Path("data/metrics/stage_metrics.jsonl")
    cache_metrics_path: Path = Path("data/metrics/cache_metrics.jsonl")


class RetryPolicySettings(BaseModel):
    parse_retry_max_attempts: int = Field(default=2, ge=1, le=5)
    generation_retry_max_attempts: int = Field(default=2, ge=1, le=5)
    verification_retry_max_attempts: int = Field(default=2, ge=1, le=5)
    pdf_compile_retry_max_attempts: int = Field(default=2, ge=1, le=5)
    fixed_backoff_seconds: float = Field(default=1.0, ge=0.0, le=30.0)


class TimeoutSettings(BaseModel):
    pdf_compile_seconds: int = Field(default=45, ge=1, le=300)
    request_processing_seconds: int = Field(default=120, ge=5, le=1800)


class CacheSettings(BaseModel):
    enabled: bool = True
    root: Path = Path("data/cache")
    max_entries: int = Field(default=256, ge=1, le=10000)
    default_ttl_seconds: int = Field(default=86400, ge=1, le=7 * 24 * 60 * 60)
    idempotency_completed_ttl_seconds: int = Field(default=300, ge=1, le=24 * 60 * 60)
    idempotency_in_flight_ttl_seconds: int = Field(default=1800, ge=5, le=24 * 60 * 60)


class ArtifactRetentionSettings(BaseModel):
    artifact_root: Path = Path("data/pipeline_artifacts")
    compile_workspace_root: Path | None = None
    compile_workspace_cleanup_policy: Literal[
        "keep", "clean_on_success", "clean_always"
    ] = "clean_always"
    persist_sensitive_debug_artifacts: bool = False


class InternalDiagnosticsSettings(BaseModel):
    config_summary_enabled: bool = True
    profiling_enabled: bool = True
    metrics_cli_enabled: bool = True
    audit_persistence_enabled: bool = True


class PrivacySettings(BaseModel):
    safe_logging_enabled: bool = True
    redact_job_descriptions: bool = True
    redact_resume_content: bool = True
    expose_internal_diagnostics: bool = False


class ModelSettings(BaseModel):
    phase1_job_analysis_model: str = "gemini-1.5-flash-latest"
    phase3_generation_model: str = "gemini-1.5-flash-latest"
    phase6_semantic_model: str = "gemini-1.5-flash-latest"

    @field_validator("*")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model name must not be empty")
        return cleaned


class DatabaseSettings(BaseModel):
    database_url: SecretStr | None = None


class AISettings(BaseModel):
    provider: str = "gemini"
    model: str = "gemini-1.5-flash-latest"
    gemini_api_key: SecretStr | None = None


class SecuritySettings(BaseModel):
    gemini_api_key: SecretStr | None = None


class Settings(BaseModel):
    """Validated runtime configuration with environment profiles and compatibility accessors."""

    environment: RuntimeEnvironment = RuntimeEnvironment.LOCAL
    default_profile_path: Path = Path(MASTER_PROFILE_EXAMPLE_PATH)
    file_encoding: str = DEFAULT_PROFILE_ENCODING
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)
    retry_policy: RetryPolicySettings = Field(default_factory=RetryPolicySettings)
    timeouts: TimeoutSettings = Field(default_factory=TimeoutSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    artifacts: ArtifactRetentionSettings = Field(
        default_factory=ArtifactRetentionSettings
    )
    diagnostics: InternalDiagnosticsSettings = Field(
        default_factory=InternalDiagnosticsSettings
    )
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    ai: AISettings = Field(default_factory=AISettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    phase2_persistence_enabled: bool = False
    semantic_verification_enabled: bool = True
    semantic_verification_strict_mode: bool = True
    semantic_verifier_unavailable_behavior: str = "block"

    @model_validator(mode="before")
    @classmethod
    def populate_from_env(cls, data: Any) -> dict[str, Any]:
        if isinstance(data, Settings):
            return data.model_dump(mode="python")
        payload = dict(data or {})
        environment = RuntimeEnvironment(
            str(
                payload.get("environment") or os.getenv("RESUME_OPTIMIZER_ENV", "local")
            ).casefold()
        )
        profile = _environment_profile(environment)

        payload.setdefault("environment", environment)
        payload.setdefault(
            "default_profile_path",
            Path(os.getenv("DEFAULT_PROFILE_PATH", profile["default_profile_path"])),
        )
        payload.setdefault(
            "file_encoding",
            os.getenv("DEFAULT_PROFILE_ENCODING", DEFAULT_PROFILE_ENCODING),
        )
        payload["logging"] = _merge_mapping(
            {
                "level": os.getenv(
                    "RESUME_OPTIMIZER_LOG_LEVEL", profile["logging_level"]
                ).upper(),
                "redact_sensitive_fields": _env_bool(
                    "RESUME_OPTIMIZER_REDACT_SENSITIVE_FIELDS", True
                ),
                "additional_redacted_fields": _env_csv(
                    "RESUME_OPTIMIZER_ADDITIONAL_REDACTED_FIELDS"
                ),
                "additional_redacted_suffixes": _env_csv(
                    "RESUME_OPTIMIZER_ADDITIONAL_REDACTED_SUFFIXES",
                    default=["_text", "_content", "_payload"],
                ),
            },
            payload.get("logging"),
        )
        payload["metrics"] = _merge_mapping(
            {
                "enabled": _env_bool("RESUME_OPTIMIZER_METRICS_ENABLED", True),
                "stage_metrics_path": Path(
                    os.getenv(
                        "PIPELINE_STAGE_METRICS_PATH", profile["stage_metrics_path"]
                    )
                ),
                "cache_metrics_path": Path(
                    os.getenv(
                        "RESUME_OPTIMIZER_CACHE_METRICS_PATH",
                        profile["cache_metrics_path"],
                    )
                ),
            },
            payload.get("metrics"),
        )
        payload["retry_policy"] = _merge_mapping(
            {
                "parse_retry_max_attempts": _env_int(
                    "RESUME_OPTIMIZER_PARSE_RETRY_MAX_ATTEMPTS", 2
                ),
                "generation_retry_max_attempts": _env_int(
                    "RESUME_OPTIMIZER_GENERATION_RETRY_MAX_ATTEMPTS", 2
                ),
                "verification_retry_max_attempts": _env_int(
                    "RESUME_OPTIMIZER_VERIFICATION_RETRY_MAX_ATTEMPTS", 2
                ),
                "pdf_compile_retry_max_attempts": _env_int(
                    "RESUME_OPTIMIZER_PDF_COMPILE_RETRY_MAX_ATTEMPTS", 2
                ),
                "fixed_backoff_seconds": _env_float(
                    "RESUME_OPTIMIZER_FIXED_BACKOFF_SECONDS",
                    1.0,
                ),
            },
            payload.get("retry_policy"),
        )
        payload["timeouts"] = _merge_mapping(
            {
                "pdf_compile_seconds": _env_int(
                    "RESUME_OPTIMIZER_PDF_COMPILE_TIMEOUT_SECONDS",
                    profile["pdf_compile_timeout_seconds"],
                ),
                "request_processing_seconds": _env_int(
                    "RESUME_OPTIMIZER_REQUEST_PROCESSING_TIMEOUT_SECONDS",
                    profile["request_processing_seconds"],
                ),
            },
            payload.get("timeouts"),
        )
        payload["cache"] = _merge_mapping(
            {
                "enabled": _env_bool("RESUME_OPTIMIZER_CACHE_ENABLED", True),
                "root": Path(
                    os.getenv("RESUME_OPTIMIZER_CACHE_ROOT", profile["cache_root"])
                ),
                "max_entries": _env_int(
                    "RESUME_OPTIMIZER_CACHE_MAX_ENTRIES",
                    profile["cache_max_entries"],
                ),
                "default_ttl_seconds": _env_int(
                    "RESUME_OPTIMIZER_CACHE_DEFAULT_TTL_SECONDS", 86400
                ),
                "idempotency_completed_ttl_seconds": _env_int(
                    "RESUME_OPTIMIZER_IDEMPOTENCY_COMPLETED_TTL_SECONDS",
                    300,
                ),
                "idempotency_in_flight_ttl_seconds": _env_int(
                    "RESUME_OPTIMIZER_IDEMPOTENCY_IN_FLIGHT_TTL_SECONDS",
                    1800,
                ),
            },
            payload.get("cache"),
        )
        payload["artifacts"] = _merge_mapping(
            {
                "artifact_root": Path(
                    os.getenv("PIPELINE_ARTIFACT_ROOT", profile["artifact_root"])
                ),
                "compile_workspace_root": (
                    Path(os.environ["RESUME_OPTIMIZER_COMPILE_WORKSPACE_ROOT"])
                    if os.getenv("RESUME_OPTIMIZER_COMPILE_WORKSPACE_ROOT")
                    else None
                ),
                "compile_workspace_cleanup_policy": os.getenv(
                    "RESUME_OPTIMIZER_COMPILE_WORKSPACE_CLEANUP_POLICY",
                    profile["compile_workspace_cleanup_policy"],
                ),
                "persist_sensitive_debug_artifacts": _env_bool(
                    "RESUME_OPTIMIZER_PERSIST_SENSITIVE_DEBUG_ARTIFACTS",
                    profile["persist_sensitive_debug_artifacts"],
                ),
            },
            payload.get("artifacts"),
        )
        payload["diagnostics"] = _merge_mapping(
            {
                "config_summary_enabled": _env_bool(
                    "RESUME_OPTIMIZER_CONFIG_SUMMARY_ENABLED",
                    profile["config_summary_enabled"],
                ),
                "profiling_enabled": _env_bool(
                    "RESUME_OPTIMIZER_PROFILING_ENABLED",
                    profile["profiling_enabled"],
                ),
                "metrics_cli_enabled": _env_bool(
                    "RESUME_OPTIMIZER_METRICS_CLI_ENABLED",
                    profile["metrics_cli_enabled"],
                ),
                "audit_persistence_enabled": _env_bool(
                    "PHASE6_AUDIT_PERSISTENCE_ENABLED",
                    _env_bool(
                        "PHASE4_AUDIT_PERSISTENCE_ENABLED",
                        profile["audit_persistence_enabled"],
                    ),
                ),
            },
            payload.get("diagnostics"),
        )
        payload["privacy"] = _merge_mapping(
            {
                "safe_logging_enabled": _env_bool(
                    "RESUME_OPTIMIZER_SAFE_LOGGING_ENABLED",
                    True,
                ),
                "redact_job_descriptions": _env_bool(
                    "RESUME_OPTIMIZER_REDACT_JOB_DESCRIPTIONS",
                    True,
                ),
                "redact_resume_content": _env_bool(
                    "RESUME_OPTIMIZER_REDACT_RESUME_CONTENT",
                    True,
                ),
                "expose_internal_diagnostics": _env_bool(
                    "RESUME_OPTIMIZER_EXPOSE_INTERNAL_DIAGNOSTICS",
                    profile["expose_internal_diagnostics"],
                ),
            },
            payload.get("privacy"),
        )
        payload["models"] = _merge_mapping(
            {
                "phase1_job_analysis_model": os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest"),
                "phase3_generation_model": os.getenv(
                    "PHASE3_GENERATION_MODEL", "gemini-1.5-flash-latest"
                ),
                "phase6_semantic_model": os.getenv(
                    "PHASE6_SEMANTIC_MODEL",
                    os.getenv(
                        "PHASE4_SEMANTIC_MODEL",
                        os.getenv("GEMINI_MODEL", "gemini-1.5-flash-latest"),
                    ),
                ),
            },
            payload.get("models"),
        )
        payload["database"] = _merge_mapping(
            {
                "database_url": os.getenv("DATABASE_URL"),
            },
            payload.get("database"),
        )
        payload["ai"] = _merge_mapping(
            {
                "provider": os.getenv("AI_PROVIDER", "gemini"),
                "model": os.getenv("AI_MODEL", "gemini-1.5-flash-latest"),
                "gemini_api_key": os.getenv("GEMINI_API_KEY"),
            },
            payload.get("ai"),
        )
        payload["security"] = _merge_mapping(
            {
                "gemini_api_key": os.getenv("GEMINI_API_KEY"),
            },
            payload.get("security"),
        )
        payload.setdefault(
            "phase2_persistence_enabled",
            _env_bool("PHASE2_PERSISTENCE_ENABLED", False),
        )
        payload.setdefault(
            "semantic_verification_enabled",
            _env_bool(
                "PHASE6_SEMANTIC_VERIFICATION_ENABLED",
                _env_bool("PHASE4_SEMANTIC_VERIFICATION_ENABLED", True),
            ),
        )
        payload.setdefault(
            "semantic_verification_strict_mode",
            _env_bool(
                "PHASE6_SEMANTIC_VERIFICATION_STRICT_MODE",
                _env_bool("PHASE4_SEMANTIC_VERIFICATION_STRICT_MODE", True),
            ),
        )
        payload.setdefault(
            "semantic_verifier_unavailable_behavior",
            os.getenv(
                "PHASE6_SEMANTIC_VERIFIER_UNAVAILABLE_BEHAVIOR",
                os.getenv("PHASE4_SEMANTIC_VERIFIER_UNAVAILABLE_BEHAVIOR", "block"),
            ),
        )
        return payload

    @field_validator("file_encoding")
    @classmethod
    def validate_file_encoding(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("file_encoding must not be empty")
        return cleaned

    @field_validator("semantic_verifier_unavailable_behavior")
    @classmethod
    def validate_semantic_behavior(cls, value: str) -> str:
        cleaned = value.strip()
        allowed = {"block", "mark_needs_review"}
        if cleaned not in allowed:
            raise ValueError(
                "semantic_verifier_unavailable_behavior must be one of: "
                + ", ".join(sorted(allowed))
            )
        return cleaned

    @model_validator(mode="after")
    def validate_runtime_safety(self) -> "Settings":
        if self.environment == RuntimeEnvironment.PRODUCTION:
            if self.logging.level == "DEBUG":
                raise ValueError("production logging level must not be DEBUG")
            if self.security.gemini_api_key is None:
                raise ValueError("GEMINI_API_KEY is required in production")
            if self.privacy.expose_internal_diagnostics:
                raise ValueError("production must not expose internal diagnostics")
            if self.artifacts.compile_workspace_cleanup_policy == "keep":
                raise ValueError(
                    "production must not keep compile workspaces by default"
                )
        if not self.default_profile_path:
            raise ValueError("default_profile_path is required")
        return self

    @property
    def phase1_job_analysis_model(self) -> str:
        return self.models.phase1_job_analysis_model

    @property
    def phase3_generation_model(self) -> str:
        return self.models.phase3_generation_model

    @property
    def phase6_semantic_model(self) -> str:
        return self.models.phase6_semantic_model

    @property
    def phase6_semantic_verification_enabled(self) -> bool:
        return self.semantic_verification_enabled

    @property
    def phase6_semantic_verification_strict_mode(self) -> bool:
        return self.semantic_verification_strict_mode

    @property
    def phase6_semantic_verifier_unavailable_behavior(self) -> str:
        return self.semantic_verifier_unavailable_behavior

    @property
    def phase6_audit_persistence_enabled(self) -> bool:
        return self.diagnostics.audit_persistence_enabled

    @property
    def phase4_semantic_model(self) -> str:
        return self.phase6_semantic_model

    @property
    def phase4_semantic_verification_enabled(self) -> bool:
        return self.phase6_semantic_verification_enabled

    @property
    def phase4_semantic_verification_strict_mode(self) -> bool:
        return self.phase6_semantic_verification_strict_mode

    @property
    def phase4_semantic_verifier_unavailable_behavior(self) -> str:
        return self.phase6_semantic_verifier_unavailable_behavior

    @property
    def phase2_safe_logging_enabled(self) -> bool:
        return self.privacy.safe_logging_enabled

    @property
    def phase3_safe_logging_enabled(self) -> bool:
        return self.privacy.safe_logging_enabled

    def get_gemini_api_key(
        self, *, required: bool = False, consumer: str = "runtime"
    ) -> str | None:
        """Return the configured Gemini API key or fail clearly when required."""

        secret = self.security.gemini_api_key
        value = secret.get_secret_value() if secret is not None else None
        if required and not value:
            raise RuntimeError(
                f"Missing required secret GEMINI_API_KEY for {consumer}."
            )
        return value

    def get_ai_provider(self) -> str:
        """Return the configured AI provider."""
        return self.ai.provider

    def get_ai_model(self) -> str:
        """Return the configured AI model."""
        return self.ai.model

    def is_ai_configured(self) -> bool:
        """Check if AI provider is configured with required credentials."""
        provider = self.ai.provider.lower()
        if provider == "gemini":
            return self.ai.gemini_api_key is not None
        return False

    def get_database_url(
        self, *, required: bool = False, consumer: str = "runtime"
    ) -> str | None:
        """Return the configured database URL or fail clearly when required."""

        secret = self.database.database_url
        value = secret.get_secret_value() if secret is not None else None
        if required and not value:
            raise RuntimeError(f"Missing required secret DATABASE_URL for {consumer}.")
        return value

    def secret_status_summary(self) -> dict[str, object]:
        """Return redacted secret presence and source metadata for operators."""

        return {
            "approved_runtime_source": "typed_runtime_config",
            "gemini_api_key": {
                "configured": self.security.gemini_api_key is not None,
                "required": self.environment == RuntimeEnvironment.PRODUCTION,
                "display_value": _redact_secret(self.security.gemini_api_key),
            },
            "database_url": {
                "configured": self.database.database_url is not None,
                "required": False,
                "display_value": _redact_secret(self.database.database_url),
            },
        }

    def safe_summary(self) -> dict[str, object]:
        """Return a redacted operator-safe configuration summary."""

        return {
            "environment": self.environment.value,
            "default_profile_path": str(self.default_profile_path),
            "file_encoding": self.file_encoding,
            "logging": self.logging.model_dump(mode="json"),
            "metrics": {
                "enabled": self.metrics.enabled,
                "stage_metrics_path": str(self.metrics.stage_metrics_path),
                "cache_metrics_path": str(self.metrics.cache_metrics_path),
            },
            "retry_policy": self.retry_policy.model_dump(mode="json"),
            "timeouts": self.timeouts.model_dump(mode="json"),
            "cache": {
                "enabled": self.cache.enabled,
                "root": str(self.cache.root),
                "max_entries": self.cache.max_entries,
                "default_ttl_seconds": self.cache.default_ttl_seconds,
                "idempotency_completed_ttl_seconds": self.cache.idempotency_completed_ttl_seconds,
                "idempotency_in_flight_ttl_seconds": self.cache.idempotency_in_flight_ttl_seconds,
            },
            "artifacts": {
                "artifact_root": str(self.artifacts.artifact_root),
                "compile_workspace_root": (
                    str(self.artifacts.compile_workspace_root)
                    if self.artifacts.compile_workspace_root is not None
                    else None
                ),
                "compile_workspace_cleanup_policy": self.artifacts.compile_workspace_cleanup_policy,
                "persist_sensitive_debug_artifacts": self.artifacts.persist_sensitive_debug_artifacts,
            },
            "diagnostics": self.diagnostics.model_dump(mode="json"),
            "privacy": self.privacy.model_dump(mode="json"),
            "models": self.models.model_dump(mode="json"),
            "database": {
                "database_url": _redact_secret(self.database.database_url),
            },
            "security": {
                "gemini_api_key": _redact_secret(self.security.gemini_api_key),
            },
            "secret_status": self.secret_status_summary(),
            "feature_flags": {
                "phase2_persistence_enabled": self.phase2_persistence_enabled,
                "phase6_audit_persistence_enabled": self.phase6_audit_persistence_enabled,
                "phase6_semantic_verification_enabled": self.phase6_semantic_verification_enabled,
                "phase6_semantic_verification_strict_mode": self.phase6_semantic_verification_strict_mode,
                "phase6_semantic_verifier_unavailable_behavior": self.phase6_semantic_verifier_unavailable_behavior,
                "phase2_safe_logging_enabled": self.phase2_safe_logging_enabled,
                "phase3_safe_logging_enabled": self.phase3_safe_logging_enabled,
            },
        }


def load_settings() -> Settings:
    """Load validated settings from the current environment."""

    try:
        return Settings()
    except ValidationError as exc:
        raise RuntimeError(f"Invalid runtime configuration: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"Invalid runtime configuration: {exc}") from exc


def get_effective_config_summary() -> dict[str, object]:
    """Return the active safe configuration summary."""

    return DEFAULT_SETTINGS.safe_summary()


def _environment_profile(environment: RuntimeEnvironment) -> dict[str, object]:
    if environment == RuntimeEnvironment.TEST:
        return {
            "default_profile_path": MASTER_PROFILE_EXAMPLE_PATH,
            "logging_level": "WARNING",
            "stage_metrics_path": "data/test_metrics/stage_metrics.jsonl",
            "cache_metrics_path": "data/test_metrics/cache_metrics.jsonl",
            "cache_root": "data/test_cache",
            "cache_max_entries": 64,
            "artifact_root": "data/test_artifacts",
            "compile_workspace_cleanup_policy": "clean_always",
            "persist_sensitive_debug_artifacts": False,
            "config_summary_enabled": True,
            "profiling_enabled": True,
            "metrics_cli_enabled": True,
            "audit_persistence_enabled": False,
            "pdf_compile_timeout_seconds": 20,
            "request_processing_seconds": 60,
            "expose_internal_diagnostics": False,
        }
    if environment == RuntimeEnvironment.PRODUCTION:
        return {
            "default_profile_path": MASTER_PROFILE_EXAMPLE_PATH,
            "logging_level": "INFO",
            "stage_metrics_path": "data/metrics/stage_metrics.jsonl",
            "cache_metrics_path": "data/metrics/cache_metrics.jsonl",
            "cache_root": "data/cache",
            "cache_max_entries": 1024,
            "artifact_root": "data/pipeline_artifacts",
            "compile_workspace_cleanup_policy": "clean_always",
            "persist_sensitive_debug_artifacts": False,
            "config_summary_enabled": False,
            "profiling_enabled": False,
            "metrics_cli_enabled": True,
            "audit_persistence_enabled": True,
            "pdf_compile_timeout_seconds": 45,
            "request_processing_seconds": 180,
            "expose_internal_diagnostics": False,
        }
    return {
        "default_profile_path": MASTER_PROFILE_EXAMPLE_PATH,
        "logging_level": "INFO",
        "stage_metrics_path": "data/metrics/stage_metrics.jsonl",
        "cache_metrics_path": "data/metrics/cache_metrics.jsonl",
        "cache_root": "data/cache",
        "cache_max_entries": 256,
        "artifact_root": "data/pipeline_artifacts",
        "compile_workspace_cleanup_policy": "clean_on_success",
        "persist_sensitive_debug_artifacts": False,
        "config_summary_enabled": True,
        "profiling_enabled": True,
        "metrics_cli_enabled": True,
        "audit_persistence_enabled": True,
        "pdf_compile_timeout_seconds": 45,
        "request_processing_seconds": 120,
        "expose_internal_diagnostics": True,
    }


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    lowered = value.strip().casefold()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None else float(value)


def _env_csv(name: str, default: list[str] | None = None) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


def _merge_mapping(defaults: dict[str, Any], overrides: Any) -> dict[str, Any]:
    if overrides is None:
        return defaults
    if not isinstance(overrides, dict):
        return overrides
    merged = dict(defaults)
    merged.update(overrides)
    return merged


def _redact_secret(secret: SecretStr | None) -> str | None:
    if secret is None:
        return None
    return "[REDACTED]"


DEFAULT_SETTINGS = load_settings()
