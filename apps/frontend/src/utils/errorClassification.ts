import type { BackendErrorPayload } from "../types/pipeline";

export function normalizeGenerateResumeTransportError(
  error: unknown,
  context: {
    requestUrl: string;
    statusCode?: number;
  },
): BackendErrorPayload {
  const message = extractErrorMessage(error);
  const lowerMessage = message.toLowerCase();

  if (context.statusCode === 404) {
    return {
      message: "API route not reachable from frontend.",
      error_source: "transport",
      status_code: 404,
      transport_target: "generate_resume",
      transport_detail: `POST ${context.requestUrl} returned HTTP 404.`,
      suggested_next_step: "Confirm the frontend base URL or dev proxy points at the backend API.",
    };
  }

  if (
    lowerMessage.includes("econnrefused") ||
    lowerMessage.includes("failed to fetch") ||
    lowerMessage.includes("networkerror") ||
    lowerMessage.includes("network request failed") ||
    lowerMessage.includes("load failed")
  ) {
    return {
      message: "Backend server not running or wrong base URL.",
      error_source: "transport",
      transport_target: "generate_resume",
      transport_detail: message,
      suggested_next_step: "Start the backend server or correct the configured API base URL.",
    };
  }

  if (
    lowerMessage.includes("timeout") ||
    lowerMessage.includes("timed out") ||
    lowerMessage.includes("aborterror") ||
    lowerMessage.includes("signal timed out")
  ) {
    return {
      message: "Backend did not respond in time.",
      error_source: "transport",
      transport_target: "generate_resume",
      transport_detail: message,
      suggested_next_step: "Retry the run. If it repeats, inspect backend responsiveness and timeout settings.",
    };
  }

  return {
    message: "Transport request failed.",
    error_source: "transport",
    transport_target: "generate_resume",
    transport_detail: message,
    suggested_next_step: "Confirm backend reachability and retry the request.",
  };
}

export function buildProgressStreamTransportError(
  detail: string,
  statusCode?: number,
): BackendErrorPayload {
  if (statusCode === 404) {
    return {
      message: "Progress stream endpoint unreachable.",
      error_source: "transport",
      status_code: 404,
      transport_target: "progress_stream",
      transport_detail: detail,
      suggested_next_step: "Confirm the /events route is exposed by the backend and routed correctly from the frontend.",
    };
  }

  return {
    message: "Progress stream disconnected.",
    error_source: "transport",
    transport_target: "progress_stream",
    transport_detail: detail,
    suggested_next_step: "Retry after confirming the backend event stream is reachable.",
  };
}

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message || error.name;
  }
  return typeof error === "string" ? error : "Unknown transport failure.";
}
