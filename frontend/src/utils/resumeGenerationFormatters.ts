import { PIPELINE_STAGE_LABELS, RUN_STATUS_LABELS } from "../constants/resumeGeneration";
import type {
  BackendErrorPayload,
  DownloadableOutput,
  FallbackRepairMetadata,
  GenerationResultData,
  PhaseStatus,
  PipelineStageName,
  PipelineOverallStatus,
  ResumeGenerationRunStatus,
  SelectedExperience,
  SelectedProject,
  SelectedSkill,
} from "../types/pipeline";

export function formatRunStatus(status: ResumeGenerationRunStatus): string {
  return RUN_STATUS_LABELS[status];
}

export function formatStageName(stageName?: PipelineStageName | string): string {
  if (!stageName) {
    return "Unknown stage";
  }
  return stageName in PIPELINE_STAGE_LABELS
    ? PIPELINE_STAGE_LABELS[stageName as PipelineStageName]
    : stageName.replaceAll("_", " ");
}

export function formatOutputLabel(output: DownloadableOutput): string {
  return output.label ?? output.file_name ?? output.kind.replaceAll("_", " ");
}

export function getPrimaryOutput(result: GenerationResultData | null): DownloadableOutput | undefined {
  if (!result) {
    return undefined;
  }
  return (
    result.downloadable_outputs.find((output) => output.kind === "pdf") ??
    result.downloadable_outputs.at(0)
  );
}

export function describePhase(stage: PhaseStatus | null | undefined): string {
  if (!stage) {
    return "No active stage";
  }
  const label = formatStageName(stage.stage_name);
  if (stage.progress_percent === undefined) {
    return `${label} (${stage.machine_status})`;
  }
  return `${label} (${stage.machine_status}, ${stage.progress_percent}%)`;
}

export function describeError(error: BackendErrorPayload | null): string {
  if (!error) {
    return "No error";
  }
  const stage = error.stage_name ? ` at ${formatStageName(error.stage_name)}` : "";
  return `${error.message}${stage}`;
}

export function formatPipelineOutcome(status: PipelineOverallStatus): string {
  if (status === "succeeded_with_warnings") {
    return "Success with warnings";
  }
  if (status === "succeeded") {
    return "Success";
  }
  if (status === "blocked") {
    return "Blocked";
  }
  if (status === "failed") {
    return "Failed";
  }
  if (status === "running") {
    return "Running";
  }
  return "Queued";
}

export function summarizeSelectionItem(
  item: SelectedExperience | SelectedProject | SelectedSkill,
): string {
  if ("company" in item) {
    return [item.title, item.company].filter(Boolean).join(" at ");
  }
  if ("name" in item) {
    return item.name ?? item.id;
  }
  return ("title" in item ? item.title : undefined) ?? item.id;
}

export function countMeaningfulWarnings(result: GenerationResultData): number {
  return result.verification_warnings.length + (result.diagnostics?.warnings.length ?? 0);
}

export function hasFallbackUsage(fallbackRepairs: FallbackRepairMetadata[] | undefined): boolean {
  return Boolean(fallbackRepairs?.some((item) => item.applied));
}

export function deriveResultTrustLabel(result: GenerationResultData): string {
  const warnings = countMeaningfulWarnings(result);
  const fallbackUsed = hasFallbackUsage(result.diagnostics?.fallback_repairs);

  if (result.overall_status === "succeeded" && warnings === 0 && !fallbackUsed) {
    return "Fully trusted";
  }

  if (result.downloadable_outputs.some((output) => output.kind === "pdf")) {
    return "Needs review";
  }

  return "Partially complete";
}

export function inferGeneratedPageLength(result: GenerationResultData): string {
  const runMetadata = result.raw_response.run_metadata as Record<string, unknown> | undefined;
  const generationPreferences = runMetadata?.generation_preferences as Record<string, unknown> | undefined;
  const configuredValue = runMetadata?.page_length_pages ?? generationPreferences?.page_length_pages;
  if (configuredValue === 2 || configuredValue === "2") {
    return "2 pages";
  }
  return "1 page";
}

export function inferDetectedRole(result: GenerationResultData): string | undefined {
  const runMetadata = result.raw_response.run_metadata as Record<string, unknown> | undefined;
  const candidateValues = [
    runMetadata?.detected_role,
    runMetadata?.resume_title,
    result.selected_experiences.at(0)?.title,
  ];

  const detected = candidateValues.find((value) => typeof value === "string" && value.trim().length > 0);
  return typeof detected === "string" ? detected : undefined;
}
