import {
  DebugPanel,
  EmptyState,
  GenerationFailure,
  GenerationResult,
  JobDescriptionForm,
  ProgressTracker,
  ResumeGenerationErrorBoundary,
  RunStatusBanner,
  SurfaceCard,
  SystemReadinessCard,
  ResumeOptionsPanel,
  WorkflowGlobalStyles,
} from "../components/resume-generation";
import {
  DEFAULT_SOURCE_PROFILE_PATH,
  DEFAULT_TEMPLATE_ID,
} from "../constants/resumeGeneration";
import { useResumeGeneration } from "../hooks/useResumeGeneration";
import { useSystemReadiness } from "../hooks/useSystemReadiness";
import type { GenerateResumeRequest, ResumeSettings } from "../types/pipeline";
import { useState } from "react";

export function ResumeGenerationPage() {
  return (
    <ResumeGenerationErrorBoundary>
      <ResumeGenerationWorkspace />
    </ResumeGenerationErrorBoundary>
  );
}

function ResumeGenerationWorkspace() {
  const { state, submit, retry, cancel, reset, toggleDebug } =
    useResumeGeneration();
  const [jobDescriptionText, setJobDescriptionText] = useState("");
  const [jobPostingUrl, setJobPostingUrl] = useState("");
  const [settings, setSettings] = useState<ResumeSettings>({
    page_length_pages: 1,
    template_id: DEFAULT_TEMPLATE_ID,
    debug_mode: false,
    strict_mode: false,
    show_detailed_diagnostics_after_run: false,
  });

  const { backendHealth, readiness, refresh } = useSystemReadiness({
    sourceProfilePath: DEFAULT_SOURCE_PROFILE_PATH,
    templateId: settings.template_id,
  });

  async function handleSubmit(request: GenerateResumeRequest) {
    try {
      await submit(request);
    } catch {
      // State is already updated by the orchestration hook.
    }
  }

  async function handleRetry() {
    try {
      await retry();
    } catch {
      // State is already updated by the orchestration hook.
    }
  }

  function handleReturnToEditor() {
    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  }

  function handleSettingsChange(nextSettings: ResumeSettings) {
    setSettings(nextSettings);
    toggleDebug(
      nextSettings.debug_mode ||
        nextSettings.show_detailed_diagnostics_after_run,
    );
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
        maxWidth: 1180,
        margin: "0 auto",
        padding: "clamp(20px, 3vw, 32px) 16px 56px",
        display: "grid",
        gap: 24,
        background: "var(--rg-background)",
      }}
    >
      <WorkflowGlobalStyles />

      <header className="rg-section-header" style={{ paddingTop: 4 }}>
        <h1 style={{ marginBottom: 0 }}>Resume Generation</h1>
        <p className="rg-muted" style={{ marginBottom: 0, maxWidth: 760 }}>
          Paste a target job description, confirm system readiness, choose simple output options, and start a run. Progress, failures, and completed outputs stay on this screen so the workflow remains inspectable.
        </p>
      </header>

      <section
        aria-label="Workflow setup"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: 24,
          alignItems: "start",
        }}
      >
        <div style={{ display: "grid", gap: 20 }}>
          <SystemReadinessCard
            backendHealth={backendHealth}
            readiness={readiness}
            onRefresh={refresh}
          />
          <JobDescriptionForm
            value={jobDescriptionText}
            onValueChange={setJobDescriptionText}
            jobPostingUrl={jobPostingUrl}
            onJobPostingUrlChange={setJobPostingUrl}
            sourceProfilePath={DEFAULT_SOURCE_PROFILE_PATH}
            settings={settings}
            onSettingsChange={handleSettingsChange}
            hideAdvancedSettings
            disabled={runActive || backendHealth.status === "unavailable"}
            submitState={submitState}
            validationErrors={state.validation_errors}
            debugVisible={state.debug_visible}
            onDebugToggle={toggleDebug}
            onSubmit={handleSubmit}
          />
        </div>

        <div style={{ display: "grid", gap: 20, alignContent: "start" }}>
          <ResumeOptionsPanel
            disabled={runActive}
            settings={settings}
            onChange={handleSettingsChange}
          />
          <SurfaceCard tone="muted" aria-label="Run guidance">
            <div className="rg-section-header">
              <h2 style={{ marginBottom: 0 }}>Before you run</h2>
              <p className="rg-muted" style={{ marginBottom: 0 }}>
                Paste the posting text first. Invalid or incomplete input stays visible and blocks submission until fixed.
              </p>
            </div>
            <ul style={{ marginBottom: 0, paddingLeft: 18 }}>
              <li>Use the job posting text itself, not a summary.</li>
              <li>Keep 1 page selected unless the role needs broader coverage.</li>
              <li>Enable debug mode only when you want raw operational detail.</li>
            </ul>
          </SurfaceCard>
        </div>
      </section>

      <section aria-label="Run output" style={{ display: "grid", gap: 20 }}>
        {state.status !== "idle" ? (
          <RunStatusBanner
            state={state}
            onCancel={cancel}
            onRetry={handleRetry}
            onReset={reset}
          />
        ) : (
          <SurfaceCard aria-label="Run workspace overview" tone="muted">
            <EmptyState
              title="No run started yet"
              description="Paste a job description above and start a generation run. Progress, results, and errors will appear below in one place."
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
          <SurfaceCard
            aria-live="polite"
            aria-busy="true"
            aria-label="Run preparation"
            tone="muted"
          >
            <div className="rg-section-header">
              <h2 style={{ marginBottom: 0 }}>Preparing run view</h2>
              <p className="rg-muted" style={{ marginBottom: 0 }}>
                The request has been accepted. Waiting for the first structured progress update from the backend.
              </p>
            </div>
            <div style={{ display: "grid", gap: 12 }}>
              <div className="rg-skeleton" style={{ width: "42%", height: 22 }} />
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
              description="Completed outputs, selection summaries, warnings, and diagnostics will appear here after the run finishes."
            />
          </SurfaceCard>
        ) : null}
      </section>

      <DebugPanel state={state} />
    </main>
  );
}
