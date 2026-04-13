import type {
  BackendHealthState,
  ReadinessIndicator,
} from "../../types/pipeline";
import { StatusBadge, SurfaceCard } from "./WorkflowUI";

export interface ReadinessPanelProps {
  backendHealth: BackendHealthState;
  readiness: ReadinessIndicator[];
  onRefresh: () => void;
}

export function ReadinessPanel({
  backendHealth,
  readiness,
  onRefresh,
}: ReadinessPanelProps) {
  const backendTone =
    backendHealth.status === "healthy"
      ? "success"
      : backendHealth.status === "degraded"
        ? "warning"
        : backendHealth.status === "unavailable"
          ? "danger"
          : "muted";

  return (
    <section aria-label="System readiness">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div className="rg-section-header">
          <h2 style={{ margin: 0 }}>System readiness</h2>
          <p className="rg-muted" style={{ margin: "8px 0 0" }}>
            Check backend reachability plus configured profile and template inputs before you start a run.
          </p>
        </div>
        <button type="button" className="rg-button" onClick={onRefresh}>
          Refresh health check
        </button>
      </div>

      <SurfaceCard tone="muted" style={{ marginTop: 16 }} aria-live="polite">
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <strong>Backend status:</strong>{" "}
          <StatusBadge tone={backendTone}>{backendHealth.status}</StatusBadge>
        </div>
        <p style={{ marginBottom: 0 }}>{backendHealth.summary}</p>
        {backendHealth.detail ? (
          <p className="rg-muted" style={{ marginBottom: 0 }}>{backendHealth.detail}</p>
        ) : null}
        {backendHealth.checked_at ? (
          <p className="rg-muted" style={{ marginBottom: 0 }}>
            Last checked: {new Date(backendHealth.checked_at).toLocaleString()}
          </p>
        ) : null}
      </SurfaceCard>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 12,
          marginTop: 16,
        }}
      >
        {readiness.map((item) => (
          <SurfaceCard key={item.key} aria-label={item.label}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
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
            <p style={{ marginBottom: 0 }}>{item.summary}</p>
            {item.detail ? (
              <p className="rg-muted" style={{ marginBottom: 0 }}>{item.detail}</p>
            ) : null}
          </SurfaceCard>
        ))}
      </div>
    </section>
  );
}
