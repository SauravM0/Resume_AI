import type {
  BackendErrorPayload,
  DownloadableOutput,
  FallbackRepairMetadata,
  GenerateResumeRequest,
  GenerateResumeResponse,
  RenderArtifact,
  RunDiagnostics,
  VerificationWarning,
} from "../types/pipeline";

const GENERATE_RESUME_ENDPOINT = "/api/generate-resume";

export interface GenerateResumeOptions {
  baseUrl?: string;
  signal?: AbortSignal;
}

export async function generateResume(
  request: GenerateResumeRequest,
  options: GenerateResumeOptions = {},
): Promise<GenerateResumeResponse> {
  const baseUrl = options.baseUrl ?? "";
  const response = await fetch(`${baseUrl}${GENERATE_RESUME_ENDPOINT}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    signal: options.signal,
  });

  const payload = await readJson(response);
  if (!response.ok) {
    throw normalizeGenerateResumeError(payload, response.status);
  }

  return normalizeGenerateResumeResponse(payload, request);
}

export function createPipelineRunId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `run.${crypto.randomUUID()}`;
  }
  return `run.${Date.now()}.${Math.random().toString(16).slice(2)}`;
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

export function normalizeGenerateResumeResponse(
  payload: unknown,
  request: GenerateResumeRequest,
): GenerateResumeResponse {
  const record = isRecord(payload) ? payload : {};
  const artifactManifest = normalizeArtifactManifest(record);
  const availableOutputs = normalizeAvailableOutputs(record, artifactManifest);
  const warnings = normalizeStringList(record.warnings);
  const verificationWarnings = normalizeVerificationWarnings(record.verification_warnings);
  const fallbackRepairs = normalizeFallbackRepairs(record.fallback_repairs);
  const diagnostics = normalizeDiagnostics(record.diagnostics, {
    warnings: verificationWarnings,
    fallbackRepairs,
  });
  const runId = readString(record.run_id) ?? request.pipeline_run_id ?? createPipelineRunId();

  return {
    run_id: runId,
    status: normalizePipelineStatus(readString(record.status)),
    available_outputs: availableOutputs,
    warnings,
    final_file_reference: readString(record.final_file_reference),
    artifact_manifest: artifactManifest,
    stage_events: Array.isArray(record.stage_events) ? record.stage_events.filter(isRecord) : [],
    diagnostics,
    selected_experiences: Array.isArray(record.selected_experiences)
      ? record.selected_experiences.filter(isRecord).map((item, index) => ({
          id: readString(item.id) ?? `experience-${index}`,
          title: readString(item.title),
          company: readString(item.company),
          summary: readString(item.summary),
          score: readNumber(item.score),
          rationale: readString(item.rationale),
          evidence: normalizeStringList(item.evidence),
          metadata: item,
        }))
      : [],
    selected_projects: Array.isArray(record.selected_projects)
      ? record.selected_projects.filter(isRecord).map((item, index) => ({
          id: readString(item.id) ?? `project-${index}`,
          name: readString(item.name),
          summary: readString(item.summary),
          score: readNumber(item.score),
          rationale: readString(item.rationale),
          evidence: normalizeStringList(item.evidence),
          metadata: item,
        }))
      : [],
    selected_skills: Array.isArray(record.selected_skills)
      ? record.selected_skills.filter(isRecord).map((item, index) => ({
          id: readString(item.id) ?? `skill-${index}`,
          name: readString(item.name) ?? `Skill ${index + 1}`,
          category: readString(item.category),
          score: readNumber(item.score),
          rationale: readString(item.rationale),
          metadata: item,
        }))
      : [],
    verification_warnings: verificationWarnings,
    fallback_repairs: fallbackRepairs,
    run_metadata: {
      run_id: runId,
      source_profile_id: request.source_profile_id,
      source_profile_path: request.source_profile_path,
      template_id: request.template_id,
      render_job_id: request.render_job_id,
      frontend_correlation_id: request.frontend_correlation_id,
    },
  };
}

export function normalizeGenerateResumeError(
  payload: unknown,
  statusCode: number,
): BackendErrorPayload {
  if (isRecord(payload)) {
    const detail = isRecord(payload.detail) ? payload.detail : payload;
    const warnings = normalizeVerificationWarnings(detail.warnings);
    const fallbackRepairs = normalizeFallbackRepairs(detail.fallback_repairs);
    return {
      message: readString(detail.message) ?? readString(payload.message) ?? "Resume generation failed.",
      failure_type: readString(detail.failure_type),
      failure_category: readString(detail.failure_category),
      stage_name: readString(detail.stage_name),
      retryable: readBoolean(detail.retryable),
      fallback_eligible: readBoolean(detail.fallback_eligible),
      run_id: readString(detail.run_id),
      status_code: statusCode,
      diagnostics: {
        summary: readString(detail.message),
        failure_type: readString(detail.failure_type),
        failure_category: readString(detail.failure_category),
        retryable: readBoolean(detail.retryable),
        fallback_eligible: readBoolean(detail.fallback_eligible),
        messages: normalizeErrorMessages(detail),
        warnings,
        fallback_repairs: fallbackRepairs,
        metadata: detail,
      },
      metadata: detail,
      error_source: "backend",
    };
  }
  return {
    message: "Resume generation failed.",
    status_code: statusCode,
    error_source: "backend",
  };
}

function normalizeArtifact(artifact: Record<string, unknown>): RenderArtifact {
  return {
    artifact_id: readString(artifact.artifact_id) ?? "artifact.unknown",
    kind: readString(artifact.kind) ?? "unknown",
    stage_name: readString(artifact.stage_name) ?? "persist_artifacts",
    storage_backend: readString(artifact.storage_backend) ?? "inline",
    schema_version: readString(artifact.schema_version) ?? "unknown",
    uri: readString(artifact.uri),
    sha256: readString(artifact.sha256),
    size_bytes: readNumber(artifact.size_bytes),
    content_type: readString(artifact.content_type),
    metadata: isRecord(artifact.metadata) ? artifact.metadata : undefined,
  };
}

function normalizeArtifactManifest(record: Record<string, unknown>): RenderArtifact[] {
  return Array.isArray(record.artifact_manifest)
    ? record.artifact_manifest.filter(isRecord).map(normalizeArtifact)
    : [];
}

function normalizeAvailableOutputs(
  record: Record<string, unknown>,
  artifactManifest: RenderArtifact[],
): DownloadableOutput[] {
  const directOutputs = Array.isArray(record.available_outputs)
    ? record.available_outputs
        .filter(isRecord)
        .map((output) => ({
          kind: readString(output.kind) ?? "unknown",
          storage_kind: readString(output.storage_kind) ?? "unknown",
          reference: readString(output.reference) ?? "",
          content_type: readString(output.content_type),
          file_name: readString(output.file_name),
          label: readString(output.label),
          size_bytes: readNumber(output.size_bytes),
          preview_reference: readString(output.preview_reference),
        }))
        .filter((output) => output.reference.length > 0)
    : [];

  if (directOutputs.length > 0) {
    return directOutputs;
  }

  return artifactManifest
    .filter((artifact) => Boolean(artifact.uri))
    .map<DownloadableOutput>((artifact) => ({
      kind: artifact.kind,
      storage_kind: artifact.storage_backend,
      reference: artifact.uri ?? "",
      content_type: artifact.content_type,
      file_name: undefined,
      label: undefined,
      size_bytes: artifact.size_bytes,
      preview_reference: undefined,
    }));
}

function normalizeDiagnostics(
  value: unknown,
  extras: {
    warnings: VerificationWarning[];
    fallbackRepairs: FallbackRepairMetadata[];
  },
): RunDiagnostics | undefined {
  if (!isRecord(value)) {
    return undefined;
  }

  return {
    summary: readString(value.summary),
    failure_type: readString(value.failure_type),
    failure_category: readString(value.failure_category),
    retryable: readBoolean(value.retryable),
    fallback_eligible: readBoolean(value.fallback_eligible),
    correlation_id: readString(value.correlation_id),
    messages: normalizeStringList(value.messages),
    warnings:
      extras.warnings.length > 0
        ? extras.warnings
        : normalizeVerificationWarnings(value.warnings),
    fallback_repairs:
      extras.fallbackRepairs.length > 0
        ? extras.fallbackRepairs
        : normalizeFallbackRepairs(value.fallback_repairs),
    metadata: value,
  };
}

function normalizeVerificationWarnings(value: unknown): VerificationWarning[] {
  return Array.isArray(value)
    ? value.filter(isRecord).map((warning) => ({
        code: readString(warning.code),
        message: readString(warning.message) ?? "Verification warning",
        severity: normalizeSeverity(readString(warning.severity)),
        field: readString(warning.field),
        source: readString(warning.source),
        metadata: warning,
      }))
    : [];
}

function normalizeFallbackRepairs(value: unknown): FallbackRepairMetadata[] {
  return Array.isArray(value)
    ? value.filter(isRecord).map((repair) => ({
        stage_name: readString(repair.stage_name),
        applied: readBoolean(repair.applied) ?? true,
        strategy: readString(repair.strategy),
        reason: readString(repair.reason),
        repair_status: normalizeRepairStatus(readString(repair.repair_status)),
        operator_message: readString(repair.operator_message),
        metadata: repair,
      }))
    : [];
}

function normalizePipelineStatus(value: string | undefined): GenerateResumeResponse["status"] {
  if (
    value === "pending" ||
    value === "running" ||
    value === "succeeded" ||
    value === "succeeded_with_warnings" ||
    value === "failed" ||
    value === "blocked"
  ) {
    return value;
  }
  return "pending";
}

function normalizeSeverity(value: string | undefined): "info" | "warning" | "error" {
  if (value === "info" || value === "error") {
    return value;
  }
  return "warning";
}

function normalizeRepairStatus(
  value: string | undefined,
): "not_needed" | "attempted" | "applied" | "failed" {
  if (value === "not_needed" || value === "attempted" || value === "applied" || value === "failed") {
    return value;
  }
  return "applied";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

function readNumber(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

function readBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function normalizeStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => normalizeStringList(item));
  }
  return typeof value === "string" && value ? [value] : [];
}

function normalizeErrorMessages(detail: Record<string, unknown>): string[] {
  const messages = normalizeStringList(detail.messages);
  if (messages.length > 0) {
    return messages;
  }
  return [readString(detail.message) ?? "Resume generation failed."];
}
