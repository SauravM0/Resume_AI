import type { ProgressPhaseViewModel } from "../../types/pipeline";
import {
  formatElapsedDuration,
  formatTimestamp,
} from "../../utils/timingFormatters";
import { formatStageName } from "../../utils/resumeGenerationFormatters";
import { StatusBadge, SurfaceCard } from "./WorkflowUI";

export interface PhaseProgressItemProps {
  phase: ProgressPhaseViewModel;
  debug?: boolean;
  isCurrent?: boolean;
}

function getTone(status: ProgressPhaseViewModel["status"]) {
  if (status === "completed") {
    return "success";
  }
  if (status === "warning" || status === "retrying") {
    return "warning";
  }
  if (status === "failed") {
    return "danger";
  }
  if (status === "pending" || status === "skipped") {
    return "muted";
  }
  return "default";
}

export function PhaseProgressItem({
  phase,
  debug = false,
  isCurrent = false,
}: PhaseProgressItemProps) {
  const tone = getTone(phase.status);

  return (
    <li style={{ listStyle: "none" }}>
      <SurfaceCard
        aria-label={`${phase.label} ${phase.status}`}
        tone={isCurrent ? "default" : undefined}
        style={isCurrent ? { borderColor: "#153a63", boxShadow: "0 0 0 1px rgba(21, 58, 99, 0.16)" } : undefined}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "grid", gap: 6 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <StatusBadge tone={tone}>{phase.status}</StatusBadge>
              {isCurrent ? <StatusBadge tone="default">Current phase</StatusBadge> : null}
            </div>
            <h3 style={{ margin: 0, fontSize: "1rem" }}>{phase.label}</h3>
          </div>
          <div style={{ textAlign: "right", color: "var(--rg-text-subtle)" }}>
            <div>{formatTimestamp(phase.updated_at)}</div>
            <div>{formatElapsedDuration(phase.elapsed_seconds)}</div>
          </div>
        </div>

        <p style={{ margin: "10px 0 0" }}>{phase.description}</p>
        {phase.detail_text ? (
          <p style={{ margin: "8px 0 0", color: "var(--rg-text-subtle)" }}>
            {phase.detail_text}
          </p>
        ) : null}

        <div
          style={{
            display: "flex",
            gap: 12,
            flexWrap: "wrap",
            marginTop: 10,
            color: "var(--rg-text-subtle)",
          }}
        >
          {phase.fallback_used ? <span>Fallback or repair used</span> : null}
          {phase.retry_in_progress ? <span>Retrying</span> : null}
          {phase.warning_text ? <span>{phase.warning_text}</span> : null}
        </div>

        {debug && phase.backend_stages.length > 0 ? (
          <details style={{ marginTop: 14 }}>
            <summary>Debug detail</summary>
            <ul style={{ display: "grid", gap: 10, marginBottom: 0, paddingLeft: 18 }}>
              {phase.backend_stages.map((stage) => (
                <li key={`${phase.key}-${stage.stage_name}-${stage.updated_at}`}>
                  <strong>{formatStageName(stage.stage_name)}</strong>
                  <div>Raw message: {stage.human_message || "Not provided"}</div>
                  <div>Timestamp: {formatTimestamp(stage.updated_at)}</div>
                  <div>Retry count: {Math.max(0, (stage.attempt_number ?? 1) - 1)}</div>
                  <div>Machine status: {stage.machine_status}</div>
                  {stage.failure_type ? <div>Warning / failure detail: {stage.failure_type}</div> : null}
                  {stage.progress_percent !== undefined ? <div>Progress: {stage.progress_percent}%</div> : null}
                  {stage.fallback_metadata?.strategy ? <div>Fallback strategy: {stage.fallback_metadata.strategy}</div> : null}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </SurfaceCard>
    </li>
  );
}
