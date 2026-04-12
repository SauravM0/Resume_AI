import { ArtifactLinksPanel } from "./ArtifactLinksPanel";
import { ArtifactActions } from "./ArtifactActions";
import { RunQualitySummary } from "./RunQualitySummary";
import { SelectionSummary } from "./SelectionSummary";
import {
  countMeaningfulWarnings,
  formatPipelineOutcome,
  hasFallbackUsage,
  inferDetectedRole,
  inferGeneratedPageLength,
} from "../../utils/resumeGenerationFormatters";
import type { GenerationResultData } from "../../types/pipeline";
import { EmptyState, StatusBadge, SurfaceCard } from "./WorkflowUI";

export interface GenerationResultProps {
  result: GenerationResultData;
  onStartNewRun: () => void;
  debug?: boolean;
}

export function GenerationResult({
  result,
  onStartNewRun,
  debug = false,
}: GenerationResultProps) {
  const warningsCount = countMeaningfulWarnings(result);
  const fallbackUsed = hasFallbackUsage(result.diagnostics?.fallback_repairs);
  const role = inferDetectedRole(result);
  const pageLength = inferGeneratedPageLength(result);
  const outcomeType =
    result.overall_status === "succeeded" && warningsCount === 0 && !fallbackUsed
      ? "success"
      : result.overall_status === "succeeded_with_warnings" || warningsCount > 0 || fallbackUsed
        ? "partial"
        : "success";

  return (
    <section aria-label="Generation result" style={{ display: "grid", gap: 16 }}>
      <SurfaceCard>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <StatusBadge tone={outcomeType === "success" ? "success" : "warning"}>
            {outcomeType === "success"
              ? "Successful run"
              : result.overall_status === "succeeded_with_warnings"
                ? "Success with warnings"
                : "Partial success"}
          </StatusBadge>
          {warningsCount > 0 ? <StatusBadge tone="warning">{warningsCount} warnings</StatusBadge> : null}
          {fallbackUsed ? <StatusBadge tone="warning">Repair used</StatusBadge> : null}
        </div>
        <h2 style={{ marginBottom: 8 }}>Result summary</h2>
        <p className="rg-muted" style={{ marginTop: 0 }}>
          {outcomeType === "success"
            ? "The run completed cleanly and produced usable outputs."
            : "The run produced outputs, but warnings, fallback behavior, or incomplete artifacts require review before final use."}
        </p>
        <div className="rg-meta-grid">
          <SummaryStat label="Final status" value={formatPipelineOutcome(result.overall_status)} />
          <SummaryStat label="Detected role / title" value={role ?? "Not reported"} />
          <SummaryStat label="Page length" value={pageLength} />
          <SummaryStat label="Selected experiences" value={String(result.selected_experiences.length)} />
          <SummaryStat label="Selected projects" value={String(result.selected_projects.length)} />
          <SummaryStat label="Selected skills" value={String(result.selected_skills.length)} />
          <SummaryStat label="Warnings count" value={String(warningsCount)} />
          <SummaryStat label="Fallback / repair used" value={fallbackUsed ? "Yes" : "No"} />
        </div>
      </SurfaceCard>

      <ArtifactActions
        result={result}
        debug={debug}
        onStartNewRun={onStartNewRun}
      />

      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
        <RunQualitySummary result={result} />
        <ArtifactLinksPanel result={result} debug={debug} />
      </div>

      <SelectionSummary result={result} />

      {debug ? (
        <SurfaceCard>
          <h3 style={{ marginTop: 0 }}>Diagnostics</h3>
          {(result.diagnostics?.messages ?? []).length > 0 ? (
            <>
              <p>
                <strong>Messages:</strong>
              </p>
              <ul>
                {(result.diagnostics?.messages ?? []).map((message, index) => (
                  <li key={`${message}-${index}`}>{message}</li>
                ))}
              </ul>
            </>
          ) : (
            <EmptyState
              title="Diagnostics are not available for this run"
              description="The backend did not return additional diagnostic messages in the completed result payload."
            />
          )}
          {result.verification_warnings.length > 0 ? (
            <>
              <p>
                <strong>Verification warnings:</strong>
              </p>
              <ul>
                {result.verification_warnings.map((warning, index) => (
                  <li key={`${warning.message}-${index}`}>
                    {warning.message}
                    {warning.code ? ` (${warning.code})` : null}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </SurfaceCard>
      ) : null}

      {outcomeType === "partial" ? (
        <SurfaceCard tone="warning">
          <h3 style={{ marginTop: 0 }}>Review before using</h3>
          <ul>
            {warningsCount > 0 ? <li>Warnings were reported during verification or final response packaging.</li> : null}
            {!result.downloadable_outputs.some((output) => output.kind === "pdf") ? (
              <li>Structured output exists, but a final PDF may not have been produced.</li>
            ) : null}
            {result.downloadable_outputs.some((output) => output.kind === "pdf") && warningsCount > 0 ? (
              <li>A PDF was generated, but verification concerns still need review.</li>
            ) : null}
            {fallbackUsed ? <li>Fallback or repair logic was used during the run.</li> : null}
          </ul>
        </SurfaceCard>
      ) : null}
    </section>
  );
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rg-stat">
      <strong>{label}</strong>
      <div>{value}</div>
    </div>
  );
}
