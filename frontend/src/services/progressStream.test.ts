import {
  parsePipelineProgressEvent,
  subscribeToPipelineProgress,
} from "./progressStream";

describe("progressStream", () => {
  it("normalizes phase progress payloads into UI-friendly events", () => {
    const event = parsePipelineProgressEvent({
      raw: {
        event_id: "evt-1",
        run_id: "run.progress",
        event_type: "stage_progress",
        stage_name: "verify_generated_content",
        human_message: "Verification in progress",
        machine_status: "running",
        progress_percent: 52,
      },
    });

    expect(event).toEqual(
      expect.objectContaining({
        event_type: "stage_progress",
        run_id: "run.progress",
        stage_name: "verify_generated_content",
        progress_percent: 52,
      }),
    );
  });

  it("maps warning-like malformed payloads into warning events instead of crashing", () => {
    const event = parsePipelineProgressEvent({
      raw: {
        run_id: "run.warning",
        warning_code: "verification_warning",
        message: "Claim needs review.",
        timestamp: "2026-04-12T10:00:00.000Z",
      },
    });

    expect(event).toEqual(
      expect.objectContaining({
        event_type: "warning",
        human_message: "Claim needs review.",
      }),
    );
  });

  it("returns null for malformed payloads missing required run context", () => {
    expect(
      parsePipelineProgressEvent({
        raw: { event_type: "stage_started", human_message: "Started" },
      }),
    ).toBeNull();
  });

  it("isolates transport cleanup for SSE subscriptions", () => {
    const close = vi.fn();
    const addEventListener = vi.fn();
    const source = {
      onopen: null,
      onerror: null,
      onmessage: null,
      addEventListener,
      close,
    } as unknown as EventSource;

    const subscription = subscribeToPipelineProgress("run.cleanup", {
      eventSourceFactory: () => source,
      onEvent: vi.fn(),
    });

    subscription.close();

    expect(subscription.transport).toBe("sse");
    expect(addEventListener).toHaveBeenCalled();
    expect(close).toHaveBeenCalled();
  });

  it("builds the SSE URL from an explicit API base URL when provided", () => {
    const close = vi.fn();
    const addEventListener = vi.fn();
    const eventSourceFactory = vi.fn(() => ({
      onopen: null,
      onerror: null,
      onmessage: null,
      addEventListener,
      close,
    })) as unknown as (url: string) => EventSource;

    subscribeToPipelineProgress("run.base-url", {
      baseUrl: "http://localhost:8000/",
      eventSourceFactory,
      onEvent: vi.fn(),
    });

    expect(eventSourceFactory).toHaveBeenCalledWith(
      "http://localhost:8000/api/pipeline-runs/run.base-url/events",
    );
  });
});
