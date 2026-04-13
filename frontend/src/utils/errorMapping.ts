import type {
  BackendErrorPayload,
  ErrorClassification,
  ErrorDisplayModel,
} from "../types/pipeline";
import { formatStageName } from "./resumeGenerationFormatters";

export function buildErrorDisplayModel(
  error: BackendErrorPayload,
): ErrorDisplayModel {
  const classification = classifyError(error);
  const phaseLabel = error.stage_name ? formatStageName(error.stage_name) : undefined;

  switch (classification) {
    case "validation":
      return {
        classification,
        title: "Input needs correction",
        explanation:
          "The run could not start because the submitted job description or settings were invalid.",
        phase_label: phaseLabel,
        retry_recommendation:
          "Update the job description or input settings, then submit again.",
        next_action_label: "Edit JD",
      };
    case "api_route_not_found":
      return {
        classification,
        title: "API route not reachable",
        explanation:
          "The frontend reached the backend origin, but the resume generation API route was not available there.",
        phase_label: phaseLabel,
        retry_recommendation:
          error.suggested_next_step ??
          "Confirm the frontend proxy or API base URL points at the backend application.",
        next_action_label: "Retry run",
      };
    case "sse_route_not_found":
      return {
        classification,
        title: "Progress stream unavailable",
        explanation:
          "The backend progress stream route could not be reached, so live run updates are unavailable.",
        phase_label: phaseLabel,
        retry_recommendation:
          error.suggested_next_step ??
          "Confirm the /events route is exposed and routed correctly from the frontend.",
        next_action_label: "Show details",
      };
    case "backend_unavailable":
      return {
        classification,
        title: "Backend unavailable",
        explanation:
          "The frontend could not reach the generation backend or the generation route is unavailable.",
        phase_label: phaseLabel,
        retry_recommendation:
          "Confirm backend availability, then retry the run without changing the current context.",
        next_action_label: "Retry run",
      };
    case "job_analysis_failed":
      return {
        classification,
        title: "Job analysis failed",
        explanation:
          "The backend could not parse or normalize the target job description.",
        phase_label: phaseLabel,
        retry_recommendation:
          "Review the pasted posting for completeness and retry after editing if needed.",
        next_action_label: "Edit JD",
      };
    case "selection_failed":
      return {
        classification,
        title: "Selection failed",
        explanation:
          "The system could not complete evidence selection from the source profile.",
        phase_label: phaseLabel,
        retry_recommendation:
          "Retry the run. If it repeats, inspect the source profile and selected input.",
        next_action_label: "Retry run",
      };
    case "generation_failed":
      return {
        classification,
        title: "Generation failed",
        explanation:
          "Structured resume generation did not complete successfully.",
        phase_label: phaseLabel,
        retry_recommendation:
          "Retry the run. If it repeats, inspect diagnostics in debug mode.",
        next_action_label: "Retry run",
      };
    case "verification_failed":
      return {
        classification,
        title: "Verification failed",
        explanation:
          "The generated content did not pass verification or required repair.",
        phase_label: phaseLabel,
        retry_recommendation:
          "Review diagnostics and retry. Human review is recommended before reusing any partial output.",
        next_action_label: "Show details",
      };
    case "rendering_failed":
      return {
        classification,
        title: "Rendering failed",
        explanation:
          "The run reached rendering but could not produce the final document successfully.",
        phase_label: phaseLabel,
        retry_recommendation:
          "Retry the run. If structured output exists, inspect compiler and artifact diagnostics first.",
        next_action_label: "Show details",
      };
    case "artifact_unavailable":
      return {
        classification,
        title: "Artifact unavailable",
        explanation:
          "The run completed partially, but one or more expected artifacts are missing or inaccessible.",
        phase_label: phaseLabel,
        retry_recommendation:
          "Inspect diagnostics and retry if the missing artifact is required.",
        next_action_label: "Show details",
      };
    case "timeout":
      return {
        classification,
        title: "Run timed out",
        explanation:
          "The backend did not finish the run within the allowed execution window.",
        phase_label: phaseLabel,
        retry_recommendation:
          "Retry the run. If it repeats, shorten the input or inspect backend diagnostics.",
        next_action_label: "Retry run",
      };
    case "transport_network_error":
      return {
        classification,
        title: "Transport failure",
        explanation:
          "The frontend could not complete the request because the backend was unreachable or the request failed in transit.",
        phase_label: phaseLabel,
        retry_recommendation:
          error.suggested_next_step ??
          "Retry safely after confirming the backend server is running and the API base URL is correct.",
        next_action_label: "Retry run",
      };
    case "frontend_exception":
      return {
        classification,
        title: "Frontend error",
        explanation:
          "The UI hit an unexpected exception while rendering or processing the current route.",
        phase_label: phaseLabel,
        retry_recommendation:
          "Copy diagnostics, then reload or start a new run.",
        next_action_label: "Show details",
      };
    default:
      return {
        classification,
        title: "Unknown internal error",
        explanation:
          "The run failed with an internal error that could not be classified more precisely.",
        phase_label: phaseLabel,
        retry_recommendation:
          "Retry the run. If it repeats, preserve the run ID and inspect diagnostics.",
        next_action_label: "Retry run",
      };
  }
}

export function classifyError(error: BackendErrorPayload): ErrorClassification {
  const message = error.message.toLowerCase();
  const backendDetail = error.backend_detail?.toLowerCase() ?? "";
  const transportDetail = error.transport_detail?.toLowerCase() ?? "";
  const failureType = error.failure_type?.toLowerCase() ?? "";
  const failureCategory = error.failure_category?.toLowerCase() ?? "";
  const stage = error.stage_name?.toLowerCase() ?? "";

  if (
    error.error_source === "validation" ||
    error.status_code === 400 ||
    failureType.includes("input_validation")
  ) {
    return "validation";
  }
  if (
    error.transport_target === "generate_resume" &&
    error.status_code === 404
  ) {
    return "api_route_not_found";
  }
  if (
    error.transport_target === "progress_stream" &&
    error.status_code === 404
  ) {
    return "sse_route_not_found";
  }
  if (
    message.includes("timeout") ||
    failureType.includes("timeout") ||
    transportDetail.includes("timed out") ||
    transportDetail.includes("aborterror")
  ) {
    return "timeout";
  }
  if (
    error.error_source === "transport" ||
    failureCategory.includes("transport") ||
    message.includes("network") ||
    transportDetail.includes("econnrefused") ||
    transportDetail.includes("failed to fetch") ||
    transportDetail.includes("network request failed")
  ) {
    return "transport_network_error";
  }
  if (
    error.status_code === 503 ||
    message.includes("unavailable") ||
    backendDetail.includes("temporarily unavailable")
  ) {
    return "backend_unavailable";
  }
  if (
    stage.includes("parse_job_description") ||
    stage.includes("ingest_job_description") ||
    failureType.includes("job_description")
  ) {
    return "job_analysis_failed";
  }
  if (
    stage.includes("rank_select_evidence") ||
    failureType.includes("ranking") ||
    failureType.includes("selection")
  ) {
    return "selection_failed";
  }
  if (
    stage.includes("generate_structured_content") ||
    failureType.includes("generation")
  ) {
    return "generation_failed";
  }
  if (
    stage.includes("verify_generated_content") ||
    failureType.includes("verification")
  ) {
    return "verification_failed";
  }
  if (
    stage.includes("render_deterministic_latex") ||
    stage.includes("compile_pdf") ||
    failureType.includes("pdf_compile") ||
    failureType.includes("latex_render") ||
    failureType.includes("render")
  ) {
    return "rendering_failed";
  }
  if (message.includes("artifact") || failureType.includes("artifact")) {
    return "artifact_unavailable";
  }
  if (error.error_source === "frontend") {
    return "frontend_exception";
  }
  return "unknown_internal_error";
}
