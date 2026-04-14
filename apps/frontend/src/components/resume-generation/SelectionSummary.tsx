import type { GenerationResultData } from "../../types/pipeline";
import { summarizeSelectionItem } from "../../utils/resumeGenerationFormatters";
import { SurfaceCard } from "./WorkflowUI";

export interface SelectionSummaryProps {
  result: GenerationResultData;
}

export function SelectionSummary({ result }: SelectionSummaryProps) {
  return (
    <SurfaceCard aria-label="Selection summary">
      <h3 style={{ marginTop: 0 }}>Selection summary</h3>
      <p className="rg-muted" style={{ marginTop: 0 }}>
        Review the evidence the run chose to represent the role. Rationale and matching keywords are shown when the backend returned them.
      </p>
      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        <SelectionColumn
          title={`Experiences (${result.selected_experiences.length})`}
          items={result.selected_experiences.map((item) => ({
            id: item.id,
            label: summarizeSelectionItem(item),
            rationale: item.rationale ?? item.summary,
            evidence: item.evidence,
          }))}
        />
        <SelectionColumn
          title={`Projects (${result.selected_projects.length})`}
          items={result.selected_projects.map((item) => ({
            id: item.id,
            label: summarizeSelectionItem(item),
            rationale: item.rationale ?? item.summary,
            evidence: item.evidence,
          }))}
        />
        <SelectionColumn
          title={`Skills (${result.selected_skills.length})`}
          items={result.selected_skills.map((item) => ({
            id: item.id,
            label: summarizeSelectionItem(item),
            rationale: item.rationale,
            evidence: undefined,
          }))}
        />
      </div>
    </SurfaceCard>
  );
}

interface SelectionColumnProps {
  title: string;
  items: Array<{ id: string; label: string; rationale?: string; evidence?: string[] }>;
}

function SelectionColumn({ title, items }: SelectionColumnProps) {
  return (
    <div>
      <strong>{title}</strong>
      {items.length > 0 ? (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <div>{item.label}</div>
              {item.rationale ? (
                <div style={{ color: "#4b5563", fontSize: "0.95rem" }}>{item.rationale}</div>
              ) : null}
              {item.evidence && item.evidence.length > 0 ? (
                <div style={{ color: "#4b5563", fontSize: "0.9rem", marginTop: 4 }}>
                  Matching keywords: {item.evidence.join(", ")}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p style={{ color: "#4b5563" }}>No items recorded for this category.</p>
      )}
    </div>
  );
}
