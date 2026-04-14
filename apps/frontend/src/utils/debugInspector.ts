import type {
  GenerationResultData,
  ResumeGenerationState,
} from "../types/pipeline";
import { getElapsedSeconds } from "./timingFormatters";

type Primitive = string | number | boolean | null | undefined;

export interface JobAnalysisDebugData {
  roleType?: string;
  seniority?: string;
  technicalSkills: string[];
  softSkills: string[];
  mustHaveRequirements: string[];
  niceToHaveRequirements: string[];
  actionVerbs: string[];
  domainSignals: string[];
}

export interface EvidenceSelectionDebugData {
  matchingKeywords: string[];
  excludedExperiences: string[];
  excludedProjects: string[];
  excludedSkills: string[];
}

export interface VerificationDebugData {
  verificationStatus?: string;
  unsupportedClaims: string[];
  semanticResults: string[];
}

export interface RenderArtifactDebugData {
  templateName?: string;
  templateVersion?: string;
  pageTarget?: string;
  renderWarnings: string[];
  pdfMetadata: Array<{ label: string; value: string }>;
  latexAvailable: boolean;
  compilerSummary?: string;
}

export interface RawRunMetadataDebugData {
  runId?: string;
  endpoint: string;
  startedAt?: string;
  finishedAt?: string;
  durationSeconds?: number;
  retryCount: number;
  phaseTransitions: Array<{ timestamp?: string; phase: string; eventType: string; message: string }>;
}

export function buildJobAnalysisDebugData(state: ResumeGenerationState): JobAnalysisDebugData {
  const sources = collectInspectorSources(state);

  return {
    roleType: findFirstString(sources, ["detected_role", "role_type", "role", "target_role"]),
    seniority: findFirstString(sources, ["seniority", "seniority_level", "level"]),
    technicalSkills: findStringList(sources, ["technical_skills", "hard_skills", "skills", "required_skills"]),
    softSkills: findStringList(sources, ["soft_skills", "behavioral_skills", "people_skills"]),
    mustHaveRequirements: findStringList(sources, ["must_have_requirements", "must_haves", "required_requirements", "requirements"]),
    niceToHaveRequirements: findStringList(sources, ["nice_to_have_requirements", "nice_to_haves", "preferred_requirements", "preferred_skills"]),
    actionVerbs: findStringList(sources, ["action_verbs", "verbs"]),
    domainSignals: findStringList(sources, ["domain_signals", "culture_signals", "culture_values", "domain_keywords"]),
  };
}

export function buildEvidenceSelectionDebugData(state: ResumeGenerationState): EvidenceSelectionDebugData {
  const sources = collectInspectorSources(state);

  return {
    matchingKeywords: findStringList(sources, ["matching_keywords", "matched_keywords", "keywords"]),
    excludedExperiences: findStringList(sources, ["excluded_experiences", "dropped_experiences"]),
    excludedProjects: findStringList(sources, ["excluded_projects", "dropped_projects"]),
    excludedSkills: findStringList(sources, ["excluded_skills", "dropped_skills"]),
  };
}

export function buildVerificationDebugData(state: ResumeGenerationState): VerificationDebugData {
  const sources = collectInspectorSources(state);

  return {
    verificationStatus: findFirstString(sources, ["verification_status", "verification_result", "status"]),
    unsupportedClaims: findStringList(sources, ["unsupported_claims", "claim_failures", "unsupported_facts"]),
    semanticResults: findStringList(sources, ["semantic_verification_results", "semantic_results", "semantic_checks"]),
  };
}

export function buildRenderArtifactDebugData(state: ResumeGenerationState): RenderArtifactDebugData {
  const result = state.result;
  const sources = collectInspectorSources(state);
  const pdfOutput = result?.downloadable_outputs.find((output) => output.kind === "pdf");
  const pdfArtifact = result?.render_artifacts.find((artifact) => artifact.kind === "pdf");
  const compileLog = result?.render_artifacts.find((artifact) => artifact.kind === "compile_log");

  return {
    templateName:
      result?.run_metadata.template_id ??
      findFirstString(sources, ["template_id", "template_name"]),
    templateVersion: findFirstString(sources, ["template_version", "version"]),
    pageTarget: findPageTarget(result),
    renderWarnings: findStringList(sources, ["render_warnings", "compiler_warnings", "warnings"]),
    pdfMetadata: [
      pdfOutput?.reference ? { label: "PDF reference", value: pdfOutput.reference } : undefined,
      pdfOutput?.content_type ? { label: "PDF content type", value: pdfOutput.content_type } : undefined,
      pdfArtifact?.sha256 ? { label: "PDF SHA-256", value: pdfArtifact.sha256 } : undefined,
      pdfArtifact?.size_bytes ? { label: "PDF size", value: `${pdfArtifact.size_bytes} bytes` } : undefined,
    ].flatMap((item) => (item ? [item] : [])),
    latexAvailable: Boolean(
      result?.downloadable_outputs.some((output) => output.kind === "latex_document") ||
        result?.render_artifacts.some((artifact) => artifact.kind === "latex_document"),
    ),
    compilerSummary:
      compileLog?.uri ??
      findFirstString(sources, ["compiler_output_summary", "compile_summary", "compile_log"]),
  };
}

export function buildRawRunMetadataDebugData(state: ResumeGenerationState): RawRunMetadataDebugData {
  const events = state.progress?.events ?? [];
  const startedAt = state.run?.started_at ?? events[0]?.timestamp;
  const finishedAt = state.run?.finished_at ?? events[events.length - 1]?.timestamp;
  const retryEventsCount = state.progress?.retry_notices.length ?? 0;
  const stageRetryCount = Math.max(
    0,
    ...(state.progress?.stages.map((stage) => Math.max(0, (stage.attempt_number ?? 1) - 1)) ?? [0]),
  );

  return {
    runId: state.run?.run_id ?? state.result?.run_metadata.run_id ?? state.error?.run_id,
    endpoint: "/api/generate-resume",
    startedAt,
    finishedAt,
    durationSeconds: getElapsedSeconds(startedAt, finishedAt),
    retryCount: Math.max(retryEventsCount, stageRetryCount),
    phaseTransitions: events.map((event) => ({
      timestamp: event.timestamp,
      phase: event.stage_name ?? "run",
      eventType: event.event_type,
      message: event.human_message,
    })),
  };
}

export function collectInspectorSources(state: ResumeGenerationState): unknown[] {
  return [
    state.result?.raw_response,
    state.result?.raw_response.run_metadata,
    state.result?.diagnostics?.metadata,
    state.result?.diagnostics,
    ...(state.result?.raw_response.stage_events ?? []),
    ...(state.progress?.events.map((event) => event.metadata) ?? []),
    ...((state.result?.render_artifacts.map((artifact) => artifact.metadata) ?? []) as Array<Record<string, unknown> | undefined>),
    state.error?.metadata,
    state.error?.diagnostics?.metadata,
  ].filter((value) => value !== undefined);
}

function findPageTarget(result: GenerationResultData | null): string | undefined {
  const runMetadata = result?.raw_response.run_metadata as Record<string, unknown> | undefined;
  const generationPreferences = runMetadata?.generation_preferences as Record<string, unknown> | undefined;
  const pageLength = runMetadata?.page_length_pages ?? generationPreferences?.page_length_pages;
  if (pageLength === 2 || pageLength === "2") {
    return "2 pages";
  }
  if (pageLength === 1 || pageLength === "1") {
    return "1 page";
  }
  return undefined;
}

function findFirstString(sources: unknown[], keys: string[]): string | undefined {
  for (const source of sources) {
    const value = findValueByKeys(source, keys);
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  return undefined;
}

function findStringList(sources: unknown[], keys: string[]): string[] {
  for (const source of sources) {
    const value = findValueByKeys(source, keys);
    const normalized = normalizeStringList(value);
    if (normalized.length > 0) {
      return normalized;
    }
  }
  return [];
}

function findValueByKeys(source: unknown, keys: string[]): unknown {
  const visited = new Set<unknown>();
  const queue: unknown[] = [source];
  const normalizedKeys = new Set(keys.map((key) => key.toLowerCase()));

  while (queue.length > 0) {
    const current = queue.shift();
    if (!current || typeof current !== "object" || visited.has(current)) {
      continue;
    }
    visited.add(current);

    if (Array.isArray(current)) {
      for (const item of current) {
        queue.push(item);
      }
      continue;
    }

    for (const [key, value] of Object.entries(current as Record<string, unknown>)) {
      if (normalizedKeys.has(key.toLowerCase())) {
        return value;
      }
      if (value && typeof value === "object") {
        queue.push(value);
      }
    }
  }

  return undefined;
}

function normalizeStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => normalizeStringList(item));
  }
  if (typeof value === "string" && value.trim()) {
    return [value];
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return [String(value)];
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if ("name" in record && isPrimitive(record.name)) {
      return normalizeStringList(record.name);
    }
    if ("label" in record && isPrimitive(record.label)) {
      return normalizeStringList(record.label);
    }
    return Object.entries(record).flatMap(([key, nestedValue]) => {
      if (isPrimitive(nestedValue)) {
        return typeof nestedValue === "string" && nestedValue.trim()
          ? [`${key}: ${nestedValue}`]
          : [];
      }
      return [];
    });
  }
  return [];
}

function isPrimitive(value: unknown): value is Primitive {
  return value === null || ["string", "number", "boolean", "undefined"].includes(typeof value);
}
