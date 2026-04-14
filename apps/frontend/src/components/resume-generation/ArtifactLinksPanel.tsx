import { useMemo, useState } from "react";
import type { ReactNode } from "react";

import type {
  ArtifactItemViewModel,
  GenerationResultData,
} from "../../types/pipeline";
import {
  buildArtifactItems,
  getArtifactStateTone,
} from "../../utils/artifactHelpers";
import { downloadArtifact } from "../../utils/downloadHelpers";
import { ArtifactCodeViewer } from "./ArtifactCodeViewer";
import { LatexViewerModal } from "./LatexViewerModal";
import { PdfPreviewPanel } from "./PdfPreviewPanel";
import { EmptyState, StatusBadge, SurfaceCard } from "./WorkflowUI";

export interface ArtifactLinksPanelProps {
  result: GenerationResultData;
  debug?: boolean;
}

export function ArtifactLinksPanel({
  result,
  debug = false,
}: ArtifactLinksPanelProps) {
  const [downloadingKind, setDownloadingKind] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [latexOpen, setLatexOpen] = useState(false);
  const [jsonOpen, setJsonOpen] = useState(false);

  const artifacts = useMemo(() => buildArtifactItems(result), [result]);
  const pdfArtifact = artifacts.find((artifact) => artifact.kind === "pdf");
  const latexArtifact = artifacts.find((artifact) => artifact.kind === "latex");
  const jsonArtifact = artifacts.find((artifact) => artifact.kind === "structured_json");
  const diagnosticsArtifact = artifacts.find((artifact) => artifact.kind === "diagnostics_bundle");

  async function handleDownload(artifact: ArtifactItemViewModel) {
    if (!artifact.download_url) {
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
    <SurfaceCard
      aria-label="Artifacts"
      style={{
        display: "grid",
        gap: 12,
      }}
    >
      <div>
        <h3 style={{ marginTop: 0 }}>Artifacts</h3>
        <p className="rg-muted" style={{ marginBottom: 0 }}>
          Artifact access is tracked per run. Missing artifacts are shown explicitly instead of assuming a full output set.
        </p>
      </div>

      {artifacts.every((artifact) => artifact.state === "unavailable") ? (
        <EmptyState
          title="No downloadable artifacts available"
          description="This run returned no downloadable outputs. Structured data or diagnostics may still be present in debug mode."
        />
      ) : null}

      <ArtifactRow
        artifact={pdfArtifact}
        downloading={downloadingKind === "pdf"}
        primaryActions={
          <>
            <button
              className="rg-button"
              type="button"
              disabled={!pdfArtifact?.download_url || downloadingKind === "pdf"}
              onClick={() => pdfArtifact && void handleDownload(pdfArtifact)}
            >
              {downloadingKind === "pdf" ? "Downloading..." : "Download PDF"}
            </button>
            <button
              className="rg-button"
              type="button"
              disabled={!pdfArtifact?.preview_url}
              onClick={() => setPreviewOpen(true)}
            >
              Preview PDF
            </button>
          </>
        }
      />

      <ArtifactRow
        artifact={latexArtifact}
        downloading={downloadingKind === "latex"}
        primaryActions={
          <>
            <button
              className="rg-button"
              type="button"
              disabled={!latexArtifact?.preview_url}
              onClick={() => setLatexOpen(true)}
            >
              View LaTeX
            </button>
            <button
              className="rg-button"
              type="button"
              disabled={!latexArtifact?.download_url || downloadingKind === "latex"}
              onClick={() => latexArtifact && void handleDownload(latexArtifact)}
            >
              {downloadingKind === "latex" ? "Downloading..." : "Download source"}
            </button>
          </>
        }
      />

      <ArtifactRow
        artifact={jsonArtifact}
        downloading={downloadingKind === "structured_json"}
        primaryActions={
          <>
            <button
              className="rg-button"
              type="button"
              disabled={!jsonArtifact?.preview_url || !debug}
              onClick={() => setJsonOpen(true)}
            >
              View JSON
            </button>
            <button
              className="rg-button"
              type="button"
              disabled={!jsonArtifact?.download_url || downloadingKind === "structured_json"}
              onClick={() => jsonArtifact && void handleDownload(jsonArtifact)}
            >
              {downloadingKind === "structured_json" ? "Downloading..." : "Download JSON"}
            </button>
          </>
        }
      />

      <ArtifactRow
        artifact={diagnosticsArtifact}
        downloading={downloadingKind === "diagnostics_bundle"}
        primaryActions={
          <button
            className="rg-button"
            type="button"
            disabled={!diagnosticsArtifact?.download_url || downloadingKind === "diagnostics_bundle"}
            onClick={() => diagnosticsArtifact && void handleDownload(diagnosticsArtifact)}
          >
            {downloadingKind === "diagnostics_bundle" ? "Downloading..." : "Download diagnostics"}
          </button>
        }
      />

      <PdfPreviewPanel
        title="PDF preview"
        sourceUrl={pdfArtifact?.preview_url}
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        previewSupported
      />
      <LatexViewerModal
        artifact={latexArtifact}
        runId={result.run_metadata.run_id}
        open={latexOpen}
        onClose={() => setLatexOpen(false)}
      />
      <ArtifactCodeViewer
        title="Structured JSON"
        url={jsonArtifact?.preview_url}
        open={jsonOpen}
        onClose={() => setJsonOpen(false)}
      />
    </SurfaceCard>
  );
}

function ArtifactRow({
  artifact,
  primaryActions,
  downloading,
}: {
  artifact?: ArtifactItemViewModel;
  primaryActions: ReactNode;
  downloading: boolean;
}) {
  return (
    <article
      style={{
        padding: 12,
        border: "1px solid var(--rg-border)",
        borderRadius: 10,
        background: "var(--rg-surface-muted)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <strong>{artifact?.label ?? "Unknown artifact"}</strong>
          <div style={{ marginTop: 6 }}>
            <StatusBadge
              tone={
                downloading
                  ? "default"
                  : getArtifactStateTone(artifact?.state ?? "unavailable")
              }
            >
              {downloading ? "downloading" : artifact?.state ?? "unavailable"}
            </StatusBadge>
          </div>
        </div>
        <div className="rg-actions">{primaryActions}</div>
      </div>
      <p className="rg-muted" style={{ margin: "8px 0 0" }}>{artifact?.message ?? "Artifact not available for this run."}</p>
      {artifact?.file_name ? (
        <p className="rg-muted" style={{ margin: "6px 0 0" }}>
          File name: {artifact.file_name}
        </p>
      ) : null}
    </article>
  );
}
