import {
  formatRunStatus,
  formatStageName,
} from "../../utils/resumeGenerationFormatters";
import type { ResumeGenerationState } from "../../types/pipeline";
import { StatusBadge, SurfaceCard } from "./WorkflowUI";

export interface RunStatusBannerProps {
  state: ResumeGenerationState;
  onCancel: () => void;
  onRetry: () => void;
  onReset: () => void;
}

export function RunStatusBanner({
  state,
  onCancel,
  onRetry,
  onReset,
}: RunStatusBannerProps) {
  const tone =
    state.status === "failed"
      ? "danger"
      : state.status === "partial_success" || state.status === "queued"
        ? "warning"
        : state.status === "success"
          ? "success"
          : "default";

  return (
    <SurfaceCard aria-label="Run status" aria-live="polite">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <strong>Status</strong>
          <StatusBadge tone={tone}>{formatRunStatus(state.status)}</StatusBadge>
        </div>
        <span className="rg-sr-only">
          Current run status is {formatRunStatus(state.status)}
        </span>
      </div>
      {state.run?.run_id ? (
        <p>
          <strong>Run ID:</strong> {state.run.run_id}
        </p>
      ) : null}
      {state.current_phase ? (
        <p>
          <strong>Current phase:</strong> {formatStageName(state.current_phase.stage_name)} (
          {state.current_phase.machine_status})
        </p>
      ) : null}
      <div className="rg-actions">
        <button
          className="rg-button rg-button-danger"
          type="button"
          onClick={onCancel}
          disabled={!["submitting", "queued", "phase_running", "phase_completed"].includes(state.status)}
        >
          Cancel client request
        </button>
        <button
          className="rg-button"
          type="button"
          onClick={onRetry}
          disabled={
            state.retrying ||
            state.submitted_request === null ||
            ["submitting", "queued", "phase_running", "phase_completed"].includes(state.status)
          }
        >
          {state.retrying ? "Retrying..." : "Retry run"}
        </button>
        <button className="rg-button rg-button-ghost" type="button" onClick={onReset}>
          Reset
        </button>
      </div>
    </SurfaceCard>
  );
}
