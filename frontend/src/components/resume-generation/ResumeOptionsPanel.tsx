import type { ResumeSettings } from "../../types/pipeline";
import { SurfaceCard } from "./WorkflowUI";

export interface ResumeOptionsPanelProps {
  disabled?: boolean;
  settings: ResumeSettings;
  onChange: (settings: ResumeSettings) => void;
  defaultExpanded?: boolean;
  showHeader?: boolean;
}

export function ResumeOptionsPanel({
  disabled = false,
  settings,
  onChange,
  defaultExpanded = false,
  showHeader = true,
}: ResumeOptionsPanelProps) {
  function update<K extends keyof ResumeSettings>(
    key: K,
    value: ResumeSettings[K],
  ) {
    onChange({
      ...settings,
      [key]: value,
    });
  }

  return (
    <SurfaceCard aria-label="Resume options">
      {showHeader ? (
        <div className="rg-section-header" style={{ marginBottom: 16 }}>
          <h2 style={{ marginBottom: 0 }}>Output options</h2>
          <p className="rg-muted" style={{ marginBottom: 0 }}>
            Keep the default settings for a normal run, or expand this panel when you need more visibility or a different output target.
          </p>
        </div>
      ) : null}

      <details open={defaultExpanded}>
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          Advanced settings
        </summary>
        <div style={{ display: "grid", gap: 18, marginTop: 16 }}>
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend style={{ fontWeight: 600 }}>Page length</legend>
            <p className="rg-muted" style={{ margin: "8px 0 10px" }}>
              Use 1 page by default. Switch to 2 pages only when the target role needs broader evidence coverage.
            </p>
            <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
              <label>
                <input
                  type="radio"
                  name="page-length"
                  checked={settings.page_length_pages === 1}
                  onChange={() => update("page_length_pages", 1)}
                  disabled={disabled}
                />
                {" "}1 page
              </label>
              <label>
                <input
                  type="radio"
                  name="page-length"
                  checked={settings.page_length_pages === 2}
                  onChange={() => update("page_length_pages", 2)}
                  disabled={disabled}
                />
                {" "}2 pages
              </label>
            </div>
          </fieldset>

          <label>
            <span style={{ display: "block", fontWeight: 600, marginBottom: 6 }}>
              Template
            </span>
            <input
              className="rg-input"
              type="text"
              value={settings.template_id}
              onChange={(event) => update("template_id", event.currentTarget.value)}
              disabled={disabled}
              placeholder="ats_standard"
            />
            <span className="rg-muted" style={{ display: "block", marginTop: 6 }}>
              Placeholder selector for future multi-template backend support. The current workflow defaults to `ats_standard`.
            </span>
          </label>

          <label>
            <input
              type="checkbox"
              checked={settings.debug_mode}
              onChange={(event) => update("debug_mode", event.currentTarget.checked)}
              disabled={disabled}
            />
            {" "}Debug mode
            <span className="rg-muted" style={{ display: "block", marginTop: 6 }}>
              Keep raw run details, progress events, and backend payloads visible in the workflow screen.
            </span>
          </label>

          <label>
            <input
              type="checkbox"
              checked={settings.show_detailed_diagnostics_after_run}
              onChange={(event) =>
                update(
                  "show_detailed_diagnostics_after_run",
                  event.currentTarget.checked,
                )}
              disabled={disabled}
            />
            {" "}Show diagnostics after run
            <span className="rg-muted" style={{ display: "block", marginTop: 6 }}>
              Keep verification details, warnings, and artifact diagnostics expanded after completion.
            </span>
          </label>
        </div>
      </details>
    </SurfaceCard>
  );
}
