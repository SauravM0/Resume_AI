import type {
  BackendHealthState,
  ReadinessIndicator,
} from "../../types/pipeline";
import { StatusBadge, SurfaceCard } from "./WorkflowUI";

export interface SystemReadinessCardProps {
  backendHealth: BackendHealthState;
  readiness: ReadinessIndicator[];
  onRefresh: () => void;
}

export function SystemReadinessCard({
  backendHealth,
  readiness,
  onRefresh,
}: SystemReadinessCardProps) {
  const backendTone =
    backendHealth.status === "healthy"
      ? "success"
      : backendHealth.status === "degraded"
        ? "warning"
        : backendHealth.status === "unavailable"
          ? "danger"
          : "muted";

  return (
    <SurfaceCard aria-label="System readiness" tone="muted">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 16,
          alignItems: "flex-start",
          flexWrap: "wrap",
        }}
      >
        <div className="rg-section-header">
          <h2 style={{ marginBottom: 0 }}>System readiness</h2>
          <p className="rg-muted" style={{ marginBottom: 0 }}>
            Confirm backend reachability and core workflow inputs before starting a run.
          </p>
        </div>
        <button type="button" className="rg-button" onClick={onRefresh}>
          Refresh status
        </button>
      </div>

      <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
        <div
          style={{
            display: "grid",
            gap: 8,
            padding: 14,
            borderRadius: 12,
            border: "1px solid var(--rg-border)",
            background: "var(--rg-surface)",
          }}
        >
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <strong>Backend</strong>
            <StatusBadge tone={backendTone}>{backendHealth.status}</StatusBadge>
          </div>
          <div>{backendHealth.summary}</div>
          {backendHealth.detail ? (
            <div className="rg-muted">{backendHealth.detail}</div>
          ) : null}
        </div>

        {readiness
          .filter((item) => item.key !== "backend")
          .map((item) => (
            <div
              key={item.key}
              style={{
                display: "grid",
                gap: 8,
                padding: 14,
                borderRadius: 12,
                border: "1px solid var(--rg-border)",
                background: "var(--rg-surface)",
              }}
            >
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <strong>{item.label}</strong>
                <StatusBadge
                  tone={
                    item.state === "ready"
                      ? "success"
                      : item.state === "warning"
                        ? "warning"
                        : item.state === "unavailable"
                          ? "danger"
                          : "muted"
                  }
                >
                  {item.state}
                </StatusBadge>
              </div>
              <div>{item.summary}</div>
              {item.detail ? <div className="rg-muted">{item.detail}</div> : null}
            </div>
          ))}
      </div>
    </SurfaceCard>
  );
}
