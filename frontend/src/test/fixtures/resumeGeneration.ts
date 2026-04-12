import type {
  BackendErrorPayload,
  BackendHealthState,
  FallbackRepairMetadata,
  GenerateResumeRequest,
  GenerateResumeResponse,
  GenerationResultData,
  PipelineProgressEvent,
  PipelineProgressState,
  ReadinessIndicator,
  ResumeGenerationState,
  RunMetadata,
} from "../../types/pipeline";
import { createEmptyProgressState, createInitialResumeGenerationState } from "../../state/resumeGenerationState";

type DeepPartial<T> = {
  [K in keyof T]?: T[K] extends Array<infer U>
    ? Array<DeepPartial<U>>
    : T[K] extends Record<string, unknown>
      ? DeepPartial<T[K]>
      : T[K];
};

export function makeGenerateRequest(overrides: Partial<GenerateResumeRequest> = {}): GenerateResumeRequest {
  return {
    pipeline_run_id: "run.fixture",
    source_profile_path: "data/master_profile.example.json",
    job_description_text: "Senior software engineer role focused on TypeScript, React, accessibility, resume generation workflows, verification, and deterministic rendering. This posting includes responsibilities, qualifications, and collaboration expectations for a production product team.",
    job_posting_url: "https://example.com/jobs/123",
    template_id: "ats_standard",
    persist_intermediate_artifacts: true,
    generation_preferences: {
      page_length_pages: 1,
    },
    ...overrides,
  };
}

export function makeRunMetadata(overrides: Partial<RunMetadata> = {}): RunMetadata {
  return {
    run_id: "run.fixture",
    started_at: "2026-04-12T10:00:00.000Z",
    source_profile_path: "data/master_profile.example.json",
    template_id: "ats_standard",
    frontend_correlation_id: "frontend.fixture",
    ...overrides,
  };
}

export function makeGenerateResponse(overrides: DeepPartial<GenerateResumeResponse> = {}): GenerateResumeResponse {
  const base: GenerateResumeResponse = {
    run_id: "run.fixture",
    status: "succeeded",
    available_outputs: [
      {
        kind: "pdf",
        storage_kind: "url",
        reference: "https://example.com/run.fixture/resume.pdf",
        preview_reference: "https://example.com/run.fixture/resume-preview.pdf",
        file_name: "resume.pdf",
        content_type: "application/pdf",
      },
      {
        kind: "structured_json",
        storage_kind: "url",
        reference: "https://example.com/run.fixture/result.json",
        file_name: "result.json",
        content_type: "application/json",
      },
    ],
    warnings: [],
    final_file_reference: "https://example.com/run.fixture/resume.pdf",
    artifact_manifest: [
      {
        artifact_id: "artifact.pipeline",
        kind: "pipeline_result",
        stage_name: "persist_artifacts",
        storage_backend: "url",
        schema_version: "1",
        uri: "https://example.com/run.fixture/pipeline.json",
        content_type: "application/json",
      },
    ],
    stage_events: [],
    diagnostics: {
      summary: "Generation completed successfully.",
      messages: ["Generation completed successfully."],
      warnings: [],
      fallback_repairs: [],
    },
    selected_experiences: [
      {
        id: "exp-1",
        title: "Senior Frontend Engineer",
        company: "ResumeAI",
        summary: "Built React workflow tooling.",
        rationale: "Strong match for React and TypeScript leadership.",
        score: 0.96,
        evidence: ["TypeScript", "React", "Accessibility"],
      },
    ],
    selected_projects: [
      {
        id: "proj-1",
        name: "Resume Pipeline",
        summary: "Implemented deterministic rendering pipeline.",
        rationale: "Directly relevant to resume generation.",
        score: 0.91,
      },
    ],
    selected_skills: [
      {
        id: "skill-1",
        name: "TypeScript",
        category: "technical",
        rationale: "Explicitly required in the posting.",
        score: 0.99,
      },
    ],
    verification_warnings: [],
    fallback_repairs: [],
    run_metadata: makeRunMetadata(),
  };

  return {
    ...base,
    ...overrides,
    available_outputs: overrides.available_outputs
      ? (overrides.available_outputs as GenerateResumeResponse["available_outputs"])
      : base.available_outputs,
    artifact_manifest: overrides.artifact_manifest
      ? (overrides.artifact_manifest as GenerateResumeResponse["artifact_manifest"])
      : base.artifact_manifest,
    diagnostics: overrides.diagnostics
      ? {
          ...base.diagnostics,
          ...overrides.diagnostics,
          messages: overrides.diagnostics.messages
            ? [...overrides.diagnostics.messages]
            : base.diagnostics?.messages ?? [],
          warnings: overrides.diagnostics.warnings
            ? [...overrides.diagnostics.warnings]
            : base.diagnostics?.warnings ?? [],
          fallback_repairs: overrides.diagnostics.fallback_repairs
            ? [...overrides.diagnostics.fallback_repairs]
            : base.diagnostics?.fallback_repairs ?? [],
        }
      : base.diagnostics,
    selected_experiences: overrides.selected_experiences
      ? (overrides.selected_experiences as GenerateResumeResponse["selected_experiences"])
      : base.selected_experiences,
    selected_projects: overrides.selected_projects
      ? (overrides.selected_projects as GenerateResumeResponse["selected_projects"])
      : base.selected_projects,
    selected_skills: overrides.selected_skills
      ? (overrides.selected_skills as GenerateResumeResponse["selected_skills"])
      : base.selected_skills,
    verification_warnings: overrides.verification_warnings
      ? (overrides.verification_warnings as GenerateResumeResponse["verification_warnings"])
      : base.verification_warnings,
    fallback_repairs: overrides.fallback_repairs
      ? (overrides.fallback_repairs as GenerateResumeResponse["fallback_repairs"])
      : base.fallback_repairs,
    run_metadata: {
      ...base.run_metadata,
      ...(overrides.run_metadata as Partial<RunMetadata> | undefined),
    },
  };
}

export function makeGenerationResult(overrides: DeepPartial<GenerationResultData> = {}): GenerationResultData {
  const fallbackRepairs: FallbackRepairMetadata[] =
    (overrides.diagnostics?.fallback_repairs as FallbackRepairMetadata[] | undefined) ?? [];

  const base: GenerationResultData = {
    run_metadata: makeRunMetadata(),
    overall_status: "succeeded",
    selected_experiences: [
      {
        id: "exp-1",
        title: "Senior Frontend Engineer",
        company: "ResumeAI",
        summary: "Built React workflow tooling.",
        rationale: "Matched to accessibility and React requirements.",
      },
    ],
    selected_projects: [
      {
        id: "proj-1",
        name: "Resume Pipeline",
        summary: "Implemented rendering and verification pipeline.",
        rationale: "Relevant project evidence.",
      },
    ],
    selected_skills: [
      {
        id: "skill-1",
        name: "TypeScript",
        rationale: "Key skill from the job description.",
      },
    ],
    verification_warnings: [],
    diagnostics: {
      summary: "Generation completed successfully.",
      messages: ["Generation completed successfully."],
      warnings: [],
      fallback_repairs: fallbackRepairs,
    },
    render_artifacts: [
      {
        artifact_id: "artifact.pipeline",
        kind: "pipeline_result",
        stage_name: "persist_artifacts",
        storage_backend: "url",
        schema_version: "1",
        uri: "https://example.com/run.fixture/pipeline.json",
        content_type: "application/json",
      },
    ],
    downloadable_outputs: [
      {
        kind: "pdf",
        storage_kind: "url",
        reference: "https://example.com/run.fixture/resume.pdf",
        preview_reference: "https://example.com/run.fixture/resume-preview.pdf",
        file_name: "resume.pdf",
        content_type: "application/pdf",
      },
      {
        kind: "structured_json",
        storage_kind: "url",
        reference: "https://example.com/run.fixture/result.json",
        file_name: "result.json",
        content_type: "application/json",
      },
    ],
    final_file_reference: "https://example.com/run.fixture/resume.pdf",
    raw_response: makeGenerateResponse(),
  };

  return {
    ...base,
    ...overrides,
    run_metadata: {
      ...base.run_metadata,
      ...(overrides.run_metadata as Partial<RunMetadata> | undefined),
    },
    diagnostics: overrides.diagnostics
      ? {
          ...base.diagnostics,
          ...overrides.diagnostics,
          messages: overrides.diagnostics.messages
            ? [...overrides.diagnostics.messages]
            : base.diagnostics?.messages ?? [],
          warnings: overrides.diagnostics.warnings
            ? [...overrides.diagnostics.warnings]
            : base.diagnostics?.warnings ?? [],
          fallback_repairs: overrides.diagnostics.fallback_repairs
            ? [...overrides.diagnostics.fallback_repairs]
            : base.diagnostics?.fallback_repairs ?? [],
        }
      : base.diagnostics,
    render_artifacts: overrides.render_artifacts
      ? (overrides.render_artifacts as GenerationResultData["render_artifacts"])
      : base.render_artifacts,
    downloadable_outputs: overrides.downloadable_outputs
      ? (overrides.downloadable_outputs as GenerationResultData["downloadable_outputs"])
      : base.downloadable_outputs,
    selected_experiences: overrides.selected_experiences
      ? (overrides.selected_experiences as GenerationResultData["selected_experiences"])
      : base.selected_experiences,
    selected_projects: overrides.selected_projects
      ? (overrides.selected_projects as GenerationResultData["selected_projects"])
      : base.selected_projects,
    selected_skills: overrides.selected_skills
      ? (overrides.selected_skills as GenerationResultData["selected_skills"])
      : base.selected_skills,
    verification_warnings: overrides.verification_warnings
      ? (overrides.verification_warnings as GenerationResultData["verification_warnings"])
      : base.verification_warnings,
  };
}

export function makeProgressEvent(overrides: Partial<PipelineProgressEvent> = {}): PipelineProgressEvent {
  return {
    event_id: `${overrides.event_type ?? "stage_started"}-${overrides.stage_name ?? "parse_job_description"}`,
    event_type: "stage_started",
    run_id: "run.fixture",
    timestamp: "2026-04-12T10:00:05.000Z",
    stage_name: "parse_job_description",
    machine_status: "running",
    human_message: "Reading job requirements",
    progress_percent: 22,
    metadata: {},
    ...overrides,
  };
}

export function makeProgressState(overrides: Partial<PipelineProgressState> = {}): PipelineProgressState {
  const state = createEmptyProgressState(overrides.run_id ?? "run.fixture");
  const baseEvent = makeProgressEvent();

  return {
    ...state,
    events: overrides.events ?? [baseEvent],
    stages: overrides.stages ?? [
      {
        stage_name: "ingest_job_description",
        machine_status: "succeeded",
        human_message: "Input accepted",
        updated_at: "2026-04-12T10:00:02.000Z",
      },
      {
        stage_name: "parse_job_description",
        machine_status: "running",
        human_message: "Reading job requirements",
        updated_at: "2026-04-12T10:00:05.000Z",
      },
    ],
    latest_event: overrides.latest_event ?? baseEvent,
    progress_percent: overrides.progress_percent ?? 22,
    terminal: overrides.terminal ?? false,
    current_stage: overrides.current_stage ?? {
      stage_name: "parse_job_description",
      machine_status: "running",
      human_message: "Reading job requirements",
      updated_at: "2026-04-12T10:00:05.000Z",
    },
    completed_stages: overrides.completed_stages ?? [
      {
        stage_name: "ingest_job_description",
        machine_status: "succeeded",
        human_message: "Input accepted",
        updated_at: "2026-04-12T10:00:02.000Z",
      },
    ],
    retry_notices: overrides.retry_notices ?? [],
    fallback_notices: overrides.fallback_notices ?? [],
    connection: {
      enabled: true,
      connected: true,
      transport: "sse",
      ...overrides.connection,
    },
    ...overrides,
  };
}

export function makeBackendError(overrides: Partial<BackendErrorPayload> = {}): BackendErrorPayload {
  return {
    message: "PDF compilation failed.",
    stage_name: "compile_pdf",
    failure_type: "pdf_compile_error",
    failure_category: "rendering",
    retryable: true,
    fallback_eligible: false,
    run_id: "run.fixture",
    diagnostics: {
      summary: "PDF compilation failed.",
      messages: ["PDF compilation failed."],
      warnings: [],
      fallback_repairs: [],
    },
    error_source: "backend",
    ...overrides,
  };
}

export function makeBackendHealth(overrides: Partial<BackendHealthState> = {}): BackendHealthState {
  return {
    status: "healthy",
    summary: "Backend is reachable.",
    checked_at: "2026-04-12T10:00:00.000Z",
    ...overrides,
  };
}

export function makeReadinessIndicators(): ReadinessIndicator[] {
  return [
    {
      key: "master_profile",
      label: "Master profile available",
      state: "ready",
      summary: "Source profile path resolved successfully.",
    },
    {
      key: "template",
      label: "Template available",
      state: "ready",
      summary: "Template is ready for rendering.",
    },
    {
      key: "backend",
      label: "Backend reachable",
      state: "ready",
      summary: "Health probe completed successfully.",
    },
  ];
}

export function makeResumeGenerationState(
  overrides: Partial<ResumeGenerationState> = {},
): ResumeGenerationState {
  return {
    ...createInitialResumeGenerationState(),
    ...overrides,
  };
}
