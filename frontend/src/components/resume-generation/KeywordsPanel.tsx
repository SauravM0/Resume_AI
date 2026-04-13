import type { GenerationResultData } from "../../types/pipeline";
import { SurfaceCard } from "./WorkflowUI";

export interface KeywordsPanelProps {
  result: GenerationResultData;
}

export function KeywordsPanel({ result }: KeywordsPanelProps) {
  const keywords = extractKeywords(result);
  
  if (keywords.length === 0) {
    return null;
  }
  
  return (
    <SurfaceCard aria-label="Extracted keywords">
      <h3 style={{ marginTop: 0 }}>Extracted keywords</h3>
      <p className="rg-muted" style={{ marginTop: 0, marginBottom: 12 }}>
        Keywords identified from the job description that guided evidence selection.
      </p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {keywords.slice(0, 30).map((keyword, index) => (
          <span
            key={`${keyword}-${index}`}
            style={{
              background: "var(--rg-surface-elevated)",
              padding: "4px 10px",
              borderRadius: 12,
              fontSize: "0.85rem",
              color: "var(--rg-text-primary)",
            }}
          >
            {keyword}
          </span>
        ))}
      </div>
      {keywords.length > 30 && (
        <p style={{ marginTop: 8, color: "var(--rg-text-subtle)", fontSize: "0.85rem" }}>
          +{keywords.length - 30} more keywords
        </p>
      )}
    </SurfaceCard>
  );
}

function extractKeywords(result: GenerationResultData): string[] {
  const keywords: string[] = [];
  
  const rawResponse = result.raw_response;
  const stageEvents = rawResponse?.stage_events || [];
  
  for (const event of stageEvents) {
    const machinePayload = (event as Record<string, unknown>).machine_payload_json as Record<string, unknown> | undefined;
    if (!machinePayload) continue;
    
    const roleType = machinePayload.role_type;
    if (roleType && typeof roleType === "string") {
      keywords.push(roleType);
    }
    
    const seniority = machinePayload.seniority_level;
    if (seniority && typeof seniority === "string") {
      keywords.push(seniority);
    }
    
    const requiredSkills = machinePayload.required_skills;
    if (Array.isArray(requiredSkills)) {
      for (const skill of requiredSkills) {
        if (typeof skill === "string" && !keywords.includes(skill)) {
          keywords.push(skill);
        }
      }
    }
    
    const matchedKeywords = machinePayload.matched_keywords;
    if (Array.isArray(matchedKeywords)) {
      for (const kw of matchedKeywords) {
        if (typeof kw === "string" && !keywords.includes(kw)) {
          keywords.push(kw);
        }
      }
    }
  }
  
  return [...new Set(keywords)];
}