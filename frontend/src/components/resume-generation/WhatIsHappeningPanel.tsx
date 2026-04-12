import type { ProgressPhaseViewModel } from "../../types/pipeline";
import { SurfaceCard } from "./WorkflowUI";

export interface WhatIsHappeningPanelProps {
  currentPhase?: ProgressPhaseViewModel;
}

export function WhatIsHappeningPanel({ currentPhase }: WhatIsHappeningPanelProps) {
  return (
    <SurfaceCard aria-label="What is happening" tone="muted">
      <h3 style={{ marginTop: 0 }}>What is happening</h3>
      <p style={{ marginBottom: 0, color: "var(--rg-text)" }}>
        {currentPhase?.description ?? "Waiting for the backend to begin processing this run."}
      </p>
    </SurfaceCard>
  );
}
