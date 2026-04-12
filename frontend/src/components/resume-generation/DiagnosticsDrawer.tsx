import { useState } from "react";

import type {
  BackendErrorPayload,
  GenerationResultData,
  PipelineProgressState,
  RunMetadata,
} from "../../types/pipeline";
import { formatStageName } from "../../utils/resumeGenerationFormatters";
import { SurfaceCard } from "./WorkflowUI";

export interface DiagnosticsDrawerProps {
  error: BackendErrorPayload;
  run: RunMetadata | null;
  progress: PipelineProgressState | null;
  result: GenerationResultData | null;
}

export function DiagnosticsDrawer({
  error,
  run,
  progress,
  result,
}: DiagnosticsDrawerProps) {
  const [copied, setCopied] = useState(false);
  const compileLog = result?.render_artifacts.find(
    (artifact) => artifact.kind === "compile_log",
  );
  const diagnosticsPayload = {
    run_id: error.run_id ?? run?.run_id ?? result?.run_metadata.run_id,
    phase_name: error.stage_name ?? progress?.current_stage?.stage_name,
    backend_detail: error.message,
    latest_progress_event: progress?.latest_event,
    completed_phases: progress?.completed_stages.map((stage) => stage.stage_name) ?? [],
    verification_failures: result?.verification_warnings ?? [],
    compiler_log_uri: compileLog?.uri,
    diagnostics: result?.diagnostics ?? error.diagnostics,
    raw_error: error,
  };

  async function handleCopyDiagnostics() {
    const text = JSON.stringify(diagnosticsPayload, null, 2);
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <SurfaceCard aria-label="Diagnostics drawer">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <h3 style={{ marginTop: 0 }}>Diagnostics</h3>
        <button className="rg-button" type="button" onClick={() => void handleCopyDiagnostics()}>
          {copied ? "Copied" : "Copy diagnostics"}
        </button>
      </div>

      <div className="rg-meta-grid">
        <DiagnosticField
          label="Run ID"
          value={error.run_id ?? run?.run_id ?? "Not reported"}
        />
        <DiagnosticField
          label="Phase name"
          value={
            error.stage_name
              ? formatStageName(error.stage_name)
              : progress?.current_stage?.stage_name
                ? formatStageName(progress.current_stage.stage_name)
                : "Not reported"
          }
        />
        <DiagnosticField
          label="Backend detail"
          value={error.message}
        />
        <DiagnosticField
          label="Failure type"
          value={error.failure_type ?? "Not reported"}
        />
      </div>

      {compileLog?.uri ? (
        <p style={{ marginTop: 12 }}>
          <strong>Compiler/log details:</strong>{" "}
          <a href={compileLog.uri}>Open compile log</a>
        </p>
      ) : null}

      {(result?.verification_warnings.length ?? 0) > 0 ? (
        <div>
          <strong>Verification failures</strong>
          <ul>
            {result?.verification_warnings.map((warning, index) => (
              <li key={`${warning.message}-${index}`}>
                {warning.message}
                {warning.code ? ` (${warning.code})` : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <details open>
        <summary>Raw diagnostics payload</summary>
        <pre
          style={{
            overflow: "auto",
            padding: 12,
            borderRadius: 10,
            background: "var(--rg-surface-muted)",
          }}
        >
          {JSON.stringify(diagnosticsPayload, null, 2)}
        </pre>
      </details>
    </SurfaceCard>
  );
}

function DiagnosticField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rg-stat">
      <strong>{label}</strong>
      <div>{value}</div>
    </div>
  );
}
