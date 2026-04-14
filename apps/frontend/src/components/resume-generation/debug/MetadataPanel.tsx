import type {
  BackendErrorPayload,
  GenerationResultData,
  PipelineProgressState,
  RunMetadata,
} from "../../../types/pipeline";
import type { RawRunMetadataDebugData } from "../../../utils/debugInspector";
import { formatElapsedDuration, formatTimestamp } from "../../../utils/timingFormatters";
import { JsonViewer } from "../JsonViewer";

export interface MetadataPanelProps {
  run: RunMetadata | null;
  progress: PipelineProgressState | null;
  result: GenerationResultData | null;
  error: BackendErrorPayload | null;
  data: RawRunMetadataDebugData;
}

export function MetadataPanel({ run, progress, result, error, data }: MetadataPanelProps) {
  return (
    <section style={panelStyle}>
      <h3 style={titleStyle}>Run metadata</h3>

      <div style={summaryGridStyle}>
        <SummaryCard label="Run ID" value={data.runId ?? "Not available"} />
        <SummaryCard label="Backend endpoint" value={data.endpoint} />
        <SummaryCard label="Started" value={formatTimestamp(data.startedAt)} />
        <SummaryCard label="Finished" value={formatTimestamp(data.finishedAt)} />
        <SummaryCard label="Elapsed" value={formatElapsedDuration(data.durationSeconds)} />
        <SummaryCard label="Retry count" value={String(data.retryCount)} />
      </div>

      <div style={cardStyle}>
        <strong>Phase transitions</strong>
        {data.phaseTransitions.length > 0 ? (
          <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
            {data.phaseTransitions.map((transition) => (
              <article key={`${transition.timestamp}-${transition.eventType}-${transition.phase}`} style={nestedCardStyle}>
                <div style={{ fontWeight: 600 }}>{transition.phase}</div>
                <div style={metaTextStyle}>Event: {transition.eventType}</div>
                <div style={metaTextStyle}>Time: {formatTimestamp(transition.timestamp)}</div>
                <div style={metaTextStyle}>Message: {transition.message || "No detail message"}</div>
              </article>
            ))}
          </div>
        ) : (
          <p style={emptyTextStyle}>No phase transitions recorded.</p>
        )}
      </div>

      <JsonViewer
        title="Run metadata raw payload"
        payload={{
          run,
          progress_state: progress,
          result_metadata: result?.run_metadata ?? null,
          error,
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

const titleStyle = { marginTop: 0, marginBottom: 16 };
const panelStyle = { display: "grid", gap: 16 };
const summaryGridStyle = {
  display: "grid",
  gap: 12,
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
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
const emptyTextStyle = { color: "#4b5563", marginBottom: 0 };
