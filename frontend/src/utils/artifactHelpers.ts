import type {
  ArtifactItemViewModel,
  DownloadableOutput,
  GenerationResultData,
  RenderArtifact,
} from "../types/pipeline";
import { inferDownloadFileName } from "./downloadHelpers";

export interface RunArtifactCollection {
  pdf: ArtifactItemViewModel;
  latex: ArtifactItemViewModel;
  structuredJson: ArtifactItemViewModel;
  diagnostics: ArtifactItemViewModel;
  items: ArtifactItemViewModel[];
}

export function getOutputByKind(
  result: GenerationResultData,
  kind: string,
): DownloadableOutput | undefined {
  return result.downloadable_outputs.find((output) => output.kind === kind);
}

export function getArtifactByKind(
  result: GenerationResultData,
  kind: string,
): RenderArtifact | undefined {
  return result.render_artifacts.find((artifact) => artifact.kind === kind);
}

export function getStructuredResultLink(result: GenerationResultData): string | undefined {
  return (
    getOutputByKind(result, "structured_json")?.reference ??
    getArtifactByKind(result, "phase3_result")?.uri ??
    getArtifactByKind(result, "pipeline_result")?.uri
  );
}

export function getLatexLink(result: GenerationResultData): string | undefined {
  return getOutputByKind(result, "latex_document")?.reference ?? getArtifactByKind(result, "latex_document")?.uri;
}

export function getDebugLinks(result: GenerationResultData): DownloadableOutput[] {
  return result.downloadable_outputs.filter((output) =>
    ["compile_log", "structured_json", "debug", "verification_report"].includes(output.kind),
  );
}

export function buildArtifactItems(result: GenerationResultData): ArtifactItemViewModel[] {
  return [
    buildPdfArtifact(result),
    buildLatexArtifact(result),
    buildStructuredJsonArtifact(result),
    buildDiagnosticsArtifact(result),
  ];
}

export function buildRunArtifactCollection(result: GenerationResultData): RunArtifactCollection {
  const items = buildArtifactItems(result);

  return {
    pdf: items.find((artifact) => artifact.kind === "pdf") ?? buildUnavailableArtifact("pdf", "PDF"),
    latex: items.find((artifact) => artifact.kind === "latex") ?? buildUnavailableArtifact("latex", "LaTeX source"),
    structuredJson:
      items.find((artifact) => artifact.kind === "structured_json") ?? buildUnavailableArtifact("structured_json", "Structured JSON"),
    diagnostics:
      items.find((artifact) => artifact.kind === "diagnostics_bundle") ?? buildUnavailableArtifact("diagnostics_bundle", "Diagnostics"),
    items,
  };
}

export function isArtifactActionable(artifact?: ArtifactItemViewModel | null): boolean {
  return Boolean(artifact && artifact.state !== "unavailable" && artifact.state !== "failed");
}

export function canDownloadArtifact(artifact?: ArtifactItemViewModel | null): boolean {
  return Boolean(artifact?.download_url);
}

export function canPreviewArtifact(artifact?: ArtifactItemViewModel | null): boolean {
  return Boolean(artifact?.preview_url);
}

export function canInlinePreviewPdf(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof document !== "undefined" &&
    typeof URL !== "undefined" &&
    typeof URL.createObjectURL === "function"
  );
}

export function getArtifactStateTone(
  state: ArtifactItemViewModel["state"] | "downloading",
): "muted" | "success" | "warning" | "danger" | "default" {
  if (state === "downloading") {
    return "default";
  }
  if (state === "available") {
    return "success";
  }
  if (state === "partial") {
    return "warning";
  }
  if (state === "failed") {
    return "danger";
  }
  return "muted";
}

function buildPdfArtifact(result: GenerationResultData): ArtifactItemViewModel {
  const output = getOutputByKind(result, "pdf");
  const artifact = getArtifactByKind(result, "pdf");
  const failedCompile = result.render_artifacts.some((item) => item.kind === "compile_log") && !output;

  return {
    kind: "pdf",
    label: "PDF",
    state: output ? "available" : failedCompile ? "failed" : "unavailable",
    download_url: output?.reference ?? artifact?.uri,
    preview_url: output?.preview_reference ?? output?.reference ?? artifact?.uri,
    file_name: output?.file_name ?? inferDownloadFileName(result.run_metadata.run_id, {
      kind: "pdf",
      file_name: "resume.pdf",
      content_type: output?.content_type ?? artifact?.content_type,
      download_url: output?.reference ?? artifact?.uri,
    }),
    content_type: output?.content_type ?? artifact?.content_type ?? "application/pdf",
    size_bytes: output?.size_bytes ?? artifact?.size_bytes,
    message: output
      ? "PDF is ready for download."
      : failedCompile
        ? "PDF generation failed for this run."
        : "PDF is not available for this run.",
    source: output ? "output" : artifact?.uri ? "artifact" : "derived",
  };
}

function buildLatexArtifact(result: GenerationResultData): ArtifactItemViewModel {
  const output = getOutputByKind(result, "latex_document");
  const artifact = getArtifactByKind(result, "latex_document");
  const state = output || artifact ? "available" : result.downloadable_outputs.length > 0 ? "partial" : "unavailable";

  return {
    kind: "latex",
    label: "LaTeX source",
    state,
    download_url: output?.reference ?? artifact?.uri,
    preview_url: output?.reference ?? artifact?.uri,
    file_name: output?.file_name ?? "resume.tex",
    content_type: output?.content_type ?? artifact?.content_type ?? "application/x-tex",
    size_bytes: output?.size_bytes ?? artifact?.size_bytes,
    message:
      output || artifact
        ? "LaTeX source is available."
        : state === "partial"
          ? "This run produced outputs, but LaTeX source was not returned."
          : "LaTeX source is not available for this run.",
    source: output ? "output" : artifact?.uri ? "artifact" : "derived",
  };
}

function buildStructuredJsonArtifact(result: GenerationResultData): ArtifactItemViewModel {
  const output = getOutputByKind(result, "structured_json");
  const artifact = getArtifactByKind(result, "phase3_result") ?? getArtifactByKind(result, "pipeline_result");
  const pdfFailedButJsonAvailable = !getOutputByKind(result, "pdf") && Boolean(output || artifact);

  return {
    kind: "structured_json",
    label: "Structured JSON",
    state: output || artifact ? (pdfFailedButJsonAvailable ? "partial" : "available") : "unavailable",
    download_url: output?.reference ?? artifact?.uri,
    preview_url: output?.reference ?? artifact?.uri,
    file_name: output?.file_name ?? "structured-result.json",
    content_type: output?.content_type ?? artifact?.content_type ?? "application/json",
    size_bytes: output?.size_bytes ?? artifact?.size_bytes,
    message:
      output || artifact
        ? pdfFailedButJsonAvailable
          ? "Structured output is available even though final PDF output is incomplete."
          : "Structured output is available."
        : "Structured output is not available for this run.",
    source: output ? "output" : artifact?.uri ? "artifact" : "derived",
  };
}

function buildDiagnosticsArtifact(result: GenerationResultData): ArtifactItemViewModel {
  const output =
    getOutputByKind(result, "diagnostics_bundle") ??
    getOutputByKind(result, "compile_log") ??
    getOutputByKind(result, "verification_report");
  const artifact = getArtifactByKind(result, "compile_log") ?? getArtifactByKind(result, "verification_report");
  const hasAnyDiagnostics = Boolean(output || artifact || result.diagnostics);

  return {
    kind: "diagnostics_bundle",
    label: "Diagnostics bundle",
    state: hasAnyDiagnostics ? "available" : "unavailable",
    download_url: output?.reference ?? artifact?.uri,
    preview_url: output?.reference ?? artifact?.uri,
    file_name: output?.file_name ?? "diagnostics.json",
    content_type: output?.content_type ?? artifact?.content_type ?? "application/json",
    size_bytes: output?.size_bytes ?? artifact?.size_bytes,
    message: hasAnyDiagnostics ? "Diagnostics output is available." : "No diagnostics bundle is available for this run.",
    source: output ? "output" : artifact?.uri ? "artifact" : "derived",
  };
}

function buildUnavailableArtifact(
  kind: ArtifactItemViewModel["kind"],
  label: string,
): ArtifactItemViewModel {
  return {
    kind,
    label,
    state: "unavailable",
    file_name: "",
    message: `${label} is not available for this run.`,
    source: "derived",
  };
}
