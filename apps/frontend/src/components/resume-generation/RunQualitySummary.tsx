import type { GenerationResultData } from "../../types/pipeline";
import {
  countMeaningfulWarnings,
  deriveResultTrustLabel,
  formatPipelineOutcome,
  hasFallbackUsage,
} from "../../utils/resumeGenerationFormatters";
import { SurfaceCard, StatusBadge } from "./WorkflowUI";

export interface RunQualitySummaryProps {
  result: GenerationResultData;
}

export function RunQualitySummary({ result }: RunQualitySummaryProps) {
  const warningsCount = countMeaningfulWarnings(result);
  const fallbackUsed = hasFallbackUsage(result.diagnostics?.fallback_repairs);
  const trustLabel = deriveResultTrustLabel(result);
  const partialSuccess = result.overall_status === "succeeded_with_warnings";
  const reviewRecommended = partialSuccess || warningsCount > 0 || fallbackUsed;
  const verificationStatus =
    warningsCount > 0
      ? "Warnings present"
      : partialSuccess
        ? "Completed with caution"
        : "Passed cleanly";

  return (
    <SurfaceCard aria-label="Run quality summary">
      <h3 style={{ marginTop: 0 }}>Run quality summary</h3>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <StatusBadge tone={partialSuccess ? "warning" : "success"}>
          {formatPipelineOutcome(result.overall_status)}
        </StatusBadge>
        {reviewRecommended ? (
          <StatusBadge tone="warning">Human review recommended</StatusBadge>
        ) : (
          <StatusBadge tone="success">Human review not required</StatusBadge>
        )}
      </div>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        <QualityMetric label="Verification status" value={verificationStatus} />
        <QualityMetric label="Warnings count" value={String(warningsCount)} />
        <QualityMetric label="Fallback used" value={fallbackUsed ? "Yes" : "No"} />
        <QualityMetric label="Trust level" value={trustLabel} />
      </div>
      {partialSuccess ? (
        <p style={{ margin: "12px 0 0", color: "#4b5563" }}>
          Partial success means the run produced usable output, but warnings, repairs, or incomplete artifacts should be reviewed before final use.
        </p>
      ) : null}
      {result.diagnostics?.fallback_repairs.length ? (
        <p style={{ margin: "12px 0 0", color: "#4b5563" }}>
          Fallback summary: {result.diagnostics.fallback_repairs.map((item) => item.strategy ?? item.reason ?? "repair applied").join(", ")}
        </p>
      ) : null}
    </SurfaceCard>
  );
}

function QualityMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <strong>{label}</strong>
      <div>{value}</div>
    </div>
  );
}
