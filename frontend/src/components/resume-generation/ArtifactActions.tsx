import { useMemo, useState } from "react";

import type { ArtifactItemViewModel, GenerationResultData } from "../../types/pipeline";
import {
  buildRunArtifactCollection,
  canDownloadArtifact,
  canInlinePreviewPdf,
  canPreviewArtifact,
  getArtifactStateTone,
} from "../../utils/artifactHelpers";
import { downloadArtifact } from "../../utils/downloadHelpers";
import { ArtifactCodeViewer } from "./ArtifactCodeViewer";
import { LatexViewerModal } from "./LatexViewerModal";
import { PdfPreviewPanel } from "./PdfPreviewPanel";
import { StatusBadge } from "./WorkflowUI";
import { SurfaceCard } from "./WorkflowUI";

export interface ArtifactActionsProps {
  result: GenerationResultData;
  debug?: boolean;
  onStartNewRun: () => void;
}

export function ArtifactActions({
  result,
  debug = false,
  onStartNewRun,
}: ArtifactActionsProps) {
  const [downloadingKind, setDownloadingKind] = useState<string | null>(null);
  const [pdfPreviewOpen, setPdfPreviewOpen] = useState(false);
  const [latexViewerOpen, setLatexViewerOpen] = useState(false);
  const [structuredViewerOpen, setStructuredViewerOpen] = useState(false);
  const artifactCollection = useMemo(() => buildRunArtifactCollection(result), [result]);
  const pdfArtifact = artifactCollection.pdf;
  const latexArtifact = artifactCollection.latex;
  const structuredArtifact = artifactCollection.structuredJson;
  const pdfPreviewSupported = canInlinePreviewPdf();

  async function handleDownload(artifact?: ArtifactItemViewModel | null) {
    if (!artifact?.download_url) {
      return;
    }

    setDownloadingKind(artifact.kind);
    try {
      await downloadArtifact(artifact, result.run_metadata.run_id);
    } finally {
      setDownloadingKind(null);
    }
  }

  return (
    <SurfaceCard aria-label="Artifact actions" style={{ display: "grid", gap: 16 }}>
      <div className="rg-section-header">
        <h3 style={{ marginBottom: 0 }}>Artifact access</h3>
        <p className="rg-muted" style={{ marginBottom: 0 }}>
          These actions apply only to run <code>{result.run_metadata.run_id}</code>. Missing or partial artifacts are shown
          explicitly so failed runs do not look complete.
        </p>
      </div>

      <div className="rg-actions">
        <button
          className="rg-button rg-button-primary"
          type="button"
          disabled={!canDownloadArtifact(pdfArtifact) || downloadingKind === "pdf"}
          onClick={() => void handleDownload(pdfArtifact)}
        >
          {downloadingKind === "pdf" ? "Downloading..." : "Download PDF"}
        </button>

        <button
          className="rg-button"
          type="button"
          disabled={!canPreviewArtifact(pdfArtifact)}
          onClick={() => setPdfPreviewOpen(true)}
        >
          Preview PDF
        </button>

        <button
          className="rg-button"
          type="button"
          disabled={!canPreviewArtifact(latexArtifact)}
          onClick={() => setLatexViewerOpen(true)}
        >
          View LaTeX
        </button>

        {debug ? (
          <button
            className="rg-button"
            type="button"
            disabled={!canPreviewArtifact(structuredArtifact)}
            onClick={() => setStructuredViewerOpen(true)}
          >
            Inspect structured output
          </button>
        ) : null}

        <button
          className="rg-button rg-button-ghost"
          type="button"
          onClick={onStartNewRun}
        >
          Start new run
        </button>
      </div>

      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        <ArtifactStatusCard artifact={pdfArtifact} downloading={downloadingKind === "pdf"} />
        <ArtifactStatusCard artifact={latexArtifact} downloading={downloadingKind === "latex"} />
        <ArtifactStatusCard artifact={structuredArtifact} downloading={downloadingKind === "structured_json"} />
      </div>

      <PdfPreviewPanel
        title="PDF preview"
        sourceUrl={pdfArtifact.preview_url}
        open={pdfPreviewOpen}
        onClose={() => setPdfPreviewOpen(false)}
        previewSupported={pdfPreviewSupported}
        onDownload={canDownloadArtifact(pdfArtifact) ? () => void handleDownload(pdfArtifact) : undefined}
        downloading={downloadingKind === "pdf"}
      />

      <LatexViewerModal
        artifact={latexArtifact}
        runId={result.run_metadata.run_id}
        open={latexViewerOpen}
        onClose={() => setLatexViewerOpen(false)}
      />

      <ArtifactCodeViewer
        title="Structured JSON"
        url={structuredArtifact.preview_url}
        open={structuredViewerOpen}
        onClose={() => setStructuredViewerOpen(false)}
      />
    </SurfaceCard>
  );
}

function ArtifactStatusCard({
  artifact,
  downloading,
}: {
  artifact: ArtifactItemViewModel;
  downloading: boolean;
}) {
  const displayState = downloading ? "downloading" : artifact.state;

  return (
    <article
      style={{
        display: "grid",
        gap: 8,
        padding: 14,
        borderRadius: 12,
        border: "1px solid var(--rg-border)",
        background: "var(--rg-surface-muted)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
        <strong>{artifact.label}</strong>
        <StatusBadge tone={getArtifactStateTone(displayState)}>
          {displayState}
        </StatusBadge>
      </div>
      <p className="rg-muted" style={{ margin: 0 }}>
        {artifact.message}
      </p>
      {artifact.file_name ? (
        <div className="rg-muted" style={{ fontSize: "0.92rem" }}>
          {artifact.file_name}
        </div>
      ) : null}
    </article>
  );
}
