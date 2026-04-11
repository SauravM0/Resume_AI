import type { PipelineProgressState } from "../../types/pipeline";
import { PIPELINE_STAGE_LABELS } from "../../types/pipeline";

export interface ProgressTrackerProps {
  progress: PipelineProgressState;
}

export function ProgressTracker({ progress }: ProgressTrackerProps) {
  return (
    <section aria-label="Resume generation progress">
      <div>
        <strong>Progress:</strong> {progress.progress_percent}%
      </div>
      {progress.current_stage ? (
        <p>
          <strong>Current stage:</strong> {PIPELINE_STAGE_LABELS[progress.current_stage.stage_name]} -{" "}
          {progress.current_stage.machine_status}
        </p>
      ) : null}
      {progress.error ? <p role="status">{progress.error}</p> : null}
      {progress.latest_event ? <p role="status">{progress.latest_event.human_message}</p> : null}
      <ol>
        {progress.stages.map((stage) => (
          <li key={stage.stage_name}>
            <span>{PIPELINE_STAGE_LABELS[stage.stage_name]}</span>
            <span> - {stage.machine_status}</span>
            {stage.attempt_number ? <span> attempt {stage.attempt_number}</span> : null}
            {stage.failure_type ? <span> ({stage.failure_type})</span> : null}
          </li>
        ))}
      </ol>
      {progress.retry_notices.length > 0 ? (
        <div>
          <strong>Retry notices</strong>
          <ul>
            {progress.retry_notices.map((event) => (
              <li key={event.event_id}>{event.human_message}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {progress.fallback_notices.length > 0 ? (
        <div>
          <strong>Fallback notices</strong>
          <ul>
            {progress.fallback_notices.map((event) => (
              <li key={event.event_id}>{event.human_message}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
