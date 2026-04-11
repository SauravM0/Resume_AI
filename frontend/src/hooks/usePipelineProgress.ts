import { useEffect, useMemo, useState } from "react";

import { subscribeToPipelineProgress } from "../services/progressStream";
import type {
  PipelineProgressEvent,
  PipelineProgressState,
  PipelineStageProgress,
} from "../types/pipeline";
import { PIPELINE_STAGE_ORDER } from "../types/pipeline";

export interface UsePipelineProgressOptions {
  baseUrl?: string;
  enabled?: boolean;
}

export function usePipelineProgress(
  runId: string | undefined,
  options: UsePipelineProgressOptions = {},
): PipelineProgressState {
  const [events, setEvents] = useState<PipelineProgressEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | undefined>();

  useEffect(() => {
    setEvents([]);
    setConnected(false);
    setError(undefined);
    if (!runId || options.enabled === false) {
      return;
    }

    const subscription = subscribeToPipelineProgress(runId, {
      baseUrl: options.baseUrl,
      onOpen: () => setConnected(true),
      onError: () => {
        setConnected(false);
        setError("Progress stream disconnected.");
      },
      onEvent: (event) => {
        setEvents((current) => [...current, event]);
      },
    });

    return () => {
      subscription.close();
      setConnected(false);
    };
  }, [runId, options.baseUrl, options.enabled]);

  return useMemo(() => buildProgressState(runId ?? "", events, connected, error), [
    connected,
    error,
    events,
    runId,
  ]);
}

function buildProgressState(
  runId: string,
  events: PipelineProgressEvent[],
  connected: boolean,
  error: string | undefined,
): PipelineProgressState {
  const latestEvent = events.at(-1);
  const stagesByName = new Map<string, PipelineStageProgress>();

  for (const event of events) {
    if (!event.stage_name) {
      continue;
    }
    stagesByName.set(event.stage_name, {
      stage_name: event.stage_name,
      machine_status: event.machine_status,
      human_message: event.human_message,
      progress_percent: event.progress_percent,
      updated_at: event.timestamp,
      attempt_number: readAttemptNumber(event),
      failure_type: readStringMetadata(event, "failure_type"),
      retryable: readBooleanMetadata(event, "retryable"),
      fallback_eligible: readBooleanMetadata(event, "fallback_eligible"),
    });
  }

  const stages = PIPELINE_STAGE_ORDER.flatMap((stageName) => {
    const stage = stagesByName.get(stageName);
    return stage ? [stage] : [];
  });
  const terminal = latestEvent?.event_type === "run_completed" || latestEvent?.event_type === "run_failed";
  const progressPercent = latestEvent?.progress_percent ?? stages.at(-1)?.progress_percent ?? 0;
  const currentStage = [...stages].reverse().find((stage) => {
    return !["succeeded", "failed", "blocked", "skipped"].includes(String(stage.machine_status));
  }) ?? stages.at(-1);
  const completedStages = stages.filter((stage) => stage.machine_status === "succeeded");
  const retryNotices = events.filter((event) => event.event_type === "retry_scheduled");
  const fallbackNotices = events.filter((event) => event.event_type === "fallback_applied" || event.metadata?.fallback_strategy);

  return {
    run_id: runId,
    events,
    stages,
    latest_event: latestEvent,
    progress_percent: progressPercent,
    connected,
    terminal,
    current_stage: currentStage,
    completed_stages: completedStages,
    retry_notices: retryNotices,
    fallback_notices: fallbackNotices,
    error,
  };
}

function readAttemptNumber(event: PipelineProgressEvent): number | undefined {
  const value = event.metadata?.attempt_number;
  return typeof value === "number" ? value : undefined;
}

function readStringMetadata(event: PipelineProgressEvent, key: string): string | undefined {
  const value = event.metadata?.[key];
  return typeof value === "string" ? value : undefined;
}

function readBooleanMetadata(event: PipelineProgressEvent, key: string): boolean | undefined {
  const value = event.metadata?.[key];
  return typeof value === "boolean" ? value : undefined;
}
