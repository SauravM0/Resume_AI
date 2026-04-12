import type { ResumeGenerationState } from "../../types/pipeline";
import { DebugInspector } from "./debug/DebugInspector";

export interface DebugPanelProps {
  state: ResumeGenerationState;
}

export function DebugPanel({ state }: DebugPanelProps) {
  return <DebugInspector state={state} />;
}
