# Operator Runbook

This runbook is for engineers and support staff diagnosing resume-generation failures, regressions, degraded runs, cache issues, and temp-artifact buildup without inspecting raw user content.

## Scope

Use the support CLI for routine inspection:

```bash
python3 -m backend.app.support.cli health
python3 -m backend.app.support.cli recent-runs --limit 20
python3 -m backend.app.support.cli show-run --run-id <run_id>
python3 -m backend.app.support.cli safe-diagnostics --run-id <run_id>
python3 -m backend.app.support.cli failure-counts --limit 500
python3 -m backend.app.support.cli fallback-frequency --limit 500
python3 -m backend.app.support.cli retry-storms --limit 500 --threshold 3
python3 -m backend.app.support.cli cache-summary --limit 500
python3 -m backend.app.support.cli temp-artifacts --older-than-hours 24
python3 -m backend.app.support.cli temp-artifacts --purge --older-than-hours 24
```

All command output is sanitized. Raw job descriptions, candidate profile content, generated summaries, LaTeX body text, PDF content, and raw model responses must not appear in these views.

## Startup Validation

Startup configuration is validated through the typed runtime config in [config.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/config.py).

Check the active environment and storage paths:

```bash
python3 -m backend.app.support.cli health
python3 -m backend.app.config.runtime_summary
```

What to verify:

- `environment` matches `local`, `test`, or `production`.
- stage metrics and cache metrics paths exist or have existing parent directories.
- compile workspace cleanup policy is not `keep` in production.
- secret presence is visible only as redacted configured/not-configured metadata.

If startup fails, inspect:

- runtime config validation errors
- missing required secrets
- unsafe production flags such as debug logging or exposed diagnostics

## Health Checks

The `health` command is the fastest safe check:

```bash
python3 -m backend.app.support.cli health
```

Look for:

- `metrics_enabled: true`
- expected stage and cache metric file locations
- artifact root existence
- privacy-safe diagnostics flags
- secret status present but redacted

## Common Failure Categories

Failure categories come from the typed taxonomy documented in [failure_taxonomy.md](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/docs/failure_taxonomy.md).

Common ones to watch:

- `input_validation_error`
- `configuration_error`
- `upstream_ai_error`
- `malformed_model_output_error`
- `parsing_error`
- `ranking_error`
- `generation_error`
- `verification_error`
- `render_error`
- `latex_compile_error`
- `filesystem_error`
- `timeout_error`
- `unexpected_internal_error`

To inspect recent counts:

```bash
python3 -m backend.app.support.cli failure-counts --limit 1000
```

## Inspect Recent Runs

Recent runs are derived from the stage metrics store and grouped by `run_id`.

```bash
python3 -m backend.app.support.cli recent-runs --limit 20 --metrics-limit 1000
```

Fields to read:

- `run_id`
- `request_id`
- `total_latency_ms`
- `status`
- `failed_stage_count`
- `failure_categories`
- `retry_count`
- `fallback_stage_count`
- `last_stage`

Use `show-run` for one run:

```bash
python3 -m backend.app.support.cli show-run --run-id <run_id>
```

This prints stage-by-stage timing, retries, fallbacks, and safe output metadata only.

## Inspect Stage Metrics

For broad latency analysis, use the dedicated metrics CLI:

```bash
python3 -m backend.app.metrics.cli --limit 1000
```

For run-specific timing inspection:

```bash
python3 -m backend.app.support.cli show-run --run-id <run_id>
```

Use this to identify:

- slowest stage in the run
- repeated retry attempts in a stage
- whether a stage failed after fallback use

## Inspect Verification Failures Safely

Verification failures should be inspected through sanitized run details only:

```bash
python3 -m backend.app.support.cli safe-diagnostics --run-id <run_id>
```

Look for:

- `stage_name: verify_generated_content` or equivalent verification stage
- `failure_type: verification_error`
- `retry_count`
- `fallback_used`
- redacted output metadata

Do not inspect raw verification prompts, candidate text, or generated bullets through ad hoc logs or temp files.

## Identify Retry Storms

Retry storms indicate instability, bad retry policy fit, or an upstream dependency issue.

```bash
python3 -m backend.app.support.cli retry-storms --limit 1000 --threshold 3
```

Interpretation:

- a flagged run exceeded the summed retry threshold across its stages
- `stages_with_retries` shows where instability is concentrated
- repeated verification or generation retries usually indicate upstream AI or malformed output issues

If many runs are flagged in a short window, investigate upstream availability and recent config changes before increasing retry counts.

## Identify Cache Issues

Cache behavior is summarized from the cache metrics store:

```bash
python3 -m backend.app.support.cli cache-summary --limit 1000
```

Fields to watch:

- `hit_rate`
- `stale_invalidations`
- namespace-level hit and miss counts
- `status`

Typical interpretations:

- `cold_or_misconfigured`: accesses exist but hit rate is zero
- `investigate`: stale invalidations occurred and the key strategy or invalidation path should be checked
- low hit rate after a deploy may be normal until caches warm

For cache design and invalidation rules, see [safe_cache.md](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/docs/safe_cache.md).

## Clean Temp Artifact Buildup Safely

Only compiler temp workspaces with the `resume-render-*` prefix under the temp directory are eligible for purge.

List candidates first:

```bash
python3 -m backend.app.support.cli temp-artifacts --older-than-hours 24
```

Purge safely:

```bash
python3 -m backend.app.support.cli temp-artifacts --purge --older-than-hours 24
```

Safety rules:

- never manually delete arbitrary directories under temp when the CLI can do it safely
- only the bounded compile workspaces are purged
- final persisted artifacts under the configured artifact root are not touched by this command

## Safe Debugging Practices

- Prefer support CLI output over grepping raw files.
- Treat metrics and support views as the primary operator interface.
- Do not paste raw exception text, model output, resume content, or job descriptions into tickets or chat.
- Enable deeper diagnostics only through explicit, documented runtime config changes, and disable them after incident review.
- If a run is `degraded` or `unsafe`, correlate failure counts, retry storms, fallback usage, and stage timing before rerunning jobs.

## Related Docs

- [runtime_config.md](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/docs/runtime_config.md)
- [stage_metrics.md](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/docs/stage_metrics.md)
- [failure_taxonomy.md](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/docs/failure_taxonomy.md)
- [safe_cache.md](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/docs/safe_cache.md)
- [privacy_data_handling.md](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/docs/privacy_data_handling.md)
