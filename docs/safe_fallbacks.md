# Safe Fallbacks

This backend now uses an explicit fallback catalog for bounded recovery paths. Fallback definitions live in [backend/app/orchestration/fallbacks.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/orchestration/fallbacks.py), and run-level audit state is recorded by [backend/app/orchestration/runner.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/orchestration/runner.py).

## Fallback Catalog

Safe fallback classes currently implemented:

- `use_original_source_bullet`
  Stage: `generate_structured_content`
  Safe path: replace an unsupported rewrite with the original supported bullet text.
- `reduce_summary_to_safe_short_form`
  Stage: `generate_structured_content`
  Safe path: replace an inflated or invalid summary with a shorter source-grounded version.
- `drop_low_priority_section`
  Stage: `generate_structured_content`
  Safe path: omit optional content when deterministic page budget or render pressure requires it.
- `skip_optional_artifact_generation`
  Stage: `compile_pdf`
  Safe path: keep a successful core PDF even if optional `resume.tex` or `compile.log` persistence fails.
- `use_deterministic_parse_signals`
  Stage: `parse_job_description`
  Safe path: mark low-confidence parse runs as relying on deterministic extraction signals when parser confidence is below `0.65`.

Additional conservative catalog entries are also tracked for existing Phase 3 behaviors such as headline fallback, supported skill fallback, and deterministic metadata rebuild.

## Safe vs Unsafe Paths

Safe paths:

- restoring source-backed bullet text
- shrinking summaries to supported text
- dropping optional, low-priority content under bounded layout pressure
- skipping non-core artifact persistence after PDF success
- leaning on deterministic parse signals when parse confidence is weak

Unsafe paths that remain disallowed:

- inventing new resume claims during recovery
- silently retrying unrelated stages after a localized failure
- dropping core verified content to hide systemic errors
- treating failed PDF persistence as a successful compile fallback

## Audit Trail

Every executed fallback records:

- `fallback_class`
- `stage_name`
- `reason`
- `allowed_when`
- `quality_tradeoff`
- `affects_final_confidence`
- `final_output_downgraded`

These records are stored in-memory on the run recorder as `fallback_audits`, emitted as `fallback_applied` stage events, and included in the final `pipeline_result` artifact metadata as:

- `fallback_count`
- `fallback_classes`
- `quality_status`
- `final_confidence_level`

## Reading Diagnostics

For a downgraded run:

- `quality_status = downgraded` means at least one content-affecting fallback executed.
- `final_confidence_level = downgraded` means operators should review the fallback trail before using the run for quality benchmarking.
- `skip_optional_artifact_generation` does not downgrade content confidence, because the PDF output is already durable and truthful.
