import type { JobAnalysisDebugData } from "../../../utils/debugInspector";
import { JsonViewer } from "../JsonViewer";

export interface JobAnalysisPanelProps {
  data: JobAnalysisDebugData;
  rawPayloads: unknown[];
}

export function JobAnalysisPanel({ data, rawPayloads }: JobAnalysisPanelProps) {
  return (
    <section style={panelStyle}>
      <h3 style={titleStyle}>Job understanding</h3>

      <SummaryGrid
        items={[
          { label: "Role type", value: data.roleType ?? "Not available" },
          { label: "Seniority", value: data.seniority ?? "Not available" },
        ]}
      />

      <div style={sectionsGridStyle}>
        <ListCard title="Skills" values={data.technicalSkills} emptyLabel="No explicit skills extracted." />
        <ListCard title="Must-have requirements" values={data.mustHaveRequirements} emptyLabel="No must-have requirements recorded." />
        <ListCard title="Nice-to-have requirements" values={data.niceToHaveRequirements} emptyLabel="No preferred requirements recorded." />
        <ListCard title="Action verbs" values={data.actionVerbs} emptyLabel="No action verbs extracted." />
        <ListCard title="Soft skills" values={data.softSkills} emptyLabel="No soft-skill signals extracted." />
        <ListCard title="Domain signals" values={data.domainSignals} emptyLabel="No domain or culture signals extracted." />
      </div>

      <JsonViewer title="Job analysis raw payloads" payload={rawPayloads} />
    </section>
  );
}

function SummaryGrid({ items }: { items: Array<{ label: string; value: string }> }) {
  return (
    <div style={summaryGridStyle}>
      {items.map((item) => (
        <div key={item.label} style={summaryCardStyle}>
          <div style={fieldLabelStyle}>{item.label}</div>
          <div>{item.value}</div>
        </div>
      ))}
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
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
};
const summaryCardStyle = {
  padding: 14,
  border: "1px solid #d6d9de",
  borderRadius: 12,
  background: "#ffffff",
};
const sectionsGridStyle = {
  display: "grid",
  gap: 12,
  gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
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
