from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _reload_config_module():
    import resume_optimizer.config as config_module

    return importlib.reload(config_module)


def test_phase6_config_prefers_phase6_env_names_and_keeps_phase4_aliases(monkeypatch) -> None:
    monkeypatch.setenv("PHASE6_SEMANTIC_MODEL", "gpt-test-phase6")
    monkeypatch.setenv("PHASE6_SEMANTIC_VERIFICATION_ENABLED", "false")
    monkeypatch.setenv("PHASE6_SEMANTIC_VERIFICATION_STRICT_MODE", "false")
    monkeypatch.setenv("PHASE6_SEMANTIC_VERIFIER_UNAVAILABLE_BEHAVIOR", "mark_needs_review")
    monkeypatch.setenv("PHASE6_AUDIT_PERSISTENCE_ENABLED", "false")
    monkeypatch.delenv("PHASE4_SEMANTIC_MODEL", raising=False)
    monkeypatch.delenv("PHASE4_SEMANTIC_VERIFICATION_ENABLED", raising=False)
    monkeypatch.delenv("PHASE4_SEMANTIC_VERIFICATION_STRICT_MODE", raising=False)
    monkeypatch.delenv("PHASE4_SEMANTIC_VERIFIER_UNAVAILABLE_BEHAVIOR", raising=False)

    reloaded = _reload_config_module()
    try:
        settings = reloaded.Settings()

        assert settings.phase6_semantic_model == "gpt-test-phase6"
        assert settings.phase6_semantic_verification_enabled is False
        assert settings.phase6_semantic_verification_strict_mode is False
        assert settings.phase6_semantic_verifier_unavailable_behavior == "mark_needs_review"
        assert settings.phase6_audit_persistence_enabled is False
        assert settings.phase4_semantic_model == settings.phase6_semantic_model
        assert settings.phase4_semantic_verification_enabled is False
        assert settings.phase4_semantic_verification_strict_mode is False
    finally:
        _reload_config_module()


def test_environment_profile_selection_works(monkeypatch) -> None:
    monkeypatch.setenv("RESUME_OPTIMIZER_ENV", "test")

    reloaded = _reload_config_module()
    try:
        settings = reloaded.Settings()

        assert settings.environment.value == "test"
        assert settings.logging.level == "WARNING"
        assert str(settings.metrics.stage_metrics_path).endswith("data/test_metrics/stage_metrics.jsonl")
        assert settings.diagnostics.audit_persistence_enabled is False
    finally:
        _reload_config_module()


def test_invalid_config_fails_startup(monkeypatch) -> None:
    monkeypatch.setenv("RESUME_OPTIMIZER_ENV", "production")
    monkeypatch.setenv("RESUME_OPTIMIZER_LOG_LEVEL", "DEBUG")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="Invalid runtime configuration"):
        _reload_config_module()

    monkeypatch.delenv("RESUME_OPTIMIZER_LOG_LEVEL", raising=False)
    monkeypatch.delenv("RESUME_OPTIMIZER_ENV", raising=False)
    _reload_config_module()


def test_safe_config_summary_redacts_secrets(monkeypatch) -> None:
    monkeypatch.setenv("RESUME_OPTIMIZER_ENV", "local")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test-secret-key-value-for-testing-purposes-only")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example.com/prod")

    reloaded = _reload_config_module()
    try:
        summary = reloaded.get_effective_config_summary()

        assert summary["security"]["gemini_api_key"] == "[REDACTED]"
        assert summary["database"]["database_url"] == "[REDACTED]"
        assert summary["secret_status"]["approved_runtime_source"] == "typed_runtime_config"
        assert summary["secret_status"]["gemini_api_key"]["configured"] is True
        assert summary["secret_status"]["gemini_api_key"]["display_value"] == "[REDACTED]"
        assert summary["secret_status"]["database_url"]["configured"] is True
        assert summary["secret_status"]["database_url"]["display_value"] == "[REDACTED]"
        assert "AIza-test-secret" not in str(summary)
        assert "db.example.com" not in str(summary)
    finally:
        _reload_config_module()


def test_partial_nested_settings_keep_defaults(monkeypatch) -> None:
    monkeypatch.delenv("RESUME_OPTIMIZER_ENV", raising=False)

    reloaded = _reload_config_module()
    try:
        settings = reloaded.Settings(logging={"level": "ERROR"})

        assert settings.logging.level == "ERROR"
        assert settings.logging.redact_sensitive_fields is True
        assert settings.logging.additional_redacted_suffixes == [
            "_text",
            "_content",
            "_payload",
        ]
    finally:
        _reload_config_module()


def test_secret_accessors_fail_clearly_when_required(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    reloaded = _reload_config_module()
    try:
        settings = reloaded.Settings(environment="local")

        with pytest.raises(RuntimeError, match="Missing required secret GEMINI_API_KEY"):
            settings.get_gemini_api_key(required=True, consumer="live_evaluation")
        with pytest.raises(RuntimeError, match="Missing required secret DATABASE_URL"):
            settings.get_database_url(required=True, consumer="persistence")
    finally:
        _reload_config_module()


def test_test_environment_allows_stub_safe_missing_secrets(monkeypatch) -> None:
    monkeypatch.setenv("RESUME_OPTIMIZER_ENV", "test")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    reloaded = _reload_config_module()
    try:
        settings = reloaded.Settings()

        assert settings.environment.value == "test"
        assert settings.get_gemini_api_key() is None
        assert settings.get_database_url() is None
        assert settings.secret_status_summary()["gemini_api_key"]["required"] is False
    finally:
        _reload_config_module()
