import type { BackendHealthState } from "../types/pipeline";
import { buildApiUrl } from "../lib/apiBase";

export interface AIDiagnostics {
  provider: string;
  model: string;
  gemini_api_key_configured: boolean;
  configured: boolean;
  errors: string[];
}

export interface ProbeBackendHealthOptions {
  baseUrl?: string;
  signal?: AbortSignal;
}

export async function probeBackendHealth(
  options: ProbeBackendHealthOptions = {},
): Promise<BackendHealthState> {
  const checkedAt = new Date().toISOString();
  const probeUrl = buildApiUrl("/api/health", options.baseUrl);

  try {
    const response = await fetch(probeUrl, {
      method: "GET",
      signal: options.signal,
    });
    const payload = (await response.json().catch(() => ({}))) as Partial<{
      ok: boolean;
      api: boolean;
      profile_path_configured: boolean;
      template_configured: boolean;
      ai_configured: boolean;
      ai_errors: string[];
    }>;

    if (response.status >= 500) {
      return {
        status: "degraded",
        summary: "Backend reachable but reporting server errors.",
        detail: `Health probe reached /api/health and received HTTP ${response.status}.`,
        http_status_code: response.status,
        checked_at: checkedAt,
      };
    }

    if (response.status === 404) {
      return {
        status: "unavailable",
        summary: "Backend health route not found.",
        detail: "The frontend could not reach /api/health at the configured base URL.",
        http_status_code: response.status,
        checked_at: checkedAt,
      };
    }

    const profileConfigured = payload.profile_path_configured !== false;
    const templateConfigured = payload.template_configured !== false;
    const aiConfigured = payload.ai_configured !== false;
    const aiErrors = payload.ai_errors || [];
    const backendHealthy = payload.ok !== false && payload.api !== false;

    return {
      status: backendHealthy ? (profileConfigured && templateConfigured ? "healthy" : "degraded") : "unavailable",
      summary: backendHealthy ? "Health check passed." : "Backend health check failed.",
      detail: `Health probe returned status ${response.status}. Profile path flag: ${String(profileConfigured)}. Template flag: ${String(templateConfigured)}. AI configured: ${String(aiConfigured)}.${aiErrors.length > 0 ? " AI errors: " + aiErrors.join(", ") : ""}`,
      http_status_code: response.status,
      checked_at: checkedAt,
      api: payload.api,
      profile_path_configured: payload.profile_path_configured,
      template_configured: payload.template_configured,
      ai_configured: payload.ai_configured,
      ai_errors: aiErrors,
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

export async function fetchAIDiagnostics(
  options: ProbeBackendHealthOptions = {},
): Promise<AIDiagnostics> {
  const probeUrl = buildApiUrl("/api/diagnostics/ai", options.baseUrl);

  try {
    const response = await fetch(probeUrl, {
      method: "GET",
      signal: options.signal,
    });
    return await response.json();
  } catch (error) {
    return {
      provider: "unknown",
      model: "unknown",
      gemini_api_key_configured: false,
      configured: false,
      errors: [error instanceof Error ? error.message : "Failed to fetch AI diagnostics"],
    };
  }
}