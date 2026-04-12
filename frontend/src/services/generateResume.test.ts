import {
  generateResume,
  normalizeGenerateResumeError,
  normalizeGenerateResumeResponse,
} from "./generateResume";
import { makeGenerateRequest } from "../test/fixtures/resumeGeneration";

describe("generateResume", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("normalizes a full success payload", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: "run.success",
          status: "succeeded",
          available_outputs: [
            {
              kind: "pdf",
              storage_kind: "url",
              reference: "https://example.com/run.success/resume.pdf",
              file_name: "resume.pdf",
            },
          ],
          selected_experiences: [{ id: "exp-1", title: "Senior Engineer" }],
          selected_projects: [{ id: "proj-1", name: "Resume Engine" }],
          selected_skills: [{ id: "skill-1", name: "TypeScript" }],
          diagnostics: {
            summary: "Completed",
            messages: ["Completed"],
          },
        }),
        { status: 200 },
      ),
    );

    const response = await generateResume(makeGenerateRequest({ pipeline_run_id: "run.success" }));

    expect(response.run_id).toBe("run.success");
    expect(response.status).toBe("succeeded");
    expect(response.available_outputs[0]?.kind).toBe("pdf");
    expect(response.selected_experiences[0]?.title).toBe("Senior Engineer");
  });

  it("normalizes low-detail backend payloads safely", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 }),
    );

    const response = await generateResume(makeGenerateRequest({ pipeline_run_id: "run.low-detail" }));

    expect(response.run_id).toBe("run.low-detail");
    expect(response.status).toBe("pending");
    expect(response.available_outputs).toEqual([]);
    expect(response.selected_skills).toEqual([]);
  });

  it("preserves warnings and diagnostics for partial success payloads", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          run_id: "run.partial",
          status: "succeeded_with_warnings",
          warnings: ["Verification warning detected."],
          verification_warnings: [{ message: "Claim needs review.", severity: "warning" }],
          diagnostics: {
            summary: "Completed with warnings",
            messages: ["Repair path used"],
            failure_type: "verification_warning",
          },
          available_outputs: [
            {
              kind: "structured_json",
              storage_kind: "url",
              reference: "https://example.com/run.partial/result.json",
            },
          ],
        }),
        { status: 200 },
      ),
    );

    const response = await generateResume(makeGenerateRequest({ pipeline_run_id: "run.partial" }));

    expect(response.status).toBe("succeeded_with_warnings");
    expect(response.warnings).toContain("Verification warning detected.");
    expect(response.verification_warnings[0]?.message).toBe("Claim needs review.");
    expect(response.diagnostics?.messages).toContain("Repair path used");
  });

  it("maps phase failure responses into backend errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            message: "Ranking failed.",
            stage_name: "rank_select_evidence",
            failure_type: "ranking_error",
            retryable: true,
          },
        }),
        { status: 500 },
      ),
    );

    await expect(generateResume(makeGenerateRequest({ pipeline_run_id: "run.failed" }))).rejects.toMatchObject({
      message: "Ranking failed.",
      stage_name: "rank_select_evidence",
      failure_type: "ranking_error",
      error_source: "backend",
    });
  });

  it("surfaces transport errors directly when fetch rejects", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Network down"));

    await expect(generateResume(makeGenerateRequest())).rejects.toThrow("Network down");
  });

  it("derives downloadable outputs from artifact metadata when outputs are omitted", () => {
    const response = normalizeGenerateResumeResponse(
      {
        run_id: "run.artifacts",
        status: "succeeded",
        artifact_manifest: [
          {
            artifact_id: "artifact.pdf",
            kind: "pdf",
            stage_name: "compile_pdf",
            storage_backend: "url",
            schema_version: "1",
            uri: "https://example.com/run.artifacts/resume.pdf",
            content_type: "application/pdf",
            size_bytes: 1024,
          },
        ],
      },
      makeGenerateRequest({ pipeline_run_id: "run.artifacts" }),
    );

    expect(response.available_outputs).toEqual([
      expect.objectContaining({
        kind: "pdf",
        reference: "https://example.com/run.artifacts/resume.pdf",
      }),
    ]);
  });

  it("normalizes backend error diagnostics safely when messages are inconsistent", () => {
    const error = normalizeGenerateResumeError(
      {
        detail: {
          message: "Verification failed.",
          failure_type: "verification_error",
          warnings: [{ message: "Claim missing evidence." }],
          fallback_repairs: [{ strategy: "safe_claim_filter" }],
        },
      },
      500,
    );

    expect(error.message).toBe("Verification failed.");
    expect(error.diagnostics?.warnings[0]?.message).toBe("Claim missing evidence.");
    expect(error.diagnostics?.fallback_repairs[0]?.strategy).toBe("safe_claim_filter");
  });
});
