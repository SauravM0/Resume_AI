import { useCallback, useEffect, useState } from "react";

import {
  DEFAULT_SOURCE_PROFILE_PATH,
  DEFAULT_TEMPLATE_ID,
} from "../constants/resumeGeneration";
import { probeBackendHealth } from "../services/systemHealth";
import type {
  BackendHealthState,
  ReadinessIndicator,
} from "../types/pipeline";

export interface UseSystemReadinessOptions {
  baseUrl?: string;
  sourceProfilePath?: string;
  templateId?: string;
}

const CHECKING_STATE: BackendHealthState = {
  status: "checking",
  summary: "Checking backend reachability.",
};

export function useSystemReadiness(options: UseSystemReadinessOptions = {}) {
  const [backendHealth, setBackendHealth] = useState<BackendHealthState>(CHECKING_STATE);

  const refresh = useCallback(async () => {
    setBackendHealth({
      status: "checking",
      summary: "Checking backend reachability.",
    });

    const result = await probeBackendHealth({ baseUrl: options.baseUrl });
    setBackendHealth(result);
  }, [options.baseUrl]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const readiness: ReadinessIndicator[] = [
    {
      key: "master-profile",
      label: "Master profile",
      state: options.sourceProfilePath ?? DEFAULT_SOURCE_PROFILE_PATH ? "ready" : "unavailable",
      summary: options.sourceProfilePath ?? DEFAULT_SOURCE_PROFILE_PATH ? "Profile path configured." : "No source profile path configured.",
      detail:
        options.sourceProfilePath ?? DEFAULT_SOURCE_PROFILE_PATH
          ? `Configured path: ${options.sourceProfilePath ?? DEFAULT_SOURCE_PROFILE_PATH}. Final validation happens when the backend loads the profile.`
          : "A source profile path or source profile id is required before generation can start.",
    },
    {
      key: "template",
      label: "Template",
      state: options.templateId ?? DEFAULT_TEMPLATE_ID ? "ready" : "warning",
      summary: options.templateId ?? DEFAULT_TEMPLATE_ID ? "Template configured." : "Template not configured.",
      detail:
        options.templateId ?? DEFAULT_TEMPLATE_ID
          ? `Configured template: ${options.templateId ?? DEFAULT_TEMPLATE_ID}. Template availability is confirmed by the backend during execution.`
          : "The backend currently defaults to ats_standard if no template is selected.",
    },
    {
      key: "backend",
      label: "Backend",
      state:
        backendHealth.status === "healthy"
          ? "ready"
          : backendHealth.status === "checking"
            ? "unknown"
            : backendHealth.status === "degraded"
              ? "warning"
              : "unavailable",
      summary: backendHealth.summary,
      detail: backendHealth.detail,
    },
  ];

  return {
    backendHealth,
    readiness,
    refresh,
  };
}
