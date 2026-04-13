import { PIPELINE_STAGE_ORDER } from "../constants/resumeGeneration";
import type {
  BackendErrorPayload,
  FallbackRepairMetadata,
  GenerateResumeRequest,
  GenerateResumeResponse,
  GenerationResultData,
  PhaseStatus,
  PipelineProgressEvent,
  PipelineProgressState,
  ProgressConnectionState,
  RenderArtifact,
  ResumeGenerationState,
  RunMetadata,
  VerificationWarning,
} from "../types/pipeline";
import {
  deriveRunStatusFromProgress,
  isActiveStageStatus,
  isCompletedStageStatus,
  mapResponseStatusToRunStatus,
  toBackendErrorFromProgressEvent,
} from "../utils/statusMappings";
import { validateJobDescription } from "../utils/jobDescriptionValidation";

export interface ResumeGenerationActionMap {
  validating: { request: GenerateResumeRequest };
  validation_failed: { request: GenerateResumeRequest; errors: string[] };
  submitting: { request: GenerateResumeRequest; runId: string };
  submit_failed: { error: BackendErrorPayload; runId?: string };
  response_received: { response: GenerateResumeResponse };
  progress_event_received: { event: PipelineProgressEvent };
  progress_connection_changed: { runId: string; connection: ProgressConnectionState };
  cancelled: { reason?: string };
  debug_toggled: { visible?: boolean };
  retry_started: {};
  retry_finished: {};
  reset: {};
}

export type ResumeGenerationAction = {
  [K in keyof ResumeGenerationActionMap]: { type: K } & ResumeGenerationActionMap[K];
}[keyof ResumeGenerationActionMap];

export function createInitialResumeGenerationState(): ResumeGenerationState {
  return {
    status: "idle",
    view: "form",
    run: null,
    current_phase: null,
    progress: null,
    result: null,
    error: null,
    debug_visible: false,
    retrying: false,
    submitted_request: null,
    last_completed_stage: null,
    validation_errors: [],
  };
}

export function resumeGenerationReducer(
  state: ResumeGenerationState,
  action: ResumeGenerationAction,
): ResumeGenerationState {
  switch (action.type) {
    case "validating":
      return {
        ...state,
        status: "validating_input",
        view: "form",
        submitted_request: action.request,
        validation_errors: [],
        error: null,
      };
    case "validation_failed":
      return {
        ...state,
        status: "idle",
        view: "form",
        submitted_request: action.request,
        validation_errors: action.errors,
      };
    case "submitting":
      return {
        ...state,
        status: "submitting",
        view: "progress",
        run: createRunMetadata(action.runId, action.request),
        submitted_request: action.request,
        result: null,
        error: null,
        progress: createEmptyProgressState(action.runId),
        current_phase: null,
        last_completed_stage: null,
        validation_errors: [],
      };
    case "submit_failed": {
      const run = action.runId ? { ...(state.run ?? { run_id: action.runId }), run_id: action.runId } : state.run;
      return {
        ...state,
        status: "failed",
        view: "error",
        run,
        error: action.error,
      };
    }
    case "response_received": {
      const result = buildGenerationResultData(action.response, state.submitted_request);
      const mappedStatus = mapResponseStatusToRunStatus(action.response);
      return {
        ...state,
        status: mappedStatus,
        view: mappedStatus === "failed" ? "error" : mappedStatus === "success" || mappedStatus === "partial_success" ? "result" : "progress",
        run: result.run_metadata,
        result,
        error:
          action.response.status === "failed" || action.response.status === "blocked"
            ? {
                message: result.diagnostics?.summary ?? "Resume generation failed.",
                run_id: action.response.run_id,
                diagnostics: result.diagnostics,
              }
            : null,
      };
    }
    case "progress_event_received": {
      const progress = updateProgressState(state.progress, action.event);
      const currentPhase = progress.current_stage ?? null;
      const lastCompletedStage =
        progress.completed_stages[progress.completed_stages.length - 1] ??
        state.last_completed_stage;
      const derivedStatus = deriveRunStatusFromProgress({
        currentStatus: state.status,
        event: action.event,
        latestResponseStatus: state.result?.overall_status,
      });
      return {
        ...state,
        status: derivedStatus,
        view: derivedStatus === "failed" ? "error" : state.result ? "result" : "progress",
        progress,
        run: {
          ...(state.run ?? { run_id: action.event.run_id }),
          run_id: action.event.run_id,
        },
        current_phase: currentPhase,
        last_completed_stage: lastCompletedStage,
        error:
          action.event.event_type === "run_failed"
            ? toBackendErrorFromProgressEvent(action.event, state.error)
            : state.error,
      };
    }
    case "progress_connection_changed":
      return {
        ...state,
        progress: updateProgressConnection(state.progress, action.runId, action.connection),
      };
    case "cancelled":
      return {
        ...state,
        status: "cancelled",
        view: state.result ? "result" : "error",
        error: action.reason
          ? {
              message: action.reason,
              run_id: state.run?.run_id,
            }
          : state.error,
      };
    case "debug_toggled":
      return {
        ...state,
        debug_visible: action.visible ?? !state.debug_visible,
      };
    case "retry_started":
      return {
        ...state,
        retrying: true,
      };
    case "retry_finished":
      return {
        ...state,
        retrying: false,
      };
    case "reset":
      return createInitialResumeGenerationState();
    default:
      return state;
  }
}

export function validateGenerateRequest(request: GenerateResumeRequest): string[] {
  const errors = [...validateJobDescription(request.job_description_text).errors];

  if (request.job_posting_url) {
    try {
      new URL(request.job_posting_url);
    } catch {
      errors.push("Job posting URL must be a valid URL.");
    }
  }

  return errors;
}

export function createEmptyProgressState(runId: string): PipelineProgressState {
  return {
    run_id: runId,
    events: [],
    stages: [],
    latest_event: undefined,
    progress_percent: 0,
    terminal: false,
    current_stage: undefined,
    completed_stages: [],
    retry_notices: [],
    fallback_notices: [],
    connection: {
      enabled: true,
      connected: false,
      transport: "sse",
    },
  };
}

function createRunMetadata(runId: string, request: GenerateResumeRequest): RunMetadata {
  return {
    run_id: runId,
    source_profile_id: request.source_profile_id,
    source_profile_path: request.source_profile_path,
    template_id: request.template_id,
    render_job_id: request.render_job_id,
    frontend_correlation_id: request.frontend_correlation_id,
    started_at: new Date().toISOString(),
  };
}

function updateProgressState(
  current: PipelineProgressState | null,
  event: PipelineProgressEvent,
): PipelineProgressState {
  const base = current ?? createEmptyProgressState(event.run_id);
  const stagesByName = new Map(base.stages.map((stage) => [stage.stage_name, stage]));

  if (event.stage_name) {
    stagesByName.set(event.stage_name, {
      stage_name: event.stage_name,
      machine_status: event.machine_status,
      human_message: event.human_message,
      progress_percent: event.progress_percent,
      updated_at: event.timestamp,
      attempt_number: readNumberMetadata(event.metadata, "attempt_number"),
      failure_type: readStringMetadata(event.metadata, "failure_type"),
      failure_category: readStringMetadata(event.metadata, "failure_category"),
      retryable: readBooleanMetadata(event.metadata, "retryable"),
      fallback_eligible: readBooleanMetadata(event.metadata, "fallback_eligible"),
      fallback_metadata: readFallbackMetadata(event.metadata),
      metadata: event.metadata,
    });
  }

  const stages = PIPELINE_STAGE_ORDER.flatMap((stageName) => {
    const stage = stagesByName.get(stageName);
    return stage ? [stage] : [];
  });
  const currentStage = [...stages].reverse().find((stage) => isActiveStageStatus(stage.machine_status));
  const completedStages = stages.filter((stage) => isCompletedStageStatus(stage.machine_status));

  return {
    run_id: event.run_id,
    events: [...base.events, event],
    stages,
    latest_event: event,
    progress_percent: event.progress_percent ?? base.progress_percent,
    terminal: event.event_type === "run_completed" || event.event_type === "run_failed",
    current_stage: currentStage,
    completed_stages: completedStages,
    retry_notices:
      event.event_type === "retry_scheduled" ? [...base.retry_notices, event] : base.retry_notices,
    fallback_notices:
      event.event_type === "fallback_applied" ? [...base.fallback_notices, event] : base.fallback_notices,
    connection: base.connection,
  };
}

function updateProgressConnection(
  current: PipelineProgressState | null,
  runId: string,
  connection: ProgressConnectionState,
): PipelineProgressState {
  const base = current ?? createEmptyProgressState(runId);
  if (
    base.run_id === runId &&
    base.connection.enabled === connection.enabled &&
    base.connection.connected === connection.connected &&
    base.connection.transport === connection.transport &&
    base.connection.last_error === connection.last_error
  ) {
    return base;
  }

  return {
    ...base,
    run_id: runId,
    connection,
  };
}

function buildGenerationResultData(
  response: GenerateResumeResponse,
  request: GenerateResumeRequest | null,
): GenerationResultData {
  const verificationWarnings = [
    ...(response.verification_warnings ?? []),
    ...response.warnings.map<VerificationWarning>((warning) => ({
      message: warning,
      severity: "warning",
      source: "pipeline_response",
    })),
  ];
  const fallbackRepairs = [
    ...(response.fallback_repairs ?? []),
    ...collectFallbackRepairsFromArtifacts(response.artifact_manifest),
  ];

  return {
    run_metadata: {
      run_id: response.run_id,
      source_profile_id: request?.source_profile_id,
      source_profile_path: request?.source_profile_path,
      template_id: request?.template_id,
      render_job_id: request?.render_job_id,
      frontend_correlation_id: request?.frontend_correlation_id,
      ...response.run_metadata,
      finished_at: new Date().toISOString(),
    },
    overall_status: response.status,
    selected_experiences: response.selected_experiences ?? [],
    selected_projects: response.selected_projects ?? [],
    selected_skills: response.selected_skills ?? [],
    verification_warnings: verificationWarnings,
    diagnostics: response.diagnostics
      ? {
          ...response.diagnostics,
          fallback_repairs: fallbackRepairs,
        }
      : {
          messages: response.warnings,
          warnings: verificationWarnings,
          fallback_repairs: fallbackRepairs,
        },
    render_artifacts: response.artifact_manifest,
    downloadable_outputs: response.available_outputs,
    final_file_reference: response.final_file_reference,
    raw_response: response,
  };
}

function collectFallbackRepairsFromArtifacts(artifacts: RenderArtifact[]): FallbackRepairMetadata[] {
  return artifacts.flatMap((artifact) => {
    const strategy = readStringMetadata(artifact.metadata, "fallback_strategy");
    if (!strategy) {
      return [];
    }
    return [
      {
        stage_name: artifact.stage_name,
        applied: true,
        strategy,
        repair_status: "applied",
        metadata: artifact.metadata,
      },
    ];
  });
}

function readStringMetadata(
  metadata: Record<string, unknown> | undefined,
  key: string,
): string | undefined {
  const value = metadata?.[key];
  return typeof value === "string" ? value : undefined;
}

function readNumberMetadata(
  metadata: Record<string, unknown> | undefined,
  key: string,
): number | undefined {
  const value = metadata?.[key];
  return typeof value === "number" ? value : undefined;
}

function readBooleanMetadata(
  metadata: Record<string, unknown> | undefined,
  key: string,
): boolean | undefined {
  const value = metadata?.[key];
  return typeof value === "boolean" ? value : undefined;
}

function readFallbackMetadata(
  metadata: Record<string, unknown> | undefined,
): FallbackRepairMetadata | undefined {
  const strategy = readStringMetadata(metadata, "fallback_strategy");
  if (!strategy) {
    return undefined;
  }
  return {
    applied: true,
    strategy,
    repair_status: "applied",
    metadata,
  };
}
