import type {
  PipelineProgressState,
  ResumeGenerationRunStatus,
  RunMetadata,
} from "../../types/pipeline";
import {
  buildProgressPhases,
  buildRunProgressOverview,
} from "../../utils/progressDataMapper";
import { PhaseProgressItem } from "./PhaseProgressItem";
import { RunStatusHeader } from "./RunStatusHeader";
import { WhatIsHappeningPanel } from "./WhatIsHappeningPanel";
import { SurfaceCard } from "./WorkflowUI";

export interface ProgressTrackerProps {
  progress: PipelineProgressState;
  run: RunMetadata | null;
  overallStatus: ResumeGenerationRunStatus;
  debug?: boolean;
}

export function ProgressTracker({
  progress,
  run,
  overallStatus,
  debug = false,
}: ProgressTrackerProps) {
  const phases = buildProgressPhases(progress);
  const overview = buildRunProgressOverview({
    progress,
    run,
    overallStatus,
  });
  const currentPhase =
    phases.find((phase) => phase.status === "active" || phase.status === "retrying") ??
    phases.find((phase) => phase.status === "failed" || phase.status === "warning");

  return (
    <section aria-label="Resume generation progress" style={{ display: "grid", gap: 16 }}>
      <RunStatusHeader overview={overview} />
      <WhatIsHappeningPanel currentPhase={currentPhase} />

      <SurfaceCard aria-live="polite">
        <h2 style={{ marginTop: 0 }}>{debug ? "Progress phases (debug)" : "Progress phases"}</h2>
        <p className="rg-muted" style={{ marginBottom: 16 }}>
          Completed phases remain visible if a later phase retries, warns, or fails.
        </p>
        <ul style={{ display: "grid", gap: 12, padding: 0, margin: 0 }}>
          {phases.map((phase) => (
            <PhaseProgressItem
              key={phase.key}
              phase={phase}
              debug={debug}
              isCurrent={currentPhase?.key === phase.key}
            />
          ))}
        </ul>
      </SurfaceCard>
    </section>
  );
}
