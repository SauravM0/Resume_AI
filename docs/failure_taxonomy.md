# Failure Taxonomy

The pipeline now separates:

- internal stage-specific failure codes
- public-safe failure categories
- explicit retry and fallback policy

This keeps handling deterministic and prevents retries from being applied to the wrong class of failure.

## Public Failure Categories

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

## Internal Failure Code To Category Mapping

| Internal failure type | Public category |
| --- | --- |
| `input_validation` | `input_validation_error` |
| `source_profile_load` | `filesystem_error` |
| `source_profile_normalization` | `configuration_error` |
| `job_description_ingestion` | `input_validation_error` |
| `job_description_parse` | `parsing_error` |
| `ranking_selection` | `ranking_error` |
| `generation_provider` | `upstream_ai_error` |
| `generation_schema` | `malformed_model_output_error` |
| `verification_blocked` | `verification_error` |
| `verification_retryable` | `verification_error` |
| `render_contract` | `render_error` |
| `latex_render` | `render_error` |
| `pdf_compile` | `latex_compile_error` |
| `artifact_persistence` | `filesystem_error` |
| `timeout` | `timeout_error` |
| `internal` | `unexpected_internal_error` |

## Retry Matrix

| Internal failure type | Retryable | Max retries | Backoff / strategy |
| --- | --- | --- | --- |
| `input_validation` | no | 0 | none |
| `source_profile_load` | no | 0 | none |
| `source_profile_normalization` | no | 0 | none |
| `job_description_ingestion` | no | 0 | none |
| `job_description_parse` | yes | 1 | `stricter_instruction_path`, `1.0s` |
| `ranking_selection` | no | 0 | none |
| `generation_provider` | yes | 1 | `fixed_backoff`, `1.0s` |
| `generation_schema` | yes | 1 | `stricter_instruction_path`, `1.0s` |
| `verification_blocked` | no | 0 | none |
| `verification_retryable` | yes | 1 | `immediate` |
| `render_contract` | no | 0 | none |
| `latex_render` | no | 0 | none |
| `pdf_compile` | yes | 1 | `local_render_correction` |
| `artifact_persistence` | no | 0 | none |
| `timeout` | yes | 1 | `fixed_backoff`, `1.0s` |
| `internal` | no | 0 | none |

## Fallback Matrix

| Internal failure type | Allowed fallback |
| --- | --- |
| `ranking_selection` | `deterministic_best_match_subset` |
| `verification_blocked` | `source_bullet_or_safer_rewrite` |
| `latex_render` | `latex_render_correction` |
| `pdf_compile` | `latex_render_correction` after retry budget is exhausted |
| all others | none |

## Safe Messaging

`OrchestrationError` now carries:

- internal failure type
- public failure category
- safe user-facing message
- operator-facing diagnostic message
- preserved root cause reference

Public API responses use the safe message and never expose the raw internal exception string.

## Design Rules

- malformed model output may retry once
- verification hard-fail does not retry the full pipeline
- PDF compile failure may retry once and then allow only targeted render correction fallback
- configuration and validation errors fail fast
- uncategorized `TimeoutError` is normalized to `timeout`
- uncategorized filesystem-related errors in file/persistence stages are normalized to `artifact_persistence`
