import { useEffect } from "react";

import { subscribeToPipelineProgress } from "../services/progressStream";
import type {
  PipelineProgressEvent,
  ProgressConnectionState,
} from "../types/pipeline";

export interface UsePipelineProgressOptions {
  baseUrl?: string;
  enabled?: boolean;
  onEvent: (event: PipelineProgressEvent) => void;
  onConnectionChange?: (connection: ProgressConnectionState) => void;
}

export function usePipelineProgress(
  runId: string | undefined,
  options: UsePipelineProgressOptions,
) {
  const { baseUrl, enabled, onConnectionChange, onEvent } = options;

  useEffect(() => {
    // Keep transport orchestration here so polling fallback can replace or
    // supplement SSE later without changing route or component code.
    const shouldEnable = Boolean(runId) && enabled !== false;
    if (!runId || !shouldEnable) {
      onConnectionChange?.({
        enabled: false,
        connected: false,
        transport: "none",
      });
      return;
    }

    onConnectionChange?.({
      enabled: true,
      connected: false,
      transport: "sse",
    });

    const subscription = subscribeToPipelineProgress(runId, {
      baseUrl,
      onOpen: () => {
        onConnectionChange?.({
          enabled: true,
          connected: true,
          transport: "sse",
        });
      },
      onError: (message) => {
        onConnectionChange?.({
          enabled: true,
          connected: false,
          transport: "sse",
          last_error: message,
        });
      },
      onEvent: (event) => {
        onEvent(event);
      },
    });

    return () => {
      subscription.close();
      onConnectionChange?.({
        enabled: true,
        connected: false,
        transport: "sse",
      });
    };
  }, [baseUrl, enabled, onConnectionChange, onEvent, runId]);
}
