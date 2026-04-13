# Secret Handling

Secret-bearing runtime values are centralized in [config.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/config.py).

## Approved Secret Sources

Runtime secret loading is allowed only through typed config:

- `GEMINI_API_KEY`
- `DATABASE_URL`

Operational code should read them through:

- `DEFAULT_SETTINGS.get_gemini_api_key(...)`
- `DEFAULT_SETTINGS.get_database_url(...)`

Direct `os.getenv(...)` reads for these secrets are not part of the approved runtime path.

## Startup Validation

Current baseline behavior:

- `production` requires `GEMINI_API_KEY`
- `production` still blocks unsafe debug logging and unsafe diagnostics exposure
- `DATABASE_URL` is optional by default and only required by callers that explicitly ask for it
- `test` allows missing secrets so stub-safe and dry-run behavior still works

If a caller marks a secret as required, config raises a clear runtime error such as:

- `Missing required secret GEMINI_API_KEY for live_evaluation.`
- `Missing required secret DATABASE_URL for persistence.`

## Redaction Guarantees

Safe config introspection includes a `secret_status` section with:

- whether each secret is configured
- whether it is required in the active environment
- a redacted display value only

Secrets are never emitted raw in:

- config summaries
- structured logs
- sanitized exception messages
- privacy-safe diagnostics

## Example Safe Summary

```json
{
  "secret_status": {
    "approved_runtime_source": "typed_runtime_config",
    "gemini_api_key": {
      "configured": true,
      "required": true,
      "display_value": "[REDACTED]"
    },
    "database_url": {
      "configured": false,
      "required": false,
      "display_value": null
    }
  }
}
```
