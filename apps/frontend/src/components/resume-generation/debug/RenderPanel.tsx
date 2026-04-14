import type { GenerationResultData } from "../../../types/pipeline";
import type { RenderArtifactDebugData } from "../../../utils/debugInspector";
import { JsonViewer } from "../JsonViewer";

export interface RenderPanelProps {
  result: GenerationResultData | null;
  data: RenderArtifactDebugData;
}

export function RenderPanel({ result, data }: RenderPanelProps) {
  return (
    <section style={panelStyle}>
      <h3 style={titleStyle}>Render and artifacts</h3>

      <div style={summaryGridStyle}>
        <SummaryCard label="Template" value={data.templateName ?? "Not available"} />
        <SummaryCard label="Template version" value={data.templateVersion ?? "Not available"} />
        <SummaryCard label="Page target" value={data.pageTarget ?? "Not available"} />
        <SummaryCard label="LaTeX available" value={data.latexAvailable ? "Yes" : "No"} />
      </div>

      <div style={sectionsGridStyle}>
        <ListCard title="Render warnings" values={data.renderWarnings} emptyLabel="No render warnings reported." />
        <ListCard
          title="Artifact availability"
          values={[
            `Downloadable outputs: ${result?.downloadable_outputs.length ?? 0}`,
            `Render artifacts: ${result?.render_artifacts.length ?? 0}`,
            `PDF metadata rows: ${data.pdfMetadata.length}`,
          ]}
          emptyLabel="No artifact availability details recorded."
        />
        <ListCard
          title="PDF metadata"
          values={data.pdfMetadata.map((item) => `${item.label}: ${item.value}`)}
          emptyLabel="No PDF metadata recorded."
        />
      </div>

      {data.compilerSummary ? (
        <div style={cardStyle}>
          <strong>Compiler summary</strong>
          <p style={{ marginBottom: 0 }}>{data.compilerSummary}</p>
        </div>
      ) : null}

      <JsonViewer
        title="Artifact raw payload"
        payload={{
          outputs: result?.downloadable_outputs ?? [],
          artifacts: result?.render_artifacts ?? [],
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
  const filteredValues = values.filter((value) => value.trim().length > 0);

  return (
    <div style={cardStyle}>
      <strong>{title}</strong>
      {filteredValues.length > 0 ? (
        <ul style={listStyle}>
          {filteredValues.map((value) => (
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
