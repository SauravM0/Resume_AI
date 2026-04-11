# Privacy Data Handling

The backend now treats the following as sensitive operational data and keeps it out of logs, metrics, diagnostics, and exception payloads by default:

- raw job descriptions
- raw candidate profile or resume content
- email, phone, address, and profile links
- generated summaries and rewritten bullets
- final LaTeX body
- resume PDF content
- raw model/provider responses

## Redaction Strategy

Shared redaction lives in [redaction.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/privacy/redaction.py).

Operational paths use two patterns:

- inline redaction for secrets and contact data inside otherwise safe strings
- metadata-only summaries for sensitive payloads, storing only class, size/count, and a short hash prefix

Examples:

- logs and metrics store `{"redacted": true, "data_class": "...", "char_count": ..., "sha256_prefix": "..."}` instead of raw text
- exception strings are collapsed to safe generic text when they look like leaked free-form user content
- render diagnostics store counts and hashed diagnostic summaries instead of raw compiler excerpts

## Retention Policy

Temporary compile workspaces:

- are created under unique `resume-render-*` temp directories
- may contain `.tex`, `.log`, and `.pdf` during compilation
- are deleted according to the compile workspace cleanup policy
- are refused for cleanup if the path is outside the expected temp scope

Durable artifacts:

- final PDF may be persisted
- LaTeX and compile-log artifacts are treated as sensitive debug artifacts and are not persisted by default
- sensitive debug artifact persistence requires explicit opt-in via `RESUME_OPTIMIZER_PERSIST_SENSITIVE_DEBUG_ARTIFACTS=true`

Metrics and diagnostics:

- stage metrics are stored as metadata-only JSONL records
- config/runtime summaries are redacted
- render diagnostics store counts, statuses, references, and hashed diagnostic fingerprints only

## Diagnostics Policy

Developer diagnostics remain enabled only where configured, but they are privacy-safe by default:

- no raw resume or JD text in JSON logs
- no raw provider/model responses in structured metrics or stage events
- no raw compiler stdout/stderr persisted in render diagnostics

The only deeper inspection path is explicit sensitive debug artifact retention. It is disabled by default and should be enabled only for short-lived local debugging.

## Example Sanitized Log

```json
{
  "timestamp": "2026-04-10T14:52:11.840Z",
  "level": "error",
  "service": "resume_optimizer.api.generate_resume",
  "request_id": "req.45581f097df3448bbb4c9d96892de481",
  "run_id": "run.safe-error-test",
  "stage_name": "generate_structured_content",
  "event_name": "pipeline_request_failed",
  "outcome": "failure",
  "error_code": "generation_provider",
  "metadata": {
    "failure_category": "upstream_ai_error",
    "operator_diagnostic_message": "Upstream AI provider failed during structured generation. ref=sha256:d58e67dae900"
  }
}
```
