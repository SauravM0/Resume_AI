# Idempotency

The resume-generation API now applies local duplicate-run protection at the `/api/generate-resume` boundary. The implementation lives in [idempotency.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/api/idempotency.py) and is enforced by [generate_resume.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/api/routes/generate_resume.py).

## Behavior

Callers may send an optional `Idempotency-Key` header. If they do not, the backend falls back to a safe internal fingerprint built from immutable request inputs.

The duplicate policy is:

- new request: execute normally and reserve a run id before pipeline work starts
- duplicate while equivalent request is still in flight: do not start a second expensive run; return `202` with the reserved `run_id`, `status=running`, and `X-Idempotency-Status: in_flight_duplicate`
- duplicate after an equivalent request completed recently and successfully: replay the cached response body and return `X-Idempotency-Status: replayed_completed_result`

## Fingerprint Inputs

Duplicate detection only matches when immutable inputs are unchanged. The fingerprint includes:

- job description hash
- profile hash or profile file hash
- source profile id when relevant
- template id, version, and checksum
- generation preferences
- persistence flag
- relevant pipeline configuration values

Reusing the same `Idempotency-Key` with changed profile, template, or config inputs does not collide.

## Limitations

This is intentionally a conservative local implementation:

- it is process-local, not distributed
- it only replays recent successful results
- failed runs are released instead of cached for replay
- in-flight duplicate protection depends on the same app process seeing both requests

## Caller Guidance

Clients that may retry due to timeouts or network flapping should send a stable `Idempotency-Key` per intended generation action. If a caller cannot provide one, the backend still applies internal fingerprint-based protection for exact duplicate inputs seen by the same process.
