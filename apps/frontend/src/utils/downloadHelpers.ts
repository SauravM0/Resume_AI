import type { ArtifactItemViewModel } from "../types/pipeline";

export function inferDownloadFileName(
  runId: string,
  artifact: Pick<ArtifactItemViewModel, "kind" | "file_name" | "content_type" | "download_url">,
): string {
  if (artifact.file_name) {
    return artifact.file_name;
  }

  const extension = inferFileExtension(artifact.content_type, artifact.download_url, artifact.kind);
  return `${runId}.${artifact.kind}${extension ? `.${extension}` : ""}`;
}

export async function downloadArtifact(
  artifact: Pick<ArtifactItemViewModel, "download_url" | "file_name" | "kind" | "content_type">,
  runId: string,
): Promise<void> {
  if (!artifact.download_url) {
    return;
  }

  const response = await fetch(artifact.download_url);
  if (!response.ok) {
    throw new Error(`Download failed with HTTP ${response.status}`);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = inferDownloadFileName(runId, {
    ...artifact,
    file_name: artifact.file_name || "",
  });
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

function inferFileExtension(
  contentType?: string,
  downloadUrl?: string,
  kind?: string,
): string {
  if (contentType === "application/pdf") {
    return "pdf";
  }
  if (contentType === "application/json") {
    return "json";
  }
  if (contentType?.includes("latex") || kind === "latex") {
    return "tex";
  }

  const fromUrl = downloadUrl?.split("?")[0].split(".").pop();
  return fromUrl && fromUrl.length <= 5 ? fromUrl : "";
}
