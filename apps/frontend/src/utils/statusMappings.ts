import type {
  BackendErrorPayload,
  GenerateResumeResponse,
  PipelineMachineStatus,
  PipelineProgressEvent,
  ResumeGenerationRunStatus,
} from "../types/pipeline";

export function mapResponseStatusToRunStatus(
  response: GenerateResumeResponse,
): ResumeGenerationRunStatus {
  if (response.status === "pending") {
    return "queued";
  }
  if (response.status === "running") {
    return "phase_running";
  }
  if (response.status === "succeeded_with_warnings") {
    return "partial_success";
  }
  if (response.status === "failed" || response.status === "blocked") {
    return "failed";
  }
  return "success";
}

export function deriveRunStatusFromProgress(input: {
  currentStatus: ResumeGenerationRunStatus;
  event: PipelineProgressEvent;
  latestResponseStatus?: string;
}): ResumeGenerationRunStatus {
  if (input.event.event_type === "run_failed" || input.latestResponseStatus === "failed") {
    return "failed";
  }
  if (input.event.event_type === "run_completed") {
    return input.latestResponseStatus === "succeeded_with_warnings"
      ? "partial_success"
      : "success";
  }
  if (input.event.event_type === "stage_completed") {
    return "phase_completed";
  }
  if (
    input.event.event_type === "run_started" ||
    input.event.event_type === "stage_started" ||
    input.event.event_type === "stage_progress" ||
    input.event.event_type === "retry_scheduled" ||
    input.event.event_type === "fallback_applied"
  ) {
    return input.event.event_type === "run_started" ? "queued" : "phase_running";
  }
  return input.currentStatus;
}

export function isActiveStageStatus(status: PipelineMachineStatus | string): boolean {
  return ["pending", "running", "retrying", "fallback_applied"].includes(status);
}

export function isCompletedStageStatus(status: PipelineMachineStatus | string): boolean {
  return ["succeeded", "succeeded_with_warnings", "completed"].includes(status);
}

export function toBackendErrorFromProgressEvent(
  event: PipelineProgressEvent,
  current: BackendErrorPayload | null,
): BackendErrorPayload {
  return {
    message: event.human_message,
    failure_type: readStringMetadata(event.metadata, "failure_type") ?? current?.failure_type,
    failure_category:
      readStringMetadata(event.metadata, "failure_category") ?? current?.failure_category,
    stage_name: event.stage_name ?? current?.stage_name,
    retryable: readBooleanMetadata(event.metadata, "retryable") ?? current?.retryable,
    fallback_eligible:
      readBooleanMetadata(event.metadata, "fallback_eligible") ?? current?.fallback_eligible,
    run_id: event.run_id,
    diagnostics: current?.diagnostics,
    metadata: event.metadata,
  };
}

function readStringMetadata(
  metadata: Record<string, unknown> | undefined,
  key: string,
): string | undefined {
  const value = metadata?.[key];
  return typeof value === "string" ? value : undefined;
}

function readBooleanMetadata(
  metadata: Record<string, unknown> | undefined,
  key: string,
): boolean | undefined {
  const value = metadata?.[key];
  return typeof value === "boolean" ? value : undefined;
}
