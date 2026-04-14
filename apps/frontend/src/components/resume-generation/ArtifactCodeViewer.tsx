import { useEffect, useState } from "react";
import { ModalShell } from "./WorkflowUI";

export interface ArtifactCodeViewerProps {
  title: string;
  url?: string;
  open: boolean;
  onClose: () => void;
}

export function ArtifactCodeViewer({
  title,
  url,
  open,
  onClose,
}: ArtifactCodeViewerProps) {
  const [content, setContent] = useState<string>("Loading...");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open || !url) {
      return;
    }

    let active = true;
    setContent("Loading...");

    void fetch(url)
      .then((response) => response.text())
      .then((text) => {
        if (active) {
          setContent(text || "No content returned.");
        }
      })
      .catch((error) => {
        if (active) {
          setContent(error instanceof Error ? error.message : "Failed to load artifact.");
        }
      });

    return () => {
      active = false;
    };
  }, [open, url]);

  async function handleCopy() {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <ModalShell
      title={title}
      subtitle={
        url
          ? "This viewer is read-only. Use copy or download actions if you need the underlying artifact outside the UI."
          : "This artifact is not available for preview in the current run."
      }
      open={open}
      onClose={onClose}
      actions={
        <button className="rg-button" type="button" onClick={() => void handleCopy()} disabled={!url}>
          {copied ? "Copied" : "Copy"}
        </button>
      }
    >
      <pre
        style={{
          margin: 0,
          padding: 16,
          overflow: "auto",
          minHeight: 240,
          background: "var(--rg-surface-muted)",
        }}
      >
        {url ? content : "Preview is unavailable for this artifact."}
      </pre>
    </ModalShell>
  );
}
