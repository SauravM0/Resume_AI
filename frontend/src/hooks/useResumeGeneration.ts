import { useCallback, useMemo, useState } from "react";

import {
  createPipelineRunId,
  generateResume,
} from "../services/generateResume";
import type {
  GenerateResumeRequest,
  GenerateResumeResponse,
  ResumeGenerationError,
  ResumeGenerationState,
} from "../types/pipeline";
import { usePipelineProgress } from "./usePipelineProgress";

export interface UseResumeGenerationOptions {
  baseUrl?: string;
  defaultSourceProfilePath?: string;
  defaultTemplateId?: string;
}

export function useResumeGeneration(options: UseResumeGenerationOptions = {}) {
  const [runId, setRunId] = useState<string | undefined>();
  const [response, setResponse] = useState<GenerateResumeResponse | undefined>();
  const [error, setError] = useState<ResumeGenerationError | undefined>();
  const [submitting, setSubmitting] = useState(false);
  const progress = usePipelineProgress(runId, {
    baseUrl: options.baseUrl,
    enabled: Boolean(runId),
  });

  const submit = useCallback(
    async (request: Omit<GenerateResumeRequest, "pipeline_run_id"> & { pipeline_run_id?: string }) => {
      const resolvedRunId = request.pipeline_run_id ?? createPipelineRunId();
      setRunId(resolvedRunId);
      setResponse(undefined);
      setError(undefined);
      setSubmitting(true);

      try {
        const result = await generateResume(
          {
            template_id: options.defaultTemplateId ?? "ats_standard",
            source_profile_path: options.defaultSourceProfilePath ?? "data/master_profile.example.json",
            ...request,
            pipeline_run_id: resolvedRunId,
          },
          { baseUrl: options.baseUrl },
        );
        setResponse(result);
        return result;
      } catch (caught) {
        const normalizedError = normalizeCaughtError(caught);
        setError(normalizedError);
        if (normalizedError.run_id && !runId) {
          setRunId(normalizedError.run_id);
        }
        throw normalizedError;
      } finally {
        setSubmitting(false);
      }
    },
    [options.baseUrl, options.defaultSourceProfilePath, options.defaultTemplateId, runId],
  );

  const reset = useCallback(() => {
    setRunId(undefined);
    setResponse(undefined);
    setError(undefined);
    setSubmitting(false);
  }, []);

  const state: ResumeGenerationState = useMemo(() => {
    return {
      run_id: runId,
      overall_status: computeOverallStatus({ submitting, response, error, progress }),
      submitting,
      response,
      error,
      warnings: response?.warnings ?? [],
      final_outputs: response?.available_outputs ?? [],
      progress,
    };
  }, [error, progress, response, runId, submitting]);

  return {
    state,
    submit,
    reset,
  };
}

function normalizeCaughtError(caught: unknown): ResumeGenerationError {
  if (typeof caught === "object" && caught !== null && "message" in caught) {
    return caught as ResumeGenerationError;
  }
  return { message: "Resume generation failed." };
}

function computeOverallStatus(input: {
  submitting: boolean;
  response?: GenerateResumeResponse;
  error?: ResumeGenerationError;
  progress: ResumeGenerationState["progress"];
}): ResumeGenerationState["overall_status"] {
  if (input.response?.status) {
    return input.response.status;
  }
  if (input.error?.stage_name || input.error?.message) {
    return input.error.status_code === 409 ? "blocked" : "failed";
  }
  if (input.submitting || input.progress.events.length > 0) {
    return "running";
  }
  return "idle";
}
