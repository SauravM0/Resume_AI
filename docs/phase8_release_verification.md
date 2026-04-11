# Phase 8 Release Verification

Phase 8 is the final production-hardening gate. It does not replace the full product regression suite. It verifies that the hardening layers added in earlier work still behave correctly before release.

## What Phase 8 Covers

The suite verifies:

- structured logging presence and privacy safety
- stage metrics completeness
- failure taxonomy behavior
- retry and fallback correctness
- safe cache correctness and invalidation
- runtime config validation
- secret redaction
- artifact cleanup safety
- internal confidence scoring
- operator tooling health
- duplicate-request protection

It also includes explicit positive and negative release-readiness scenarios such as:

- normal success path
- malformed upstream-style output classification
- retryable transient failure
- non-retryable configuration failure
- duplicate request handling
- cache-key change after profile change
- render failure driving unsafe confidence
- sanitized diagnostics behavior

## How To Run

Quick profile:

```bash
python3 -m backend.app.phase8.cli --profile quick
```

Full release gate:

```bash
python3 -m backend.app.phase8.cli --profile full
```

JSON report to file:

```bash
python3 -m backend.app.phase8.cli --profile full --format json --output data/reports/phase8_release_report.json
```

Optional pytest passthrough:

```bash
python3 -m backend.app.phase8.cli --profile full --pytest-arg -q
```

The runner uses `pytest -s` by default because this environment has previously shown capture-related tempfile issues on some targeted test runs.

## Profiles

- `quick`
  Runs the unit-level hardening gate and the dedicated Phase 8 scenario tests. Useful for local iteration and pre-push checks.
- `full`
  Runs the quick profile plus integration-level checks for stage metrics propagation and duplicate-request handling. This is the required pre-release profile.

## Release Decision Rules

Release is blocked if any blocker area fails.

Blocker areas include:

- Phase 8 scenario coverage
- structured logging and privacy
- stage metrics
- failure taxonomy
- retry and fallback policy
- safe cache
- runtime config and secrets
- artifact cleanup
- confidence scoring
- operator tooling
- duplicate request guard in the full profile

## Report Output

The generated report includes:

- pass or fail by area
- required environment settings
- known limitations
- unresolved risks
- final release recommendation

Recommendations:

- `release_candidate_approved`
  All selected blocker areas passed.
- `blocked`
  At least one blocker area failed.

## CI Integration Path

There is no existing repository workflow file in this project today. The intended CI entrypoint is the Phase 8 CLI itself:

```bash
python3 -m backend.app.phase8.cli --profile full --format json --output data/reports/phase8_release_report.json
```

The process exits with:

- `0` when the selected profile passes
- `1` when release should be blocked

This makes it safe to add as a standalone CI job without new hosted dependencies.

## Required Environment Settings

Use these defaults for repeatable verification:

- `RESUME_OPTIMIZER_ENV=test`
- install test dependencies
- run from repository root
- prefer the full profile before release approval

No live secrets are required for the current Phase 8 suite.

## Blockers and Non-Blockers

Blockers:

- any blocker-area failure
- quick profile used as the only release signal
- broken redaction or secret handling
- missing stage metrics or broken request tracing
- unsafe confidence or fallback behavior regressions

Non-blockers but still worth noting:

- known local-only limitations such as process-local idempotency scope
- bounded temp-artifact cleanup only covering compiler workspaces
- hardening suite pass without a separate broader product regression run

## Related Files

- [suite.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/phase8/suite.py)
- [cli.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/phase8/cli.py)
- [test_phase8_release_readiness.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/tests/phase8/test_phase8_release_readiness.py)
- [test_phase8_suite.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/tests/unit/test_phase8_suite.py)
