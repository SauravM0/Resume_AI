import { act, renderHook } from "@testing-library/react";

import { usePipelineProgress } from "./usePipelineProgress";
import { subscribeToPipelineProgress } from "../services/progressStream";
import type {
  PipelineProgressEvent,
  ProgressConnectionState,
} from "../types/pipeline";

vi.mock("../services/progressStream", () => ({
  subscribeToPipelineProgress: vi.fn(),
}));

describe("usePipelineProgress", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(console, "debug").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("creates one subscription for one run and does not resubscribe on callback identity changes", () => {
    const close = vi.fn();
    vi.mocked(subscribeToPipelineProgress).mockReturnValue({
      close,
      transport: "sse",
    });

    const { rerender } = renderHook(
      ({
        runId,
        onEvent,
        onConnectionChange,
      }: {
        runId?: string;
        onEvent: (event: PipelineProgressEvent) => void;
        onConnectionChange: (connection: ProgressConnectionState) => void;
      }) =>
        usePipelineProgress(runId, {
          enabled: true,
          onEvent,
          onConnectionChange,
        }),
      {
        initialProps: {
          runId: "run.stable",
          onEvent: vi.fn(),
          onConnectionChange: vi.fn(),
        },
      },
    );

    rerender({
      runId: "run.stable",
      onEvent: vi.fn(),
      onConnectionChange: vi.fn(),
    });

    expect(subscribeToPipelineProgress).toHaveBeenCalledTimes(1);
    expect(close).not.toHaveBeenCalled();
  });

  it("closes the previous stream before subscribing to a new run", () => {
    const firstClose = vi.fn();
    const secondClose = vi.fn();

    vi.mocked(subscribeToPipelineProgress)
      .mockReturnValueOnce({
        close: firstClose,
        transport: "sse",
      })
      .mockReturnValueOnce({
        close: secondClose,
        transport: "sse",
      });

    const { rerender, unmount } = renderHook(
      ({ runId }: { runId?: string }) =>
        usePipelineProgress(runId, {
          enabled: true,
          onEvent: vi.fn(),
          onConnectionChange: vi.fn(),
        }),
      {
        initialProps: {
          runId: "run.one",
        },
      },
    );

    rerender({ runId: "run.two" });

    expect(subscribeToPipelineProgress).toHaveBeenCalledTimes(2);
    expect(firstClose).toHaveBeenCalledTimes(1);

    unmount();

    expect(secondClose).toHaveBeenCalledTimes(1);
  });

  it("caps reconnect attempts and stops resubscribing after terminal transport failure", () => {
    const subscriptions: Array<{ close: ReturnType<typeof vi.fn> }> = [];

    vi.mocked(subscribeToPipelineProgress).mockImplementation((_runId, options) => {
      const subscription = {
        close: vi.fn(),
        transport: "sse" as const,
      };
      subscriptions.push(subscription);
      return subscription;
    });

    renderHook(() =>
      usePipelineProgress("run.retry", {
        enabled: true,
        onEvent: vi.fn(),
        onConnectionChange: vi.fn(),
      }),
    );

    for (let attempt = 0; attempt < 4; attempt += 1) {
      const latestOptions = vi.mocked(subscribeToPipelineProgress).mock.calls.at(-1)?.[1];
      expect(latestOptions).toBeDefined();

      act(() => {
        latestOptions?.onError?.("Progress stream disconnected.");
      });

      act(() => {
        vi.advanceTimersByTime(Math.min(1000 * 2 ** attempt, 8000));
      });
    }

    const terminalOptions = vi.mocked(subscribeToPipelineProgress).mock.calls.at(-1)?.[1];
    act(() => {
      terminalOptions?.onError?.("Progress stream disconnected.");
    });

    act(() => {
      vi.advanceTimersByTime(16000);
    });

    expect(subscribeToPipelineProgress).toHaveBeenCalledTimes(5);
    expect(subscriptions).toHaveLength(5);
  });

  it("stops retrying on 404 missing run", () => {
    const close = vi.fn();
    vi.mocked(subscribeToPipelineProgress).mockReturnValue({
      close,
      transport: "sse",
    });

    renderHook(() =>
      usePipelineProgress("run.notfound", {
        enabled: true,
        onEvent: vi.fn(),
        onConnectionChange: vi.fn(),
      }),
    );

    const options = vi.mocked(subscribeToPipelineProgress).mock.calls[0]?.[1];
    act(() => {
      options?.onError?.("404 Not Found");
    });

    act(() => {
      vi.advanceTimersByTime(10000);
    });

    expect(subscribeToPipelineProgress).toHaveBeenCalledTimes(1);
  });

  it("stops retrying after receiving terminal run_failed event", () => {
    const close = vi.fn();
    vi.mocked(subscribeToPipelineProgress).mockReturnValue({
      close,
      transport: "sse",
    });

    const { unmount } = renderHook(() =>
      usePipelineProgress("run.failed", {
        enabled: true,
        onEvent: vi.fn(),
        onConnectionChange: vi.fn(),
      }),
    );

    const options = vi.mocked(subscribeToPipelineProgress).mock.calls[0]?.[1];
    act(() => {
      options?.onEvent?.({
        event_id: "run_failed.run.failed",
        run_id: "run.failed",
        event_type: "run_failed",
        machine_status: "failed",
        human_message: "Job description could not be parsed",
        timestamp: new Date().toISOString(),
      });
    });

    act(() => {
      vi.advanceTimersByTime(10000);
    });

    expect(subscribeToPipelineProgress).toHaveBeenCalledTimes(1);

    unmount();
  });
});
