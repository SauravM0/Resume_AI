import {
  DEFAULT_SOURCE_PROFILE_PATH,
  DEFAULT_TEMPLATE_ID,
} from "../../constants/resumeGeneration";
import { useResumeGeneration } from "../../hooks/useResumeGeneration";
import { useSystemReadiness } from "../../hooks/useSystemReadiness";
import type { GenerateResumeRequest } from "../../types/pipeline";
import { DebugPanel } from "./DebugPanel";
import { GenerationFailure } from "./GenerationFailure";
import { GenerationResult } from "./GenerationResult";
import { JobDescriptionForm } from "./JobDescriptionForm";
import { ProgressTracker } from "./ProgressTracker";
import { ReadinessPanel } from "./ReadinessPanel";
import { RunStatusBanner } from "./RunStatusBanner";
import { EmptyState, SurfaceCard, WorkflowGlobalStyles } from "./WorkflowUI";

export interface ResumeGenerationPanelProps {
  baseUrl?: string;
}

export function ResumeGenerationPanel({ baseUrl }: ResumeGenerationPanelProps) {
  const { state, submit, retry, cancel, reset, toggleDebug } = useResumeGeneration({ baseUrl });
  const { backendHealth, readiness, refresh } = useSystemReadiness({
    baseUrl,
    sourceProfilePath: DEFAULT_SOURCE_PROFILE_PATH,
    templateId: DEFAULT_TEMPLATE_ID,
  });

  async function handleSubmit(request: GenerateResumeRequest) {
    try {
      await submit(request);
    } catch {
      // State is already updated in the hook.
    }
  }

  async function handleRetry() {
    try {
      await retry();
    } catch {
      // State is already updated in the hook.
    }
  }

  function handleReturnToEditor() {
    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  }

  const runActive = ["submitting", "queued", "phase_running", "phase_completed"].includes(state.status);
  const submitState =
    backendHealth.status === "unavailable"
      ? "backend_unavailable"
      : state.status === "submitting"
          ? "submitting"
        : runActive
          ? "run_active"
          : "ready";

  return (
    <main
      className="resume-workflow"
      style={{
        maxWidth: 1120,
        margin: "0 auto",
        padding: "24px 16px 56px",
        display: "grid",
        gap: 24,
        background: "var(--rg-background)",
      }}
    >
      <WorkflowGlobalStyles />

      <header className="rg-section-header" style={{ paddingTop: 4 }}>
        <h1 style={{ margin: 0 }}>Resume Generation</h1>
        <p className="rg-muted" style={{ margin: 0, maxWidth: 760 }}>
          Paste a target job description, confirm readiness, adjust output settings if needed, and start a real generation run.
          This screen is built to show operational behavior clearly, including validation, progress, warnings, and failures.
        </p>
      </header>

      <ReadinessPanel backendHealth={backendHealth} readiness={readiness} onRefresh={refresh} />

      <JobDescriptionForm
        disabled={runActive || backendHealth.status === "unavailable"}
        submitState={submitState}
        validationErrors={state.validation_errors}
        debugVisible={state.debug_visible}
        onDebugToggle={toggleDebug}
        onSubmit={handleSubmit}
      />

      {state.status !== "idle" ? (
        <RunStatusBanner state={state} onCancel={cancel} onRetry={handleRetry} onReset={reset} />
      ) : (
        <SurfaceCard aria-label="Run workspace overview" tone="muted">
          <EmptyState
            title="No run started yet"
            description="Paste a job description above, confirm readiness, and start a run. Progress, results, warnings, and diagnostics will stay on this page so you can inspect the full workflow."
          />
        </SurfaceCard>
      )}

      {state.progress ? (
        <ProgressTracker
          progress={state.progress}
          run={state.run}
          overallStatus={state.status}
          debug={state.debug_visible}
        />
      ) : runActive ? (
        <SurfaceCard aria-live="polite" aria-busy="true" aria-label="Run preparation" tone="muted">
          <div className="rg-section-header">
            <h2 style={{ marginBottom: 0 }}>Preparing run view</h2>
            <p className="rg-muted" style={{ marginBottom: 0 }}>
              The request has been accepted. Waiting for the backend to return the first structured progress update.
            </p>
          </div>
          <div style={{ display: "grid", gap: 12 }}>
            <div className="rg-skeleton" style={{ width: "40%", height: 22 }} />
            <div className="rg-skeleton" style={{ width: "100%", height: 18 }} />
            <div className="rg-skeleton" style={{ width: "88%", height: 18 }} />
            <div className="rg-skeleton" style={{ width: "92%", height: 64 }} />
          </div>
        </SurfaceCard>
      ) : null}
      {state.view === "error" && state.error ? (
        <GenerationFailure
          error={state.error}
          run={state.run}
          progress={state.progress}
          result={state.result}
          onRetry={handleRetry}
          onStartNewRun={reset}
          onReturnToEditor={handleReturnToEditor}
          debug={state.debug_visible}
        />
      ) : null}
      {state.view === "result" && state.result ? (
        <GenerationResult
          result={state.result}
          onStartNewRun={reset}
          debug={state.debug_visible}
        />
      ) : null}

      {state.view !== "result" && state.view !== "error" && !runActive ? (
        <SurfaceCard tone="muted" aria-label="Results placeholder">
          <EmptyState
            title="No result available yet"
            description="Completed outputs, selection summaries, and run quality signals will appear here after a generation run finishes."
          />
        </SurfaceCard>
      ) : null}

      <DebugPanel state={state} />
    </main>
  );
}
