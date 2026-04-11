import type { PipelineProgressEvent } from "../types/pipeline";

export interface ProgressStreamSubscription {
  close: () => void;
}

export interface ProgressStreamOptions {
  baseUrl?: string;
  onEvent: (event: PipelineProgressEvent) => void;
  onError?: (error: Event) => void;
  onOpen?: () => void;
}

export function subscribeToPipelineProgress(
  runId: string,
  options: ProgressStreamOptions,
): ProgressStreamSubscription {
  const baseUrl = options.baseUrl ?? "";
  const source = new EventSource(`${baseUrl}/api/pipeline-runs/${encodeURIComponent(runId)}/events`);

  source.onopen = () => {
    options.onOpen?.();
  };
  source.onerror = (error) => {
    options.onError?.(error);
  };

  const eventTypes = [
    "run_started",
    "stage_started",
    "stage_progress",
    "stage_completed",
    "stage_failed",
    "retry_scheduled",
    "fallback_applied",
    "run_completed",
    "run_failed",
  ];

  for (const eventType of eventTypes) {
    source.addEventListener(eventType, (message) => {
      const eventMessage = message as MessageEvent<string>;
      try {
        options.onEvent(JSON.parse(eventMessage.data) as PipelineProgressEvent);
      } catch {
        options.onError?.(message);
      }
    });
  }

  return {
    close: () => {
      source.close();
    },
  };
}
