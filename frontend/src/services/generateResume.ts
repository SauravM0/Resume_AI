import type {
  GenerateResumeRequest,
  GenerateResumeResponse,
  ResumeGenerationError,
} from "../types/pipeline";

export interface GenerateResumeOptions {
  baseUrl?: string;
  signal?: AbortSignal;
}

export async function generateResume(
  request: GenerateResumeRequest,
  options: GenerateResumeOptions = {},
): Promise<GenerateResumeResponse> {
  const baseUrl = options.baseUrl ?? "";
  const response = await fetch(`${baseUrl}/api/generate-resume`, {
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
  return payload as GenerateResumeResponse;
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

function normalizeGenerateResumeError(payload: unknown, statusCode: number): ResumeGenerationError {
  if (isRecord(payload)) {
    const detail = isRecord(payload.detail) ? payload.detail : payload;
    return {
      message: readString(detail.message) ?? readString(payload.detail) ?? "Resume generation failed.",
      failure_type: readString(detail.failure_type),
      stage_name: readString(detail.stage_name),
      retryable: readBoolean(detail.retryable),
      fallback_eligible: readBoolean(detail.fallback_eligible),
      run_id: readString(detail.run_id),
      status_code: statusCode,
    };
  }
  return {
    message: "Resume generation failed.",
    status_code: statusCode,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

function readBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}
