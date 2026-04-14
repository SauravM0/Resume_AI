import { ModalShell } from "./WorkflowUI";

export interface PdfPreviewPanelProps {
  title?: string;
  sourceUrl?: string;
  open: boolean;
  onClose: () => void;
  previewSupported: boolean;
  downloadLabel?: string;
  onDownload?: () => void;
  downloading?: boolean;
}

export function PdfPreviewPanel({
  title = "PDF preview",
  sourceUrl,
  open,
  onClose,
  previewSupported,
  downloadLabel = "Download PDF",
  onDownload,
  downloading = false,
}: PdfPreviewPanelProps) {
  const showInlinePreview = Boolean(sourceUrl && previewSupported);

  return (
    <ModalShell
      title={title}
      subtitle={
        showInlinePreview
          ? "Browser preview depends on local PDF support. If the preview is blank, download the file directly."
          : "Inline preview is unavailable in this browser context or for this run. Use the download action instead."
      }
      open={open}
      onClose={onClose}
      width="min(1100px, 100%)"
      actions={
        onDownload ? (
          <button className="rg-button" type="button" onClick={onDownload} disabled={downloading}>
            {downloading ? "Downloading..." : downloadLabel}
          </button>
        ) : undefined
      }
    >
      {showInlinePreview ? (
        <iframe
          title={title}
          src={sourceUrl}
          style={{ width: "100%", height: "min(72vh, 820px)", border: 0, background: "#ffffff" }}
        />
      ) : (
        <div
          style={{
            display: "grid",
            gap: 12,
            padding: 16,
            borderRadius: 12,
            background: "var(--rg-surface-muted)",
          }}
        >
          <p style={{ margin: 0 }}>
            PDF preview is not available here. This can happen when the browser blocks inline PDF display or when the run did not
            return a previewable URL.
          </p>
          {sourceUrl ? (
            <p className="rg-muted" style={{ margin: 0 }}>
              A source URL exists for this artifact, so direct download should still work.
            </p>
          ) : (
            <p className="rg-muted" style={{ margin: 0 }}>
              No preview URL was returned for this run.
            </p>
          )}
        </div>
      )}
    </ModalShell>
  );
}
