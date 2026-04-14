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
  summary: "Checking backend health.",
};

export function useSystemReadiness(options: UseSystemReadinessOptions = {}) {
  const [backendHealth, setBackendHealth] = useState<BackendHealthState>(CHECKING_STATE);

  const refresh = useCallback(async () => {
    setBackendHealth({
      status: "checking",
      summary: "Checking backend health.",
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
      label: "Profile path",
      state: options.sourceProfilePath ?? DEFAULT_SOURCE_PROFILE_PATH ? "ready" : "unavailable",
      summary: options.sourceProfilePath ?? DEFAULT_SOURCE_PROFILE_PATH ? "Profile path set." : "No source profile path set.",
      detail:
        options.sourceProfilePath ?? DEFAULT_SOURCE_PROFILE_PATH
          ? `Path: ${options.sourceProfilePath ?? DEFAULT_SOURCE_PROFILE_PATH}. Backend will validate when run starts.`
          : "A source profile path or source profile id is required before generation can start.",
    },
    {
      key: "template",
      label: "Template",
      state: options.templateId ?? DEFAULT_TEMPLATE_ID ? "ready" : "warning",
      summary: options.templateId ?? DEFAULT_TEMPLATE_ID ? "Template set." : "Template not set.",
      detail:
        options.templateId ?? DEFAULT_TEMPLATE_ID
          ? `Template: ${options.templateId ?? DEFAULT_TEMPLATE_ID}. Backend will validate when rendering starts.`
          : "The backend defaults to ats_standard if no template is selected.",
    },
    {
      key: "backend",
      label: "Backend status",
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
