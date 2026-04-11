# Phase 5 Rewrite Policy Reason Codes

Phase 5 now enforces conservative rewrite policy checks before Phase 6 verification.

## What changed

The old Phase 5 modules each carried their own local heuristics for inflated claims. That made summary and bullet enforcement inconsistent, and once a module fell back to safe text the original violation reasons were easy to lose.

The new guardrail layer centralizes rewrite-policy evaluation in `src/resume_optimizer/generation/rewrite_policy.py`. It returns machine-readable reason codes plus enforcement outcomes, and both `summary_service.py` and `bullet_rewrite_service.py` attach those signals to their `GenerationQualitySignals`.

## Reason codes

- `unsupported_number`
  Triggered when generated text adds numeric detail not present in source evidence.
- `unsupported_tool`
  Triggered when generated text adds tools or platforms not supported by source evidence.
- `ownership_inflation`
  Triggered when generated text upgrades ownership beyond source wording such as `helped` to `owned`.
- `leadership_inflation`
  Triggered when generated text adds unsupported leadership language such as `led` or `managed`.
- `scope_inflation`
  Triggered when generated text adds unsupported system-wide or organizational scope.
- `domain_inflation`
  Triggered when generated text implies domain specialization not supported by evidence.
- `fake_specialization`
  Triggered when generated text adds unsupported expertise or specialist claims.
- `unsupported_years_experience`
  Triggered when generated text adds years-of-experience phrasing without source support.

## Policy severities

- `hard_block`
  The text is directly unsupported and should not be used as generated.
- `soft_warning`
  The text is still usable, but should be reviewed.
- `fallback_to_source`
  Used primarily for bullet rewriting when the safe response is to preserve normalized source wording.
- `requires_regeneration`
  Used primarily for summary generation when the unsafe text should be replaced with a bounded regenerated or deterministic fallback summary.

## Integration behavior

- Summary generation evaluates the candidate summary against the shared policy layer. If blocking violations appear, the service replaces the text with a bounded fallback summary and preserves the original policy signals.
- Bullet rewriting evaluates each rewritten bullet independently. If blocking violations appear, the service replaces the rewrite with normalized source text and preserves the original policy signals.
- Downstream systems can inspect `reason_code` and `policy_severity` on `QualitySignal` records without parsing free-form warning text.
