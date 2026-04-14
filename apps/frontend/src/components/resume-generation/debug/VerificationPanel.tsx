import type { GenerationResultData } from "../../../types/pipeline";
import type { VerificationDebugData } from "../../../utils/debugInspector";
import { JsonViewer } from "../JsonViewer";

export interface VerificationPanelProps {
  result: GenerationResultData | null;
  data: VerificationDebugData;
}

export function VerificationPanel({ result, data }: VerificationPanelProps) {
  const fallbackEvents = result?.diagnostics?.fallback_repairs ?? [];
  const warnings = result?.verification_warnings ?? [];

  return (
    <section style={panelStyle}>
      <h3 style={titleStyle}>Verification and repair</h3>

      <div style={summaryGridStyle}>
        <SummaryCard
          label="Verification status"
          value={data.verificationStatus ?? (warnings.length > 0 ? "Warnings present" : "Not available")}
        />
        <SummaryCard label="Warnings" value={String(warnings.length)} />
        <SummaryCard label="Unsupported claims" value={String(data.unsupportedClaims.length)} />
        <SummaryCard label="Fallback / repair events" value={String(fallbackEvents.length)} />
      </div>

      <div style={sectionsGridStyle}>
        <ListCard title="Warnings" values={warnings.map((warning) => warning.message)} emptyLabel="No verification warnings reported." />
        <ListCard title="Unsupported claim issues" values={data.unsupportedClaims} emptyLabel="No unsupported claims reported." />
        <ListCard title="Semantic verification results" values={data.semanticResults} emptyLabel="No semantic verification details available." />
        <ListCard
          title="Fallback / repair events"
          values={fallbackEvents.map((item) => item.strategy ?? item.reason ?? "repair applied")}
          emptyLabel="No fallback or repair events recorded."
        />
      </div>

      <JsonViewer
        title="Verification raw payload"
        payload={{
          verification_warnings: warnings,
          diagnostics: result?.diagnostics ?? null,
        }}
      />
    </section>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={summaryCardStyle}>
      <div style={fieldLabelStyle}>{label}</div>
      <div>{value}</div>
    </div>
  );
}

function ListCard({
  title,
  values,
  emptyLabel,
}: {
  title: string;
  values: string[];
  emptyLabel: string;
}) {
  return (
    <div style={cardStyle}>
      <strong>{title}</strong>
      {values.length > 0 ? (
        <ul style={listStyle}>
          {values.map((value) => (
            <li key={value}>{value}</li>
          ))}
        </ul>
      ) : (
        <p style={emptyTextStyle}>{emptyLabel}</p>
      )}
    </div>
  );
}

const titleStyle = { marginTop: 0, marginBottom: 16 };
const panelStyle = { display: "grid", gap: 16 };
const summaryGridStyle = {
  display: "grid",
  gap: 12,
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
};
const sectionsGridStyle = {
  display: "grid",
  gap: 12,
  gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
};
const summaryCardStyle = {
  padding: 14,
  border: "1px solid #d6d9de",
  borderRadius: 12,
  background: "#ffffff",
};
const cardStyle = {
  padding: 14,
  border: "1px solid #d6d9de",
  borderRadius: 12,
  background: "#ffffff",
};
const fieldLabelStyle = {
  fontSize: "0.82rem",
  color: "#4b5563",
  marginBottom: 6,
};
const listStyle = { margin: "10px 0 0", paddingLeft: 18 };
const emptyTextStyle = { color: "#4b5563", marginBottom: 0 };
