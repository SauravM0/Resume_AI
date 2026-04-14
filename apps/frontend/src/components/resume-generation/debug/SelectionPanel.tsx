import type { GenerationResultData } from "../../../types/pipeline";
import type { EvidenceSelectionDebugData } from "../../../utils/debugInspector";
import { JsonViewer } from "../JsonViewer";

export interface SelectionPanelProps {
  result: GenerationResultData | null;
  data: EvidenceSelectionDebugData;
}

export function SelectionPanel({ result, data }: SelectionPanelProps) {
  return (
    <section style={panelStyle}>
      <h3 style={titleStyle}>Selection review</h3>

      <div style={summaryGridStyle}>
        <SummaryCard label="Experiences selected" value={String(result?.selected_experiences.length ?? 0)} />
        <SummaryCard label="Projects selected" value={String(result?.selected_projects.length ?? 0)} />
        <SummaryCard label="Skills selected" value={String(result?.selected_skills.length ?? 0)} />
        <SummaryCard label="Matched keywords" value={String(data.matchingKeywords.length)} />
      </div>

      <div style={sectionsGridStyle}>
        <SelectionBlock
          title="Selected experiences"
          items={result?.selected_experiences.map((item) => ({
            key: item.id,
            title: [item.title, item.company].filter(Boolean).join(" at ") || item.id,
            score: item.score,
            rationale: item.rationale ?? item.summary,
            extra: item.evidence?.join(", "),
          })) ?? []}
          emptyLabel="No experiences were selected."
        />
        <SelectionBlock
          title="Selected projects"
          items={result?.selected_projects.map((item) => ({
            key: item.id,
            title: item.name ?? item.id,
            score: item.score,
            rationale: item.rationale ?? item.summary,
            extra: item.evidence?.join(", "),
          })) ?? []}
          emptyLabel="No projects were selected."
        />
        <SelectionBlock
          title="Selected skills"
          items={result?.selected_skills.map((item) => ({
            key: item.id,
            title: item.name,
            score: item.score,
            rationale: item.rationale,
            extra: item.category,
          })) ?? []}
          emptyLabel="No skills were selected."
        />
      </div>

      <div style={sectionsGridStyle}>
        <ListCard title="Excluded experiences" values={data.excludedExperiences} emptyLabel="No excluded experiences reported." />
        <ListCard title="Excluded projects" values={data.excludedProjects} emptyLabel="No excluded projects reported." />
        <ListCard title="Excluded skills" values={data.excludedSkills} emptyLabel="No excluded skills reported." />
        <ListCard title="Matching keywords" values={data.matchingKeywords} emptyLabel="No matching keywords recorded." />
      </div>

      <JsonViewer
        title="Selection raw payload"
        payload={{
          selected_experiences: result?.selected_experiences ?? [],
          selected_projects: result?.selected_projects ?? [],
          selected_skills: result?.selected_skills ?? [],
          matching_keywords: data.matchingKeywords,
          excluded_experiences: data.excludedExperiences,
          excluded_projects: data.excludedProjects,
          excluded_skills: data.excludedSkills,
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

function SelectionBlock({
  title,
  items,
  emptyLabel,
}: {
  title: string;
  items: Array<{ key: string; title: string; score?: number; rationale?: string; extra?: string }>;
  emptyLabel: string;
}) {
  return (
    <div style={cardStyle}>
      <strong>{title}</strong>
      {items.length > 0 ? (
        <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
          {items.map((item) => (
            <article key={item.key} style={nestedCardStyle}>
              <div style={{ fontWeight: 600 }}>{item.title}</div>
              {item.score !== undefined ? <div style={metaTextStyle}>Relevance score: {item.score}</div> : null}
              {item.extra ? <div style={metaTextStyle}>Keywords / context: {item.extra}</div> : null}
              {item.rationale ? <div style={metaTextStyle}>Rationale: {item.rationale}</div> : null}
            </article>
          ))}
        </div>
      ) : (
        <p style={emptyTextStyle}>{emptyLabel}</p>
      )}
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
const nestedCardStyle = {
  padding: 12,
  borderRadius: 10,
  border: "1px solid #e3e7ec",
  background: "#f8fafc",
};
const fieldLabelStyle = {
  fontSize: "0.82rem",
  color: "#4b5563",
  marginBottom: 6,
};
const metaTextStyle = { color: "#4b5563", marginTop: 4 };
const listStyle = { margin: "10px 0 0", paddingLeft: 18 };
const emptyTextStyle = { color: "#4b5563", marginBottom: 0 };
