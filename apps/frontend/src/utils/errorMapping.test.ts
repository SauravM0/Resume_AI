import { buildProgressStreamTransportError, normalizeGenerateResumeTransportError } from "./errorClassification";
import { buildErrorDisplayModel, classifyError } from "./errorMapping";
import { makeBackendError } from "../test/fixtures/resumeGeneration";

describe("error classification", () => {
  it("classifies POST 404 as an API route transport failure", () => {
    const error = normalizeGenerateResumeTransportError(new Error("HTTP 404"), {
      requestUrl: "/api/generate-resume",
      statusCode: 404,
    });

    expect(classifyError(error)).toBe("api_route_not_found");
    expect(buildErrorDisplayModel(error).title).toBe("API route not reachable");
  });

  it("classifies SSE 404 as a progress-stream route failure", () => {
    const error = buildProgressStreamTransportError(
      "GET /api/pipeline-runs/run.test/events returned HTTP 404.",
      404,
    );

    expect(classifyError(error)).toBe("sse_route_not_found");
    expect(buildErrorDisplayModel(error).title).toBe("Progress stream unavailable");
  });

  it("classifies ECONNREFUSED as a transport network failure", () => {
    const error = normalizeGenerateResumeTransportError(new Error("connect ECONNREFUSED 127.0.0.1:8000"), {
      requestUrl: "http://localhost:8000/api/generate-resume",
    });

    expect(classifyError(error)).toBe("transport_network_error");
    expect(error.message).toBe("Backend server not running or wrong base URL.");
  });

  it("classifies timeout failures explicitly", () => {
    const error = normalizeGenerateResumeTransportError(new Error("Request timed out"), {
      requestUrl: "/api/generate-resume",
    });

    expect(classifyError(error)).toBe("timeout");
    expect(error.message).toBe("Backend did not respond in time.");
  });

  it("preserves structured backend 500 failures", () => {
    const error = makeBackendError({
      message: "Ranking failed.",
      backend_detail: "Ranking failed.",
      stage_name: "rank_select_evidence",
      failure_type: "ranking_error",
      failure_category: "pipeline_stage_error",
      status_code: 500,
    });

    expect(classifyError(error)).toBe("selection_failed");
    expect(buildErrorDisplayModel(error).title).toBe("Selection failed");
  });

  it("uses unknown internal error only as the final fallback", () => {
    const error = makeBackendError({
      message: "Resume generation failed.",
      backend_detail: undefined,
      failure_type: undefined,
      failure_category: undefined,
      stage_name: undefined,
      error_source: "backend",
    });

    expect(classifyError(error)).toBe("unknown_internal_error");
  });
});
