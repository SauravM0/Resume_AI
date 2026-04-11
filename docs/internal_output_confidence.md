# Internal Output Confidence

The backend now assigns an internal run-confidence classification to every end-to-end pipeline run. This is an operational truthfulness layer only; it does not change resume generation logic.

## Confidence Dimensions

The scorer evaluates these internal dimensions:

- JD parse confidence
- evidence selection confidence
- generation confidence
- verification confidence
- fallback impact
- render confidence

Each dimension gets:

- a bounded score
- a dimension-level classification
- safe gating reasons

## Final Levels

Runs are classified as:

- `strong`
- `acceptable`
- `degraded`
- `unsafe`

## Gating Rules

Current hard gates:

- verification `fail_closed` => `unsafe`
- verification not renderable => `unsafe`
- render failure or compile failure => `unsafe`

Current degradation rules:

- excessive fallback usage => `degraded`
- repeated retries without clean first-pass success => `degraded`
- weak JD parse plus weak evidence selection => `degraded`
- partial render state => `degraded`

If none of the gates fire, the final level falls back to a weighted internal score across the six dimensions.

## Operator Use

The confidence assessment is stored in internal run diagnostics and pipeline-result metadata.

Operators should use it to:

- distinguish robust outputs from merely acceptable ones
- identify degraded runs that finished but need scrutiny
- separate unsafe failed runs from healthy successful ones

This assessment is internal-only. It is not intended to expose raw scoring details to end users.
