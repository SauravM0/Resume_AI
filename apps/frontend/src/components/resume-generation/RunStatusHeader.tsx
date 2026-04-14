import type { RunProgressOverview } from "../../types/pipeline";
import { formatRunStatus } from "../../utils/resumeGenerationFormatters";
import {
  formatElapsedDuration,
  formatTimestamp,
} from "../../utils/timingFormatters";
import { StatusBadge, SurfaceCard } from "./WorkflowUI";

export interface RunStatusHeaderProps {
  overview: RunProgressOverview;
}

export function RunStatusHeader({ overview }: RunStatusHeaderProps) {
  const healthTone =
    overview.run_health === "healthy"
      ? "success"
      : overview.run_health === "warning"
        ? "warning"
        : "danger";

  return (
    <SurfaceCard aria-label="Run progress header">
      <div className="rg-meta-grid">
        <div className="rg-stat">
          <strong>Run ID</strong>
          <div>{overview.run_id}</div>
        </div>
        <div className="rg-stat">
          <strong>Overall status</strong>
          <div>{formatRunStatus(overview.overall_status)}</div>
        </div>
        <div className="rg-stat">
          <strong>Started</strong>
          <div>{formatTimestamp(overview.started_at)}</div>
        </div>
        <div className="rg-stat">
          <strong>Elapsed</strong>
          <div>{formatElapsedDuration(overview.elapsed_seconds)}</div>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          alignItems: "center",
          marginTop: 14,
        }}
      >
        <StatusBadge tone={healthTone}>{overview.run_health_text}</StatusBadge>
        <span className="rg-muted">Transport: {overview.connection.transport}</span>
        <span className="rg-muted">Connected: {String(overview.connection.connected)}</span>
        {overview.queued ? <span className="rg-muted">Waiting for execution to begin</span> : null}
        {overview.retry_in_progress ? <span className="rg-muted">Retry in progress</span> : null}
        {overview.partial_recovery ? <span className="rg-muted">Fallback applied</span> : null}
        {overview.hard_failure ? <span className="rg-muted">Hard failure recorded</span> : null}
      </div>

      {overview.current_backend_message ? (
        <p style={{ margin: "14px 0 0" }}>
          <strong>Backend detail:</strong> {overview.current_backend_message}
        </p>
      ) : null}

      {overview.timeout_warning ? (
        <p style={{ margin: "12px 0 0", color: "var(--rg-warning-text)" }}>
          <strong>Timeout warning:</strong> {overview.timeout_warning}
        </p>
      ) : null}

      {overview.connection.last_error ? (
        <p style={{ margin: "12px 0 0", color: "var(--rg-warning-text)" }}>
          <strong>Progress transport:</strong> {overview.connection.last_error}
        </p>
      ) : null}
    </SurfaceCard>
  );
}
