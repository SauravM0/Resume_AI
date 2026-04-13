import { useEffect, useMemo, useReducer, useRef } from "react";
import { useCallback } from "react";

import {
  DEFAULT_SOURCE_PROFILE_PATH,
  DEFAULT_TEMPLATE_ID,
} from "../constants/resumeGeneration";
import {
  createPipelineRunId,
  generateResume,
} from "../services/generateResume";
import {
  createInitialResumeGenerationState,
  resumeGenerationReducer,
  validateGenerateRequest,
} from "../state/resumeGenerationState";
import type {
  BackendErrorPayload,
  GenerateResumeRequest,
  GenerateResumeResponse,
  GenerationResultData,
  PhaseStatus,
  PipelineProgressEvent,
  ProgressConnectionState,
  ResumeGenerationRunStatus,
  RunMetadata,
} from "../types/pipeline";
import { getOutputByKind } from "../utils/artifactLinks";
import { usePipelineProgress } from "./usePipelineProgress";

export interface UseResumeGenerationOptions {
  baseUrl?: string;
  defaultSourceProfilePath?: string;
  defaultTemplateId?: string;
}

export interface UseResumeGenerationSubmitInput
  extends Omit<GenerateResumeRequest, "pipeline_run_id"> {
  pipeline_run_id?: string;
}

export interface UseResumeGenerationController {
  state: ReturnType<typeof createInitialResumeGenerationState>;
  run: RunMetadata | null;
  progress: ReturnType<typeof createInitialResumeGenerationState>["progress"];
  currentPhase: PhaseStatus | null;
  completedPhases: PhaseStatus[];
  status: ResumeGenerationRunStatus;
  error: BackendErrorPayload | null;
  result: GenerationResultData | null;
  debugVisible: boolean;
  isLoading: boolean;
  isRunning: boolean;
  isRetrying: boolean;
  isSuccess: boolean;
  isPartialSuccess: boolean;
  isFailure: boolean;
  isValidationError: boolean;
  isTransportError: boolean;
  isHardFailure: boolean;
  hasDiagnostics: boolean;
  hasArtifacts: boolean;
  canDownloadPdf: boolean;
  usedFallback: boolean;
  submit: (request: UseResumeGenerationSubmitInput) => Promise<GenerateResumeResponse>;
  retry: () => Promise<GenerateResumeResponse | undefined>;
  cancel: () => void;
  reset: () => void;
  toggleDebug: (visible?: boolean) => void;
}

export function useResumeGeneration(options: UseResumeGenerationOptions = {}) {
  const [state, dispatch] = useReducer(
    resumeGenerationReducer,
    undefined,
    createInitialResumeGenerationState,
  );
  const abortControllerRef = useRef<AbortController | null>(null);

  const currentRunId = state.run?.run_id;
  const shouldSubscribe = Boolean(
    currentRunId && state.status !== "idle" && state.status !== "cancelled",
  );

  const handleProgressEvent = useCallback((event: PipelineProgressEvent) => {
    dispatch({ type: "progress_event_received", event });
  }, []);

  const handleProgressConnectionChange = useCallback((connection: ProgressConnectionState) => {
    if (!currentRunId) {
      return;
    }

    dispatch({
      type: "progress_connection_changed",
      runId: currentRunId,
      connection,
    });
  }, [currentRunId]);

  usePipelineProgress(currentRunId, {
    baseUrl: options.baseUrl,
    enabled: shouldSubscribe,
    onEvent: handleProgressEvent,
    onConnectionChange: handleProgressConnectionChange,
  });

  const submit = useCallback(
    async (
      request: UseResumeGenerationSubmitInput,
    ): Promise<GenerateResumeResponse> => {
      const normalizedRequest: GenerateResumeRequest = {
        template_id: options.defaultTemplateId ?? DEFAULT_TEMPLATE_ID,
        source_profile_path: options.defaultSourceProfilePath ?? DEFAULT_SOURCE_PROFILE_PATH,
        persist_intermediate_artifacts: true,
        ...request,
        job_description_text: request.job_description_text.trim(),
        job_posting_url: request.job_posting_url?.trim() || undefined,
      };

      dispatch({ type: "validating", request: normalizedRequest });
      const validationErrors = validateGenerateRequest(normalizedRequest);
      if (validationErrors.length > 0) {
        dispatch({
          type: "validation_failed",
          request: normalizedRequest,
          errors: validationErrors,
        });
        const validationError: BackendErrorPayload = {
          message: validationErrors.join(" "),
          error_source: "validation",
        };
        throw validationError;
      }

      abortControllerRef.current?.abort();
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      const resolvedRunId = normalizedRequest.pipeline_run_id ?? createPipelineRunId();
      const requestWithRunId = {
        ...normalizedRequest,
        pipeline_run_id: resolvedRunId,
      };

      dispatch({
        type: "submitting",
        request: requestWithRunId,
        runId: resolvedRunId,
      });

      try {
        const response = await generateResume(requestWithRunId, {
          baseUrl: options.baseUrl,
          signal: abortController.signal,
        });
        dispatch({ type: "response_received", response });
        return response;
      } catch (caught) {
        if (abortController.signal.aborted) {
          dispatch({
            type: "cancelled",
            reason: "Request cancelled from the client. The backend run may still continue.",
          });
          throw {
            message: "Request cancelled from the client.",
            run_id: resolvedRunId,
            error_source: "transport",
          } satisfies BackendErrorPayload;
        }

        const normalizedError = normalizeCaughtError(caught);
        dispatch({
          type: "submit_failed",
          error: normalizedError,
          runId: normalizedError.run_id ?? resolvedRunId,
        });
        throw normalizedError;
      }
    },
    [options.baseUrl, options.defaultSourceProfilePath, options.defaultTemplateId],
  );

  const retry = useCallback(async () => {
    if (!state.submitted_request) {
      return undefined;
    }
    dispatch({ type: "retry_started" });
    try {
      return await submit({
        ...state.submitted_request,
        pipeline_run_id: createPipelineRunId(),
      });
    } finally {
      dispatch({ type: "retry_finished" });
    }
  }, [state.submitted_request, submit]);

  const cancel = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
  }, []);

  const reset = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    dispatch({ type: "reset" });
  }, []);

  const toggleDebug = useCallback((visible?: boolean) => {
    dispatch({ type: "debug_toggled", visible });
  }, []);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const controller = useMemo<UseResumeGenerationController>(() => {
    const status = state.status;
    const run = state.run;
    const progress = state.progress;
    const result = state.result;
    const error = state.error;
    const currentPhase = state.current_phase;
    const completedPhases = progress?.completed_stages ?? [];
    const diagnostics =
      result?.diagnostics ?? error?.diagnostics ?? undefined;
    const hasArtifacts =
      (result?.render_artifacts.length ?? 0) > 0 ||
      (result?.downloadable_outputs.length ?? 0) > 0;
    const pdfOutput = result ? getOutputByKind(result, "pdf") : undefined;
    const usedFallback = Boolean(
      diagnostics?.fallback_repairs.some((repair) => repair.applied) ||
        progress?.fallback_notices.length,
    );
    const isRunning = [
      "submitting",
      "queued",
      "phase_running",
      "phase_completed",
    ].includes(status);
    const isLoading = status === "validating_input" || isRunning || state.retrying;
    const isSuccess = status === "success";
    const isPartialSuccess = status === "partial_success";
    const isFailure = status === "failed" || status === "cancelled";

    return {
      state,
      run,
      progress,
      currentPhase,
      completedPhases,
      status,
      error,
      result,
      debugVisible: state.debug_visible,
      isLoading,
      isRunning,
      isRetrying: state.retrying,
      isSuccess,
      isPartialSuccess,
      isFailure,
      isValidationError: error?.error_source === "validation",
      isTransportError: error?.error_source === "transport",
      isHardFailure: status === "failed" && !isPartialSuccess,
      hasDiagnostics: Boolean(
        diagnostics &&
          (diagnostics.summary ||
            diagnostics.messages.length > 0 ||
            diagnostics.warnings.length > 0 ||
            diagnostics.fallback_repairs.length > 0),
      ),
      hasArtifacts,
      canDownloadPdf: Boolean(pdfOutput?.reference),
      usedFallback,
      submit,
      retry,
      cancel,
      reset,
      toggleDebug,
    };
  }, [cancel, reset, retry, state, submit, toggleDebug]);

  return controller;
}

function normalizeCaughtError(caught: unknown): BackendErrorPayload {
  if (typeof caught === "object" && caught !== null && "message" in caught) {
    return caught as BackendErrorPayload;
  }
  return { message: "Resume generation failed.", error_source: "frontend" };
}
