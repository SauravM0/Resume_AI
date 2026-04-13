import { useCallback, useEffect, useRef } from "react";

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
  const onEventRef = useRef(onEvent);
  const onConnectionChangeRef = useRef(onConnectionChange);
  const connectionStateRef = useRef<ProgressConnectionState | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const hasSeenSuccessfulOpenRef = useRef(false);
  const hasSeenTerminalEventRef = useRef(false);
  const isSubscribedRef = useRef(false);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    onConnectionChangeRef.current = onConnectionChange;
  }, [onConnectionChange]);

  const emitConnectionChange = useCallback((nextConnection: ProgressConnectionState) => {
    const previousConnection = connectionStateRef.current;
    if (
      previousConnection?.enabled === nextConnection.enabled &&
      previousConnection?.connected === nextConnection.connected &&
      previousConnection?.transport === nextConnection.transport &&
      previousConnection?.last_error === nextConnection.last_error
    ) {
      return;
    }

    connectionStateRef.current = nextConnection;
    onConnectionChangeRef.current?.(nextConnection);
  }, []);

  const closeActiveSubscription = useCallback((reason: "cleanup" | "reconnect" | "terminal") => {
    if (!isSubscribedRef.current) {
      return;
    }

    if (import.meta.env.DEV) {
      console.debug("[progress] SSE subscribe closed", { runId, reason });
    }

    isSubscribedRef.current = false;
  }, [runId]);

  const classifyTerminalFailure = useCallback((message: string) => {
    if (import.meta.env.DEV) {
      console.debug("[progress] SSE terminal failure classified", {
        runId,
        message,
        attempts: reconnectAttemptRef.current,
        opened: hasSeenSuccessfulOpenRef.current,
      });
    }
  }, [runId]);

  useEffect(() => {
    const shouldEnable = Boolean(runId) && enabled !== false;
    let disposed = false;

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    const scheduleReconnect = (message: string) => {
      const MAX_RECONNECT_ATTEMPTS = 4;
      if (disposed || hasSeenTerminalEventRef.current) {
        return;
      }

      if (reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS) {
        classifyTerminalFailure(message);
        emitConnectionChange({
          enabled: true,
          connected: false,
          transport: "sse",
          last_error: message,
        });
        return;
      }

      reconnectAttemptRef.current += 1;
      const delayMs = Math.min(1000 * 2 ** (reconnectAttemptRef.current - 1), 8000);

      if (import.meta.env.DEV) {
        console.debug("[progress] SSE reconnect attempt", {
          runId,
          attempt: reconnectAttemptRef.current,
          delayMs,
        });
      }

      clearReconnectTimer();
      reconnectTimerRef.current = window.setTimeout(() => {
        reconnectTimerRef.current = null;
        if (!disposed && !hasSeenTerminalEventRef.current) {
          startSubscription();
        }
      }, delayMs);
    };

    const startSubscription = () => {
      if (!runId || !shouldEnable || disposed) {
        return;
      }

      clearReconnectTimer();
      closeActiveSubscription("reconnect");

      emitConnectionChange({
        enabled: true,
        connected: false,
        transport: "sse",
      });

      if (import.meta.env.DEV) {
        console.debug("[progress] SSE subscribe start", {
          runId,
          attempt: reconnectAttemptRef.current,
        });
      }

      const onOpen = () => {
        if (disposed) return;
        hasSeenSuccessfulOpenRef.current = true;
        reconnectAttemptRef.current = 0;
        emitConnectionChange({
          enabled: true,
          connected: true,
          transport: "sse",
        });
      };

      const onError = (message: string, error?: Event | Error) => {
        if (disposed) return;
        const isNotFound =
          error instanceof Event &&
          (error.target as EventSource)?.readyState === EventSource.CLOSED;
        const shouldStopReconnecting =
          isNotFound || message.includes("404") || message.includes("not found");
        if (shouldStopReconnecting) {
          hasSeenTerminalEventRef.current = true;
          clearReconnectTimer();
          emitConnectionChange({
            enabled: true,
            connected: false,
            transport: "sse",
            last_error: message,
          });
          return;
        }
        closeActiveSubscription("reconnect");
        emitConnectionChange({
          enabled: true,
          connected: false,
          transport: "sse",
          last_error: message,
        });
        scheduleReconnect(message);
      };

      const onEventCallback = (event: PipelineProgressEvent) => {
        if (disposed) return;
        if (event.event_type === "run_completed" || event.event_type === "run_failed") {
          hasSeenTerminalEventRef.current = true;
          clearReconnectTimer();
        }
        onEventRef.current(event);
      };

      const subscription = subscribeToPipelineProgress(runId, {
        baseUrl,
        onOpen,
        onError,
        onEvent: onEventCallback,
      });

      isSubscribedRef.current = true;
    };

    if (!runId || !shouldEnable) {
      hasSeenSuccessfulOpenRef.current = false;
      hasSeenTerminalEventRef.current = false;
      reconnectAttemptRef.current = 0;
      clearReconnectTimer();
      emitConnectionChange({
        enabled: false,
        connected: false,
        transport: "none",
      });
      return;
    }

    hasSeenSuccessfulOpenRef.current = false;
    hasSeenTerminalEventRef.current = false;
    reconnectAttemptRef.current = 0;
    startSubscription();

    return () => {
      disposed = true;
      clearReconnectTimer();
      closeActiveSubscription("cleanup");
      emitConnectionChange({
        enabled: true,
        connected: false,
        transport: "sse",
      });
    };
  }, [baseUrl, enabled, runId, emitConnectionChange, closeActiveSubscription, classifyTerminalFailure]);
}
