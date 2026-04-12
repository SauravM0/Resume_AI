import type {
  PipelineMachineStatus,
  PipelineProgressEvent,
  PipelineProgressEventType,
  PipelineStageName,
} from "../types/pipeline";

const PROGRESS_STREAM_ENDPOINT = "/api/pipeline-runs";

export interface ProgressStreamSubscription {
  close: () => void;
  transport: "sse" | "polling";
}

export interface ProgressStreamOptions {
  baseUrl?: string;
  onEvent: (event: PipelineProgressEvent) => void;
  onError?: (message: string, error?: Event | Error) => void;
  onOpen?: () => void;
  onMalformedEvent?: (reason: string, payload?: unknown) => void;
  transport?: "sse" | "polling";
  eventSourceFactory?: (url: string) => EventSource;
}

export function subscribeToPipelineProgress(
  runId: string,
  options: ProgressStreamOptions,
): ProgressStreamSubscription {
  const transport = options.transport ?? "sse";

  if (transport === "polling") {
    options.onError?.(
      "Polling transport is not implemented yet. Falling back to SSE is required.",
    );
    return {
      close: () => {},
      transport,
    };
  }

  return subscribeToSseProgress(runId, options);
}

export function parsePipelineProgressEvent(input: {
  raw: unknown;
  fallbackRunId?: string;
  eventTypeHint?: string;
}): PipelineProgressEvent | null {
  const record = isRecord(input.raw) ? input.raw : undefined;
  if (!record) {
    return null;
  }

  const normalizedEventType = normalizeEventType(
    readString(record.event_type) ?? input.eventTypeHint,
    record,
  );
  const runId = readString(record.run_id) ?? input.fallbackRunId;
  if (!normalizedEventType || !runId) {
    return null;
  }

  const humanMessage =
    readString(record.human_message) ??
    readString(record.message) ??
    defaultHumanMessage(normalizedEventType);

  const stageName = normalizeStageName(
    readString(record.stage_name) ??
      readString(record.phase_name) ??
      readString(record.stage),
  );
  const machineStatus =
    normalizeMachineStatus(
      readString(record.machine_status) ??
        readString(record.status) ??
        inferMachineStatus(normalizedEventType),
    ) ?? inferMachineStatus(normalizedEventType);

  return buildNormalizedEvent({
    eventType: normalizedEventType,
    eventId:
      readString(record.event_id) ??
      `${normalizedEventType}.${runId}.${readString(record.timestamp) ?? Date.now()}`,
    runId,
    timestamp: readString(record.timestamp) ?? new Date().toISOString(),
    stageName,
    humanMessage,
    machineStatus,
    progressPercent: normalizeProgressPercent(record.progress_percent),
    metadata: isRecord(record.metadata)
      ? record.metadata
      : collectResidualMetadata(record, [
          "event_id",
          "run_id",
          "event_type",
          "timestamp",
          "stage_name",
          "phase_name",
          "stage",
          "human_message",
          "message",
          "machine_status",
          "status",
          "progress_percent",
          "metadata",
        ]),
  });
}

function buildNormalizedEvent(input: {
  eventType: PipelineProgressEventType;
  eventId: string;
  runId: string;
  timestamp: string;
  stageName?: PipelineStageName;
  humanMessage: string;
  machineStatus: PipelineMachineStatus | string;
  progressPercent?: number;
  metadata?: Record<string, unknown>;
}): PipelineProgressEvent {
  const common = {
    event_id: input.eventId,
    run_id: input.runId,
    timestamp: input.timestamp,
    human_message: input.humanMessage,
    machine_status: input.machineStatus,
    progress_percent: input.progressPercent,
    metadata: input.metadata,
  };

  switch (input.eventType) {
    case "stage_started":
    case "stage_progress":
    case "stage_completed":
    case "stage_failed":
      if (!input.stageName) {
        return {
          ...common,
          event_type: "warning",
          human_message: input.humanMessage,
          machine_status: "succeeded_with_warnings",
        } as PipelineProgressEvent;
      }
      return {
        ...common,
        event_type: input.eventType,
        stage_name: input.stageName,
      } as PipelineProgressEvent;
    case "run_started":
    case "warning":
    case "retry_scheduled":
    case "fallback_applied":
    case "run_completed":
    case "run_failed":
      return {
        ...common,
        event_type: input.eventType,
        stage_name: input.stageName,
      } as PipelineProgressEvent;
  }
}

function subscribeToSseProgress(
  runId: string,
  options: ProgressStreamOptions,
): ProgressStreamSubscription {
  const baseUrl = options.baseUrl ?? "";
  const url = `${baseUrl}${PROGRESS_STREAM_ENDPOINT}/${encodeURIComponent(runId)}/events`;
  const source = (options.eventSourceFactory ?? ((target) => new EventSource(target)))(url);

  source.onopen = () => {
    options.onOpen?.();
  };

  source.onerror = (error) => {
    options.onError?.("Progress stream disconnected.", error);
  };

  const eventTypes = [
    "run_started",
    "stage_started",
    "stage_progress",
    "stage_completed",
    "stage_failed",
    "warning",
    "retry_scheduled",
    "fallback_applied",
    "run_completed",
    "run_failed",
  ] as const;

  for (const eventType of eventTypes) {
    source.addEventListener(eventType, (message) => {
      handleSseMessage(runId, message, eventType, options);
    });
  }

  source.onmessage = (message) => {
    handleSseMessage(runId, message, undefined, options);
  };

  return {
    close: () => source.close(),
    transport: "sse",
  };
}

function handleSseMessage(
  runId: string,
  message: Event,
  eventTypeHint: string | undefined,
  options: ProgressStreamOptions,
) {
  const eventMessage = message as MessageEvent<string>;
  const raw = safeParseJson(eventMessage.data);
  if (raw === null) {
    options.onMalformedEvent?.(
      `Failed to parse ${eventTypeHint ?? "message"} event payload.`,
      eventMessage.data,
    );
    options.onError?.(`Failed to parse ${eventTypeHint ?? "message"} event.`, message);
    return;
  }

  const normalized = parsePipelineProgressEvent({
    raw,
    fallbackRunId: runId,
    eventTypeHint,
  });

  if (!normalized) {
    options.onMalformedEvent?.(
      `Malformed ${eventTypeHint ?? "message"} event payload.`,
      raw,
    );
    return;
  }

  options.onEvent(normalized);
}

function safeParseJson(input: string): unknown | null {
  try {
    return JSON.parse(input);
  } catch {
    return null;
  }
}

function normalizeEventType(
  value: string | undefined,
  record: Record<string, unknown>,
): PipelineProgressEventType | null {
  if (
    value === "run_started" ||
    value === "stage_started" ||
    value === "stage_progress" ||
    value === "stage_completed" ||
    value === "stage_failed" ||
    value === "warning" ||
    value === "retry_scheduled" ||
    value === "fallback_applied" ||
    value === "run_completed" ||
    value === "run_failed"
  ) {
    return value;
  }

  if (readBoolean(record.retryable) || readNumber(record.attempt_number)) {
    return "retry_scheduled";
  }
  if (
    readString(record.fallback_strategy) ||
    readString(record.repair_status) ||
    readBoolean(record.fallback_eligible)
  ) {
    return "fallback_applied";
  }
  if (readString(record.warning_code) || Array.isArray(record.warnings)) {
    return "warning";
  }
  return null;
}

function normalizeStageName(value: string | undefined): PipelineStageName | undefined {
  if (
    value === "load_source_profile" ||
    value === "normalize_source_data" ||
    value === "ingest_job_description" ||
    value === "parse_job_description" ||
    value === "rank_select_evidence" ||
    value === "generate_structured_content" ||
    value === "verify_generated_content" ||
    value === "render_deterministic_latex" ||
    value === "compile_pdf" ||
    value === "persist_artifacts"
  ) {
    return value;
  }
  return undefined;
}

function normalizeMachineStatus(
  value: string | undefined,
): PipelineMachineStatus | string | undefined {
  if (
    value === "pending" ||
    value === "running" ||
    value === "succeeded" ||
    value === "succeeded_with_warnings" ||
    value === "failed" ||
    value === "skipped" ||
    value === "retrying" ||
    value === "fallback_applied" ||
    value === "blocked" ||
    value === "completed"
  ) {
    return value;
  }
  return value;
}

function inferMachineStatus(eventType: PipelineProgressEventType): PipelineMachineStatus | string {
  switch (eventType) {
    case "run_started":
      return "pending";
    case "stage_started":
    case "stage_progress":
      return "running";
    case "stage_completed":
    case "run_completed":
      return "completed";
    case "stage_failed":
    case "run_failed":
      return "failed";
    case "warning":
      return "succeeded_with_warnings";
    case "retry_scheduled":
      return "retrying";
    case "fallback_applied":
      return "fallback_applied";
    default:
      return "pending";
  }
}

function defaultHumanMessage(eventType: PipelineProgressEventType): string {
  switch (eventType) {
    case "run_started":
      return "Run started";
    case "stage_started":
      return "Phase started";
    case "stage_progress":
      return "Phase updated";
    case "stage_completed":
      return "Phase completed";
    case "stage_failed":
      return "Phase failed";
    case "warning":
      return "Warning received";
    case "retry_scheduled":
      return "Retry scheduled";
    case "fallback_applied":
      return "Fallback applied";
    case "run_completed":
      return "Run completed";
    case "run_failed":
      return "Run failed";
  }
}

function normalizeProgressPercent(value: unknown): number | undefined {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return undefined;
  }
  return Math.max(0, Math.min(100, value));
}

function collectResidualMetadata(
  record: Record<string, unknown>,
  excludedKeys: string[],
): Record<string, unknown> | undefined {
  const excluded = new Set(excludedKeys);
  const metadata = Object.fromEntries(
    Object.entries(record).filter(([key]) => !excluded.has(key)),
  );
  return Object.keys(metadata).length > 0 ? metadata : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function readBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function readNumber(value: unknown): number | undefined {
  return typeof value === "number" && !Number.isNaN(value) ? value : undefined;
}
