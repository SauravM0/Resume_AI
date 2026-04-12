import type { ResumeSettings } from "../../types/pipeline";

export interface ResumeSettingsPanelProps {
  disabled?: boolean;
  settings: ResumeSettings;
  onChange: (settings: ResumeSettings) => void;
}

export function ResumeSettingsPanel({
  disabled = false,
  settings,
  onChange,
}: ResumeSettingsPanelProps) {
  function update<K extends keyof ResumeSettings>(key: K, value: ResumeSettings[K]) {
    onChange({
      ...settings,
      [key]: value,
    });
  }

  return (
    <section aria-label="Resume settings">
      <h2 style={{ marginTop: 0 }}>Resume settings</h2>
      <p className="rg-muted">
        Choose output behavior before starting the run. These settings affect generation intent and inspection detail.
      </p>

      <div style={{ display: "grid", gap: 16 }}>
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend style={{ fontWeight: 600 }}>Page length</legend>
          <p className="rg-muted" style={{ margin: "8px 0" }}>
            1 page keeps the resume tighter. 2 pages allows more evidence when the target role needs broader coverage.
          </p>
          <label style={{ display: "block", marginBottom: 8 }}>
            <input
              type="radio"
              name="page-length"
              checked={settings.page_length_pages === 1}
              onChange={() => update("page_length_pages", 1)}
              disabled={disabled}
            />
            {" "}1 page
          </label>
          <label style={{ display: "block" }}>
            <input
              type="radio"
              name="page-length"
              checked={settings.page_length_pages === 2}
              onChange={() => update("page_length_pages", 2)}
              disabled={disabled}
            />
            {" "}2 pages
          </label>
        </fieldset>

        <label>
          <span style={{ fontWeight: 600 }}>Template</span>
          <input
            className="rg-input"
            type="text"
            value={settings.template_id}
            onChange={(event) => update("template_id", event.currentTarget.value)}
            disabled={disabled}
            placeholder="ats_standard"
            style={{ marginTop: 6 }}
          />
          <span className="rg-muted" style={{ display: "block", marginTop: 6 }}>
            Current backend path defaults to `ats_standard`. This control keeps template selection explicit for future multi-template support.
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
            Shows raw progress events, payloads, and error details after or during the run.
          </span>
        </label>

        <label>
          <input
            type="checkbox"
            checked={settings.show_detailed_diagnostics_after_run}
            onChange={(event) => update("show_detailed_diagnostics_after_run", event.currentTarget.checked)}
            disabled={disabled}
          />
          {" "}Show detailed diagnostics after run
          <span className="rg-muted" style={{ display: "block", marginTop: 6 }}>
            Keeps deeper verification and artifact details visible once results arrive.
          </span>
        </label>

        <label>
          <input
            type="checkbox"
            checked={settings.strict_mode}
            onChange={(event) => update("strict_mode", event.currentTarget.checked)}
            disabled
          />
          {" "}Strict mode
          <span className="rg-muted" style={{ display: "block", marginTop: 6 }}>
            Placeholder for future stricter generation constraints. Not yet enforced by the current backend contract.
          </span>
        </label>
      </div>
    </section>
  );
}
