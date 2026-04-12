import { useEffect, useState } from "react";

import { downloadArtifact } from "../../utils/downloadHelpers";
import type { ArtifactItemViewModel } from "../../types/pipeline";
import { ModalShell } from "./WorkflowUI";

export interface LatexViewerModalProps {
  artifact?: ArtifactItemViewModel;
  runId: string;
  open: boolean;
  onClose: () => void;
}

export function LatexViewerModal({
  artifact,
  runId,
  open,
  onClose,
}: LatexViewerModalProps) {
  const [content, setContent] = useState<string>("Loading...");
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }

    if (!artifact?.preview_url) {
      setContent("Preview is unavailable for this artifact.");
      return;
    }

    let active = true;
    setContent("Loading...");

    void fetch(artifact.preview_url)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Preview failed with HTTP ${response.status}`);
        }
        return response.text();
      })
      .then((text) => {
        if (active) {
          setContent(text || "No LaTeX content returned.");
        }
      })
      .catch((error) => {
        if (active) {
          setContent(error instanceof Error ? error.message : "Failed to load LaTeX source.");
        }
      });

    return () => {
      active = false;
    };
  }, [artifact?.preview_url, open]);

  async function handleCopy() {
    if (typeof navigator === "undefined" || !navigator.clipboard) {
      return;
    }

    await navigator.clipboard.writeText(content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  async function handleDownload() {
    if (!artifact?.download_url) {
      return;
    }

    setDownloading(true);
    try {
      await downloadArtifact(artifact, runId);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <ModalShell
      title="LaTeX source"
      subtitle={
        artifact?.preview_url
          ? "Read-only source view for the current run. Copy or download the source if you need to inspect or compile it outside the UI."
          : "LaTeX source was not returned for this run."
      }
      open={open}
      onClose={onClose}
      width="min(1100px, 100%)"
      actions={
        <>
          <button className="rg-button" type="button" onClick={() => void handleCopy()} disabled={!artifact?.preview_url}>
            {copied ? "Copied" : "Copy to clipboard"}
          </button>
          <button className="rg-button" type="button" onClick={() => void handleDownload()} disabled={!artifact?.download_url || downloading}>
            {downloading ? "Downloading..." : "Download source"}
          </button>
        </>
      }
    >
      <pre
        style={{
          margin: 0,
          padding: 16,
          overflow: "auto",
          minHeight: 280,
          borderRadius: 12,
          background: "var(--rg-surface-muted)",
        }}
      >
        {content}
      </pre>
    </ModalShell>
  );
}
