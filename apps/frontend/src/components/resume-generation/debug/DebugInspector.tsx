import { useMemo, useState } from "react";

import type { ResumeGenerationState } from "../../../types/pipeline";
import {
  buildEvidenceSelectionDebugData,
  buildJobAnalysisDebugData,
  buildRawRunMetadataDebugData,
  buildRenderArtifactDebugData,
  buildVerificationDebugData,
  collectInspectorSources,
} from "../../../utils/debugInspector";
import { EmptyState, SurfaceCard } from "../WorkflowUI";
import { JobAnalysisPanel } from "./JobAnalysisPanel";
import { MetadataPanel } from "./MetadataPanel";
import { RenderPanel } from "./RenderPanel";
import { SelectionPanel } from "./SelectionPanel";
import { VerificationPanel } from "./VerificationPanel";

export interface DebugInspectorProps {
  state: ResumeGenerationState;
}

type DebugTab = "job_analysis" | "selection" | "verification" | "render" | "metadata";

const tabs: Array<{ key: DebugTab; label: string; description: string }> = [
  {
    key: "job_analysis",
    label: "Job analysis",
    description: "Inspect what the backend inferred from the job description.",
  },
  {
    key: "selection",
    label: "Selection",
    description: "Review the evidence and skills chosen for generation.",
  },
  {
    key: "verification",
    label: "Verification",
    description: "Check warnings, unsupported claims, and repair behavior.",
  },
  {
    key: "render",
    label: "Render",
    description: "Inspect template, page target, and artifact readiness.",
  },
  {
    key: "metadata",
    label: "Metadata",
    description: "Review timings, phase transitions, and backend context.",
  },
];

export function DebugInspector({ state }: DebugInspectorProps) {
  const [activeTab, setActiveTab] = useState<DebugTab>("job_analysis");

  const inspectorSources = useMemo(() => collectInspectorSources(state), [state]);
  const jobAnalysis = useMemo(() => buildJobAnalysisDebugData(state), [state]);
  const evidenceSelection = useMemo(() => buildEvidenceSelectionDebugData(state), [state]);
  const verification = useMemo(() => buildVerificationDebugData(state), [state]);
  const renderArtifacts = useMemo(() => buildRenderArtifactDebugData(state), [state]);
  const rawMetadata = useMemo(() => buildRawRunMetadataDebugData(state), [state]);

  if (!state.debug_visible) {
    return null;
  }

  const hasAnyDebugData = Boolean(state.run || state.progress || state.result || state.error);

  return (
    <SurfaceCard
      aria-label="Debug inspector"
      tone="muted"
      style={{
        display: "grid",
        gap: 16,
      }}
    >
      <div className="rg-section-header">
        <h2 style={{ marginTop: 0, marginBottom: 4 }}>Debug inspector</h2>
        <p className="rg-muted" style={{ margin: 0, maxWidth: 820 }}>
          Internal inspection mode for product testing. Interpreted views are shown first. Raw JSON stays available inside
          each panel when deeper backend inspection is needed.
        </p>
      </div>

      {!hasAnyDebugData ? (
        <EmptyState
          title="No debug data yet"
          description="Start a run with debug mode enabled to inspect job understanding, evidence selection, verification details, render outputs, and phase metadata."
        />
      ) : null}

      <div className="rg-tablist" role="tablist" aria-label="Debug inspector panels">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            id={`debug-tab-${tab.key}`}
            className="rg-tab"
            onClick={() => setActiveTab(tab.key)}
            onKeyDown={(event) => handleTabKeyDown(indexOfTab(tab.key), event.key, setActiveTab)}
            aria-selected={activeTab === tab.key}
            aria-controls={`debug-panel-${tab.key}`}
            tabIndex={activeTab === tab.key ? 0 : -1}
            title={tab.description}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {hasAnyDebugData ? (
        <div
          style={{
            padding: 12,
            borderRadius: 12,
            border: "1px solid #d6d9de",
            background: "#f5f7fa",
          }}
        >
          <strong>{tabs.find((tab) => tab.key === activeTab)?.label}</strong>
          <p className="rg-muted" style={{ margin: "6px 0 0" }}>
            {tabs.find((tab) => tab.key === activeTab)?.description}
          </p>
        </div>
      ) : null}

      <div role="tabpanel" id={`debug-panel-${activeTab}`} aria-labelledby={`debug-tab-${activeTab}`}>
        {activeTab === "job_analysis" ? (
          <JobAnalysisPanel data={jobAnalysis} rawPayloads={inspectorSources} />
        ) : null}
        {activeTab === "selection" ? (
          <SelectionPanel result={state.result} data={evidenceSelection} />
        ) : null}
        {activeTab === "verification" ? (
          <VerificationPanel result={state.result} data={verification} />
        ) : null}
        {activeTab === "render" ? (
          <RenderPanel result={state.result} data={renderArtifacts} />
        ) : null}
        {activeTab === "metadata" ? (
          <MetadataPanel
            run={state.run}
            progress={state.progress}
            result={state.result}
            error={state.error}
            data={rawMetadata}
          />
        ) : null}
      </div>
    </SurfaceCard>
  );
}

function handleTabKeyDown(
  index: number,
  key: string,
  setActiveTab: (value: DebugTab) => void,
) {
  if (key !== "ArrowRight" && key !== "ArrowLeft" && key !== "Home" && key !== "End") {
    return;
  }

  if (key === "Home") {
    setActiveTab(tabs[0].key);
    return;
  }

  if (key === "End") {
    setActiveTab(tabs[tabs.length - 1].key);
    return;
  }

  const direction = key === "ArrowRight" ? 1 : -1;
  const nextIndex = (index + direction + tabs.length) % tabs.length;
  setActiveTab(tabs[nextIndex].key);
}

function indexOfTab(key: DebugTab) {
  return tabs.findIndex((tab) => tab.key === key);
}
