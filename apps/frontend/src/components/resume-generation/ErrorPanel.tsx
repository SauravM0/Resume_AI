import { useMemo, useState } from "react";

import type {
  BackendErrorPayload,
  GenerationResultData,
  PipelineProgressState,
  RunMetadata,
} from "../../types/pipeline";
import { buildErrorDisplayModel } from "../../utils/errorMapping";
import { formatStageName } from "../../utils/resumeGenerationFormatters";
import { DiagnosticsDrawer } from "./DiagnosticsDrawer";
import { StatusBadge, SurfaceCard } from "./WorkflowUI";

export interface ErrorPanelProps {
  error: BackendErrorPayload;
  run: RunMetadata | null;
  progress: PipelineProgressState | null;
  result: GenerationResultData | null;
  onRetry?: () => void;
  onStartNewRun: () => void;
  onReturnToEditor: () => void;
  debug?: boolean;
}

export function ErrorPanel({
  error,
  run,
  progress,
  result,
  onRetry,
  onStartNewRun,
  onReturnToEditor,
  debug = false,
}: ErrorPanelProps) {
  const [detailsVisible, setDetailsVisible] = useState(debug);
  const display = buildErrorDisplayModel(error);
  const completedPhaseCount = progress?.completed_stages.length ?? 0;
  const failedPhaseLabel = useMemo(() => {
    if (display.phase_label) {
      return display.phase_label;
    }
    if (error.stage_name) {
      return formatStageName(error.stage_name);
    }
    return "Not reported";
  }, [display.phase_label, error.stage_name]);

  return (
    <section aria-label="Generation failure" role="alert" style={{ display: "grid", gap: 16 }}>
      <SurfaceCard tone="danger">
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <StatusBadge tone="danger">{display.title}</StatusBadge>
          <StatusBadge tone="muted">Failed phase: {failedPhaseLabel}</StatusBadge>
          {completedPhaseCount > 0 ? (
            <StatusBadge tone="muted">
              {completedPhaseCount} completed phase{completedPhaseCount === 1 ? "" : "s"} preserved
            </StatusBadge>
          ) : null}
        </div>
        <h2 style={{ marginBottom: 8 }}>Run failure</h2>
        <p style={{ marginTop: 0 }}>{display.explanation}</p>
        <p>
          <strong>Failure type:</strong> {error.failure_type ?? "Not reported"}
        </p>
        <p>
          <strong>Backend detail:</strong> {error.message}
        </p>
        {error.transport_detail ? (
          <p>
            <strong>Transport detail:</strong> {error.transport_detail}
          </p>
        ) : null}
        <p>
          <strong>Suggested next step:</strong> {error.suggested_next_step ?? display.retry_recommendation}
        </p>
        {error.run_id || run?.run_id ? (
          <p>
            <strong>Run ID:</strong> {error.run_id ?? run?.run_id}
          </p>
        ) : null}

        <div className="rg-actions">
          {onRetry ? (
            <button className="rg-button" type="button" onClick={onRetry}>
              Retry run
            </button>
          ) : null}
          <button className="rg-button" type="button" onClick={onReturnToEditor}>
            Edit JD
          </button>
          <button
            className="rg-button"
            type="button"
            onClick={() => setDetailsVisible((current) => !current)}
            aria-expanded={detailsVisible}
          >
            {detailsVisible ? "Hide details" : "Show details"}
          </button>
          <button className="rg-button rg-button-ghost" type="button" onClick={onStartNewRun}>
            Start new run
          </button>
        </div>

        {(error.retryable !== undefined || error.fallback_eligible !== undefined) ? (
          <div
            style={{
              display: "flex",
              gap: 12,
              flexWrap: "wrap",
              marginTop: 12,
              color: "var(--rg-text-subtle)",
            }}
          >
            {error.retryable !== undefined ? (
              <span>Retryable: {String(error.retryable)}</span>
            ) : null}
            {error.fallback_eligible !== undefined ? (
              <span>Fallback eligible: {String(error.fallback_eligible)}</span>
            ) : null}
          </div>
        ) : null}
      </SurfaceCard>

      {detailsVisible ? (
        <DiagnosticsDrawer
          error={error}
          run={run}
          progress={progress}
          result={result}
        />
      ) : null}

      {completedPhaseCount > 0 ? (
        <p>
          <strong>Progress history has been preserved.</strong> Earlier successful phases remain visible in the progress tracker for investigation.
        </p>
      ) : null}
    </section>
  );
}
