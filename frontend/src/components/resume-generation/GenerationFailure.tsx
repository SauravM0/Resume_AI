import type { ResumeGenerationError } from "../../types/pipeline";
import { PIPELINE_STAGE_LABELS, type PipelineStageName } from "../../types/pipeline";

export interface GenerationFailureProps {
  error: ResumeGenerationError;
}

export function GenerationFailure({ error }: GenerationFailureProps) {
  const stageLabel = isPipelineStageName(error.stage_name)
    ? PIPELINE_STAGE_LABELS[error.stage_name]
    : error.stage_name;

  return (
    <section aria-label="Generation failure" role="alert">
      <h2>Generation failed</h2>
      <p>{error.message}</p>
      {stageLabel ? <p>Failed stage: {stageLabel}</p> : null}
      {error.failure_type ? <p>Error type: {error.failure_type}</p> : null}
      {error.retryable ? <p>This failure may be retryable.</p> : null}
      {error.fallback_eligible ? <p>A safe fallback may be available.</p> : null}
      {error.run_id ? <p>Run ID: {error.run_id}</p> : null}
    </section>
  );
}

function isPipelineStageName(value: unknown): value is PipelineStageName {
  return typeof value === "string" && value in PIPELINE_STAGE_LABELS;
}
