import { useResumeGeneration } from "../../hooks/useResumeGeneration";
import type { GenerateResumeRequest } from "../../types/pipeline";
import { GenerationFailure } from "./GenerationFailure";
import { GenerationResult } from "./GenerationResult";
import { JobDescriptionForm } from "./JobDescriptionForm";
import { ProgressTracker } from "./ProgressTracker";

export interface ResumeGenerationPanelProps {
  baseUrl?: string;
}

export function ResumeGenerationPanel({ baseUrl }: ResumeGenerationPanelProps) {
  const { state, submit, reset } = useResumeGeneration({ baseUrl });

  async function handleSubmit(request: Pick<GenerateResumeRequest, "job_description_text" | "job_posting_url">) {
    try {
      await submit(request);
    } catch {
      // Error state is normalized inside useResumeGeneration.
    }
  }

  return (
    <main>
      <h1>Resume optimizer</h1>
      <JobDescriptionForm disabled={state.submitting} onSubmit={handleSubmit} />
      {state.run_id ? <p>Run ID: {state.run_id}</p> : null}
      {state.overall_status !== "idle" ? (
        <p>
          <strong>Status:</strong> {state.overall_status}
        </p>
      ) : null}
      {state.run_id ? <ProgressTracker progress={state.progress} /> : null}
      {state.error ? <GenerationFailure error={state.error} /> : null}
      {state.response ? <GenerationResult response={state.response} /> : null}
      {state.overall_status !== "idle" ? (
        <button type="button" onClick={reset} disabled={state.submitting}>
          Start another run
        </button>
      ) : null}
    </main>
  );
}
