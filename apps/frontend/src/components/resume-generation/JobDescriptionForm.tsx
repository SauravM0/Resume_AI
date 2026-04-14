import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import {
  DEFAULT_SOURCE_PROFILE_PATH,
  DEFAULT_TEMPLATE_ID,
} from "../../constants/resumeGeneration";
import type {
  GenerateResumeRequest,
  ResumeSettings,
} from "../../types/pipeline";
import {
  JOB_DESCRIPTION_MAX_LENGTH,
  JOB_DESCRIPTION_MIN_LENGTH,
  validateJobDescription,
} from "../../utils/jobDescriptionValidation";
import { ResumeOptionsPanel } from "./ResumeOptionsPanel";

export interface JobDescriptionFormProps {
  value?: string;
  onValueChange?: (value: string) => void;
  jobPostingUrl?: string;
  onJobPostingUrlChange?: (value: string) => void;
  sourceProfilePath?: string;
  settings?: ResumeSettings;
  onSettingsChange?: (settings: ResumeSettings) => void;
  hideAdvancedSettings?: boolean;
  disabled?: boolean;
  submitState?: "ready" | "submitting" | "run_active" | "backend_unavailable";
  validationErrors?: string[];
  debugVisible: boolean;
  onDebugToggle: (visible?: boolean) => void;
  onSubmit: (request: GenerateResumeRequest) => void;
}

export function JobDescriptionForm({
  value,
  onValueChange,
  jobPostingUrl,
  onJobPostingUrlChange,
  sourceProfilePath,
  settings: controlledSettings,
  onSettingsChange,
  hideAdvancedSettings = false,
  disabled = false,
  submitState = "ready",
  validationErrors = [],
  debugVisible,
  onDebugToggle,
  onSubmit,
}: JobDescriptionFormProps) {
  const [internalJobDescriptionText, setInternalJobDescriptionText] = useState("");
  const [internalJobPostingUrl, setInternalJobPostingUrl] = useState("");
  const [settingsExpanded, setSettingsExpanded] = useState(false);
  const [internalSettings, setInternalSettings] = useState<ResumeSettings>({
    page_length_pages: 1,
    template_id: DEFAULT_TEMPLATE_ID,
    debug_mode: debugVisible,
    strict_mode: false,
    show_detailed_diagnostics_after_run: false,
  });

  const jobDescriptionText = value ?? internalJobDescriptionText;
  const currentJobPostingUrl = jobPostingUrl ?? internalJobPostingUrl;
  const resolvedSourceProfilePath = sourceProfilePath ?? DEFAULT_SOURCE_PROFILE_PATH;
  const settings = controlledSettings ?? internalSettings;

  const validation = validateJobDescription(jobDescriptionText);
  const allValidationErrors = [...validation.errors, ...validationErrors];
  const characterCount = jobDescriptionText.length;
  const validationMessageId = "job-description-validation";
  const descriptionHelpId = "job-description-help";
  const submitReadinessText = validation.isValid ? "Ready to start a run." : "Fix the inline issues before starting.";
  const submitLabel =
    submitState === "submitting"
      ? "Submitting run..."
      : submitState === "run_active"
        ? "Run in progress"
        : submitState === "backend_unavailable"
          ? "Backend unavailable"
          : "Start generation";
  const primaryValidationError = allValidationErrors[0];
  const lengthGuidance = useMemo(() => {
    if (characterCount === 0) {
      return "Paste the target job description to begin.";
    }
    if (characterCount < JOB_DESCRIPTION_MIN_LENGTH) {
      return `Add more detail. Aim for at least ${JOB_DESCRIPTION_MIN_LENGTH} characters.`;
    }
    if (characterCount > JOB_DESCRIPTION_MAX_LENGTH) {
      return `Trim the posting below ${JOB_DESCRIPTION_MAX_LENGTH.toLocaleString()} characters.`;
    }
    return "Input length is within range.";
  }, [characterCount]);

  useEffect(() => {
    setInternalSettings((current) => ({
      ...current,
      debug_mode: debugVisible,
    }));
  }, [debugVisible]);

  function updateJobDescription(nextValue: string) {
    onValueChange?.(nextValue);
    if (value === undefined) {
      setInternalJobDescriptionText(nextValue);
    }
  }

  function updateJobPostingUrl(nextValue: string) {
    onJobPostingUrlChange?.(nextValue);
    if (jobPostingUrl === undefined) {
      setInternalJobPostingUrl(nextValue);
    }
  }

  function updateSettings(nextSettings: ResumeSettings) {
    onSettingsChange?.(nextSettings);
    if (controlledSettings === undefined) {
      setInternalSettings(nextSettings);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!validation.isValid) {
      return;
    }

    onDebugToggle(settings.debug_mode || settings.show_detailed_diagnostics_after_run);
    onSubmit({
      job_description_text: jobDescriptionText.trim(),
      job_posting_url: currentJobPostingUrl.trim() || undefined,
      source_profile_path: resolvedSourceProfilePath.trim() || undefined,
      template_id: settings.template_id.trim() || undefined,
      persist_intermediate_artifacts: settings.debug_mode || settings.show_detailed_diagnostics_after_run,
      frontend_correlation_id:
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? `frontend.${crypto.randomUUID()}`
          : undefined,
      generation_preferences: {
        page_length_pages: settings.page_length_pages,
        strict_mode: settings.strict_mode,
        show_detailed_diagnostics_after_run: settings.show_detailed_diagnostics_after_run,
      },
    });
  }

  return (
    <section
      aria-label="Resume generation input"
      className="rg-card"
      style={{
        border: "1px solid var(--rg-border)",
        borderRadius: 16,
        background: "var(--rg-surface)",
        padding: 20,
      }}
    >
      <form onSubmit={handleSubmit}>
        <div style={{ display: "grid", gap: 20 }}>
          <div className="rg-section-header">
            <h2 style={{ marginBottom: 0 }}>Job description</h2>
            <p className="rg-muted" style={{ marginBottom: 0 }}>
              Paste the target posting text you want the system to optimize against. Use the full role description rather than a summary so evidence selection and phrasing stay grounded in the actual requirements.
            </p>
          </div>

          <div>
            <label htmlFor="job-description" style={{ display: "block", fontWeight: 600, marginBottom: 8 }}>
              Paste the job description
            </label>
            <p id={descriptionHelpId} className="rg-muted" style={{ margin: "0 0 10px" }}>
              Include responsibilities, required qualifications, preferred skills, work model, and domain context. Plain pasted text is best.
            </p>
            <textarea
              className="rg-textarea"
              id="job-description"
              required
              rows={16}
              value={jobDescriptionText}
              onChange={(event) => updateJobDescription(event.currentTarget.value)}
              disabled={disabled}
              aria-invalid={allValidationErrors.length > 0}
              aria-describedby={`${descriptionHelpId} ${validationMessageId}`}
              placeholder={
                "Paste the full job description here.\n\nExample content to include:\n• responsibilities and outcomes\n• required and preferred qualifications\n• technical stack and tools\n• seniority expectations\n• work model or domain context"
              }
              style={{
                minHeight: 320,
                lineHeight: 1.5,
                resize: "vertical",
              }}
            />
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 12,
                flexWrap: "wrap",
                marginTop: 8,
                color: "var(--rg-text-subtle)",
              }}
            >
              <span>Paste-friendly input. Rich formatting is not required.</span>
              <span>
                {characterCount.toLocaleString()} characters
              </span>
            </div>
            <p
              aria-live="polite"
              style={{
                margin: "8px 0 0",
                color:
                  characterCount === 0 || characterCount < JOB_DESCRIPTION_MIN_LENGTH || characterCount > JOB_DESCRIPTION_MAX_LENGTH
                    ? "var(--rg-danger-text)"
                    : "var(--rg-text-subtle)",
              }}
            >
              {lengthGuidance}
            </p>
            {characterCount === 0 ? (
              <div className="rg-empty-state" style={{ marginTop: 12, padding: 14 }}>
                <strong>What to paste here</strong>
                <p className="rg-muted" style={{ margin: "6px 0 0" }}>
                  Use the target job posting text itself, not a summary. The quality of analysis and evidence selection depends on the exact wording.
                </p>
              </div>
            ) : null}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
            <label>
              <span style={{ fontWeight: 600 }}>Job posting URL</span>
              <input
                className="rg-input"
                type="url"
                value={currentJobPostingUrl}
                onChange={(event) => updateJobPostingUrl(event.currentTarget.value)}
                disabled={disabled}
                placeholder="https://example.com/job"
                style={{ marginTop: 6 }}
              />
              <span className="rg-muted" style={{ display: "block", marginTop: 6 }}>
                Optional. Helpful for traceability only; the pasted text remains the primary input.
              </span>
            </label>

            <label>
              <span style={{ fontWeight: 600 }}>Source profile path</span>
              <input
                className="rg-input"
                type="text"
                value={resolvedSourceProfilePath}
                readOnly
                disabled={disabled}
                placeholder={DEFAULT_SOURCE_PROFILE_PATH}
                style={{ marginTop: 6 }}
              />
              <span className="rg-muted" style={{ display: "block", marginTop: 6 }}>
                The current workflow uses the configured master profile path for evidence selection. This is surfaced here for transparency.
              </span>
            </label>
          </div>

          {!hideAdvancedSettings ? (
            <>
              <div>
                <button
                  className="rg-button"
                  type="button"
                  onClick={() => setSettingsExpanded((current) => !current)}
                  aria-expanded={settingsExpanded}
                  aria-controls="resume-settings-panel"
                  disabled={disabled}
                >
                  {settingsExpanded ? "Hide advanced settings" : "Show advanced settings"}
                </button>
                <p className="rg-muted" style={{ margin: "8px 0 0" }}>
                  Advanced settings are optional. Use them when you need a different page length, template, or deeper diagnostics.
                </p>
              </div>

              {settingsExpanded ? (
                <div
                  id="resume-settings-panel"
                  style={{
                    borderTop: "1px solid var(--rg-border)",
                    paddingTop: 20,
                  }}
                >
                  <ResumeOptionsPanel
                    disabled={disabled}
                    settings={settings}
                    onChange={(nextSettings) => {
                      updateSettings(nextSettings);
                      onDebugToggle(nextSettings.debug_mode);
                    }}
                    defaultExpanded
                    showHeader={false}
                  />
                </div>
              ) : null}
            </>
          ) : null}

          {allValidationErrors.length > 0 ? (
            <div
              id={validationMessageId}
              role="alert"
              aria-label="Validation errors"
              style={{
                padding: 14,
                borderRadius: 12,
                border: "1px solid var(--rg-danger-border)",
                background: "var(--rg-danger-surface)",
              }}
            >
              <strong>Input issues</strong>
              <ul style={{ marginBottom: 0 }}>
                {allValidationErrors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            </div>
          ) : (
            <div
              id={validationMessageId}
              aria-live="polite"
              aria-label="Validation summary"
              style={{
                padding: 14,
                borderRadius: 12,
                border: "1px solid var(--rg-border)",
                background: "var(--rg-surface-muted)",
                color: "var(--rg-text)",
              }}
            >
              The system will parse this posting, select matching evidence from the master profile, generate a tailored resume, verify it, and return run outputs below.
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
            <div className="rg-muted" aria-live="polite">
              <strong>Submit readiness:</strong> {primaryValidationError ?? submitReadinessText}
            </div>
            <button className="rg-button rg-button-primary" type="submit" disabled={disabled || !validation.isValid} aria-disabled={disabled || !validation.isValid}>
              {submitLabel}
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}
