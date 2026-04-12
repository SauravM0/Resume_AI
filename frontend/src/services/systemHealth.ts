import type { BackendHealthState } from "../types/pipeline";

export interface ProbeBackendHealthOptions {
  baseUrl?: string;
  signal?: AbortSignal;
}

export async function probeBackendHealth(
  options: ProbeBackendHealthOptions = {},
): Promise<BackendHealthState> {
  const baseUrl = options.baseUrl ?? "";
  const checkedAt = new Date().toISOString();

  try {
    const response = await fetch(`${baseUrl}/api/generate-resume`, {
      method: "GET",
      signal: options.signal,
    });

    if (response.status >= 500) {
      return {
        status: "degraded",
        summary: "Backend reachable but reporting server errors.",
        detail: `Health probe reached /api/generate-resume and received HTTP ${response.status}.`,
        http_status_code: response.status,
        checked_at: checkedAt,
      };
    }

    if (response.status === 404) {
      return {
        status: "unavailable",
        summary: "Backend endpoint not found.",
        detail: "The resume generation route is not available at the configured base URL.",
        http_status_code: response.status,
        checked_at: checkedAt,
      };
    }

    return {
      status: "healthy",
      summary: "Backend reachable and responding.",
      detail:
        response.status === 405
          ? "The generation route is present and rejected the probe method as expected."
          : `The generation route responded with HTTP ${response.status}.`,
      http_status_code: response.status,
      checked_at: checkedAt,
    };
  } catch (error) {
    return {
      status: "unavailable",
      summary: "Backend unreachable.",
      detail: error instanceof Error ? error.message : "Network request failed.",
      checked_at: checkedAt,
    };
  }
}
