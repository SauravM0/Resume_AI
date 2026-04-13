import { resumeGenerationReducer } from "./resumeGenerationState";
import {
  makeBackendError,
  makeGenerateRequest,
  makeGenerateResponse,
  makeGenerationResult,
  makeProgressEvent,
  makeResumeGenerationState,
} from "../test/fixtures/resumeGeneration";

describe("resumeGenerationReducer", () => {
  it("clears stale result and error when a new submission starts", () => {
    const staleResult = makeGenerationResult({
      run_metadata: { run_id: "run.old" },
    });
    const state = makeResumeGenerationState({
      status: "success",
      view: "result",
      result: staleResult,
      error: makeBackendError(),
    });

    const next = resumeGenerationReducer(state, {
      type: "submitting",
      request: makeGenerateRequest({ pipeline_run_id: "run.new" }),
      runId: "run.new",
    });

    expect(next.status).toBe("submitting");
    expect(next.view).toBe("progress");
    expect(next.result).toBeNull();
    expect(next.error).toBeNull();
    expect(next.run?.run_id).toBe("run.new");
  });

  it("maps partial success responses into result view", () => {
    const next = resumeGenerationReducer(makeResumeGenerationState(), {
      type: "response_received",
      response: makeGenerateResponse({
        run_id: "run.partial",
        status: "succeeded_with_warnings",
        warnings: ["Review before using."],
      }),
    });

    expect(next.status).toBe("partial_success");
    expect(next.view).toBe("result");
    expect(next.result?.verification_warnings).toHaveLength(1);
  });

  it("preserves completed stages when a later phase fails", () => {
    const started = resumeGenerationReducer(makeResumeGenerationState(), {
      type: "submitting",
      request: makeGenerateRequest({ pipeline_run_id: "run.failure" }),
      runId: "run.failure",
    });

    const withCompletedStage = resumeGenerationReducer(started, {
      type: "progress_event_received",
      event: makeProgressEvent({
        run_id: "run.failure",
        event_type: "stage_completed",
        stage_name: "ingest_job_description",
        machine_status: "succeeded",
        human_message: "Input accepted",
        progress_percent: 10,
      }),
    });

    const failed = resumeGenerationReducer(withCompletedStage, {
      type: "progress_event_received",
      event: makeProgressEvent({
        run_id: "run.failure",
        event_id: "event-failed",
        event_type: "run_failed",
        stage_name: "compile_pdf",
        machine_status: "failed",
        human_message: "PDF compilation failed.",
        metadata: {
          failure_type: "pdf_compile_error",
        },
      }),
    });

    expect(failed.status).toBe("failed");
    expect(failed.view).toBe("error");
    expect(failed.progress?.completed_stages).toHaveLength(1);
    expect(failed.error?.stage_name).toBe("compile_pdf");
  });

  it("resets cleanly after a completed run", () => {
    const completed = makeResumeGenerationState({
      status: "success",
      view: "result",
      result: makeGenerationResult(),
      error: makeBackendError(),
    });

    const reset = resumeGenerationReducer(completed, { type: "reset" });

    expect(reset.status).toBe("idle");
    expect(reset.view).toBe("form");
    expect(reset.result).toBeNull();
    expect(reset.error).toBeNull();
    expect(reset.progress).toBeNull();
  });

  it("does not create a new progress object when the connection state is unchanged", () => {
    const submitting = resumeGenerationReducer(makeResumeGenerationState(), {
      type: "submitting",
      request: makeGenerateRequest({ pipeline_run_id: "run.connection" }),
      runId: "run.connection",
    });

    const next = resumeGenerationReducer(submitting, {
      type: "progress_connection_changed",
      runId: "run.connection",
      connection: {
        enabled: true,
        connected: false,
        transport: "sse",
      },
    });

    expect(next.progress).toBe(submitting.progress);
  });
});
