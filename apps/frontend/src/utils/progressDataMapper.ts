import type {
  PhaseStatus,
  PipelineMachineStatus,
  PipelineProgressEvent,
  PipelineProgressState,
  ProgressPhaseKey,
  ProgressPhaseStatus,
  ProgressPhaseViewModel,
  ResumeGenerationRunStatus,
  RunMetadata,
  RunProgressOverview,
} from "../types/pipeline";
import { getElapsedSeconds } from "./timingFormatters";

interface PhaseDefinition {
  key: ProgressPhaseKey;
  label: string;
  description: string;
  stageNames: string[];
  userCopy: string;
}

const PHASE_DEFINITIONS: PhaseDefinition[] = [
  {
    key: "input_accepted",
    label: "Input accepted",
    description: "The run has been accepted and initial orchestration has started.",
    stageNames: ["load_source_profile"],
    userCopy: "Accepting your request and loading source data",
  },
  {
    key: "job_description_analysis",
    label: "Job description analysis",
    description: "Reading job requirements and structuring the target role input.",
    stageNames: ["normalize_source_data", "ingest_job_description", "parse_job_description"],
    userCopy: "Reading job requirements",
  },
  {
    key: "evidence_extraction_ranking",
    label: "Evidence extraction / ranking",
    description: "Matching the strongest evidence from the source profile.",
    stageNames: ["rank_select_evidence"],
    userCopy: "Matching the strongest evidence from your profile",
  },
  {
    key: "content_generation",
    label: "Content generation",
    description: "Preparing a structured resume draft from the selected evidence.",
    stageNames: ["generate_structured_content"],
    userCopy: "Preparing a structured resume draft",
  },
  {
    key: "verification_repair",
    label: "Verification / repair",
    description: "Checking claims, warnings, and any repair or fallback steps before rendering.",
    stageNames: ["verify_generated_content"],
    userCopy: "Verifying claims before rendering",
  },
  {
    key: "rendering_pdf_assembly",
    label: "Rendering / PDF assembly",
    description: "Building the deterministic LaTeX document and final PDF outputs.",
    stageNames: ["render_deterministic_latex", "compile_pdf"],
    userCopy: "Building the final PDF",
  },
  {
    key: "finalization",
    label: "Finalization",
    description: "Persisting final artifacts and closing out the run.",
    stageNames: ["persist_artifacts"],
    userCopy: "Finalizing outputs and artifacts",
  },
];

export function buildRunProgressOverview(input: {
  progress: PipelineProgressState;
  run: RunMetadata | null;
  overallStatus: ResumeGenerationRunStatus;
}): RunProgressOverview {
  const timeoutWarning = findEventMessage(input.progress.events, "timeout");
  const retryInProgress =
    input.progress.stages.some((stage) => stage.machine_status === "retrying") ||
    input.progress.retry_notices.length > 0;
  const partialRecovery =
    input.progress.fallback_notices.length > 0 ||
    input.progress.stages.some((stage) => stage.fallback_metadata?.applied);
  const hardFailure =
    input.overallStatus === "failed" ||
    input.progress.events.some((event) => event.event_type === "run_failed");
  const runHealth = hardFailure ? "failed" : timeoutWarning || retryInProgress || partialRecovery ? "warning" : "healthy";

  return {
    run_id: input.progress.run_id,
    overall_status: input.overallStatus,
    started_at: input.run?.started_at,
    elapsed_seconds: getElapsedSeconds(input.run?.started_at, input.run?.finished_at),
    current_backend_message: input.progress.latest_event?.human_message,
    run_health: runHealth,
    run_health_text:
      runHealth === "healthy"
        ? "Run is progressing normally."
        : runHealth === "warning"
          ? "Run is still active but has warnings, retries, or fallback behavior."
          : "Run has failed and requires attention.",
    queued: input.overallStatus === "queued",
    timeout_warning: timeoutWarning,
    retry_in_progress: retryInProgress,
    partial_recovery: partialRecovery,
    hard_failure: hardFailure,
    connection: input.progress.connection,
  };
}

export function buildProgressPhases(progress: PipelineProgressState): ProgressPhaseViewModel[] {
  return PHASE_DEFINITIONS.map((definition) => {
    const backendStages = definition.stageNames.flatMap((stageName) => {
      const stage = progress.stages.find((item) => item.stage_name === stageName);
      return stage ? [stage] : [];
    });

    const phaseStatus = mapPhaseStatus(backendStages);
    const lastStage = backendStages[backendStages.length - 1];
    const fallbackUsed = backendStages.some(
      (stage) =>
        stage.fallback_metadata?.applied ||
        typeof stage.metadata?.fallback_strategy === "string",
    );
    const retryInProgress = backendStages.some((stage) => stage.machine_status === "retrying");
    const warningText = readWarningText(backendStages);

    return {
      key: definition.key,
      label: definition.label,
      description: definition.userCopy,
      status: phaseStatus,
      updated_at: lastStage?.updated_at,
      elapsed_seconds: getPhaseElapsedSeconds(backendStages),
      detail_text: lastStage?.human_message ?? definition.description,
      backend_stages: backendStages,
      fallback_used: fallbackUsed,
      retry_in_progress: retryInProgress,
      warning_text: warningText,
      failed: phaseStatus === "failed",
    };
  });
}

function mapPhaseStatus(stages: PhaseStatus[]): ProgressPhaseStatus {
  if (stages.length === 0) {
    return "pending";
  }

  if (stages.some((stage) => stage.machine_status === "failed" || stage.machine_status === "blocked")) {
    return "failed";
  }

  if (stages.some((stage) => stage.machine_status === "retrying")) {
    return "retrying";
  }

  if (stages.some((stage) => stage.machine_status === "fallback_applied" || stage.fallback_metadata?.applied)) {
    return "warning";
  }

  if (stages.some((stage) => stage.machine_status === "succeeded_with_warnings")) {
    return "warning";
  }

  if (stages.every((stage) => isCompletedStatus(stage.machine_status))) {
    return "completed";
  }

  if (stages.every((stage) => stage.machine_status === "skipped")) {
    return "skipped";
  }

  if (stages.some((stage) => isActiveStatus(stage.machine_status))) {
    return "active";
  }

  return "pending";
}

function isCompletedStatus(status: PipelineMachineStatus | string): boolean {
  return ["succeeded", "completed"].includes(status);
}

function isActiveStatus(status: PipelineMachineStatus | string): boolean {
  return ["pending", "running", "fallback_applied"].includes(status);
}

function readWarningText(stages: PhaseStatus[]): string | undefined {
  for (const stage of stages) {
    if (stage.failure_type) {
      return stage.failure_type;
    }
    if (stage.fallback_metadata?.strategy) {
      return `Fallback used: ${stage.fallback_metadata.strategy}`;
    }
  }
  return undefined;
}

function getPhaseElapsedSeconds(stages: PhaseStatus[]): number | undefined {
  const timestamps = stages
    .map((stage) => new Date(stage.updated_at).getTime())
    .filter((value) => !Number.isNaN(value))
    .sort((left, right) => left - right);

  if (timestamps.length === 0) {
    return undefined;
  }

  return Math.max(0, Math.floor((timestamps[timestamps.length - 1]! - timestamps[0]!) / 1000));
}

function findEventMessage(events: PipelineProgressEvent[], match: string): string | undefined {
  return [...events]
    .reverse()
    .find((event) => event.human_message.toLowerCase().includes(match) || JSON.stringify(event.metadata ?? {}).toLowerCase().includes(match))
    ?.human_message;
}
