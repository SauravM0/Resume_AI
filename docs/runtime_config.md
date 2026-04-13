# Runtime Config

The runtime configuration is now centralized in [config.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/config.py). It provides validated typed settings, environment profiles, compatibility accessors for older callers, and a redacted effective-config summary.

## Environment Profiles

Supported environments:

- `local`
  Safe for development, keeps diagnostics enabled, uses normal local metrics and cache paths, and defaults compile workspace cleanup to `clean_on_success`.
- `test`
  Uses isolated test metrics and cache paths, disables audit persistence by default, and keeps diagnostics enabled.
- `production`
  Disables debug logging and internal diagnostics exposure by default, requires `GEMINI_API_KEY`, and forbids unsafe workspace retention defaults.

Select the profile with `RESUME_OPTIMIZER_ENV=local|test|production`.

## Config Schema

Top-level config areas:

- `environment`
- `logging`
- `metrics`
- `retry_policy`
- `timeouts`
- `cache`
- `artifacts`
- `diagnostics`
- `privacy`
- `models`
- `database`
- `security`

Compatibility properties remain available for existing code paths, including:

- `phase1_job_analysis_model`
- `phase3_generation_model`
- `phase6_semantic_model`
- `phase6_semantic_verification_enabled`
- `phase6_semantic_verification_strict_mode`
- `phase6_semantic_verifier_unavailable_behavior`
- `phase6_audit_persistence_enabled`

## Environment Variables

Core profile selection:

- `RESUME_OPTIMIZER_ENV`
- `DEFAULT_PROFILE_PATH`
- `DEFAULT_PROFILE_ENCODING`

Logging:

- `RESUME_OPTIMIZER_LOG_LEVEL`
- `RESUME_OPTIMIZER_REDACT_SENSITIVE_FIELDS`
- `RESUME_OPTIMIZER_ADDITIONAL_REDACTED_FIELDS`
- `RESUME_OPTIMIZER_ADDITIONAL_REDACTED_SUFFIXES`

Metrics:

- `PIPELINE_STAGE_METRICS_PATH`
- `RESUME_OPTIMIZER_CACHE_METRICS_PATH`
- `RESUME_OPTIMIZER_METRICS_ENABLED`

Retry and timeout policy:

- `RESUME_OPTIMIZER_PARSE_RETRY_MAX_ATTEMPTS`
- `RESUME_OPTIMIZER_GENERATION_RETRY_MAX_ATTEMPTS`
- `RESUME_OPTIMIZER_VERIFICATION_RETRY_MAX_ATTEMPTS`
- `RESUME_OPTIMIZER_PDF_COMPILE_RETRY_MAX_ATTEMPTS`
- `RESUME_OPTIMIZER_FIXED_BACKOFF_SECONDS`
- `RESUME_OPTIMIZER_PDF_COMPILE_TIMEOUT_SECONDS`
- `RESUME_OPTIMIZER_REQUEST_PROCESSING_TIMEOUT_SECONDS`

Cache:

- `RESUME_OPTIMIZER_CACHE_ENABLED`
- `RESUME_OPTIMIZER_CACHE_ROOT`
- `RESUME_OPTIMIZER_CACHE_MAX_ENTRIES`
- `RESUME_OPTIMIZER_CACHE_DEFAULT_TTL_SECONDS`
- `RESUME_OPTIMIZER_IDEMPOTENCY_COMPLETED_TTL_SECONDS`
- `RESUME_OPTIMIZER_IDEMPOTENCY_IN_FLIGHT_TTL_SECONDS`

Artifacts and diagnostics:

- `PIPELINE_ARTIFACT_ROOT`
- `RESUME_OPTIMIZER_COMPILE_WORKSPACE_ROOT`
- `RESUME_OPTIMIZER_COMPILE_WORKSPACE_CLEANUP_POLICY`
- `RESUME_OPTIMIZER_PERSIST_SENSITIVE_DEBUG_ARTIFACTS`
- `RESUME_OPTIMIZER_CONFIG_SUMMARY_ENABLED`
- `RESUME_OPTIMIZER_PROFILING_ENABLED`
- `RESUME_OPTIMIZER_METRICS_CLI_ENABLED`
- `PHASE6_AUDIT_PERSISTENCE_ENABLED`
- `PHASE4_AUDIT_PERSISTENCE_ENABLED`

Security and models:

- `GEMINI_API_KEY`
- `DATABASE_URL`
- `GEMINI_MODEL`
- `PHASE3_GENERATION_MODEL`
- `PHASE6_SEMANTIC_MODEL`
- `PHASE4_SEMANTIC_MODEL`
- `PHASE6_SEMANTIC_VERIFICATION_ENABLED`
- `PHASE4_SEMANTIC_VERIFICATION_ENABLED`
- `PHASE6_SEMANTIC_VERIFICATION_STRICT_MODE`
- `PHASE4_SEMANTIC_VERIFICATION_STRICT_MODE`
- `PHASE6_SEMANTIC_VERIFIER_UNAVAILABLE_BEHAVIOR`
- `PHASE4_SEMANTIC_VERIFIER_UNAVAILABLE_BEHAVIOR`

## Effective Config Summary

Operators can inspect the redacted effective config with [runtime_summary.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/config/runtime_summary.py).

It includes:

- active environment
- logging, metrics, retry, timeout, cache, and artifact policy values
- active feature flags
- secret presence and requiredness in `secret_status`
- redacted secret placeholders instead of raw secret values

## Recommended Defaults

- local: `INFO` logging, diagnostics enabled, cache enabled, compile cleanup `clean_on_success`
- test: `WARNING` logging, isolated test paths, audit persistence off
- production: `INFO` logging, diagnostics exposure off, cache enabled, compile cleanup `clean_always`, secrets required
