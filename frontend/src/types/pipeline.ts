export type PipelineProgressEventType =
  | "run_started"
  | "stage_started"
  | "stage_progress"
  | "stage_completed"
  | "stage_failed"
  | "retry_scheduled"
  | "fallback_applied"
  | "run_completed"
  | "run_failed";

export type PipelineStageName =
  | "load_source_profile"
  | "normalize_source_data"
  | "ingest_job_description"
  | "parse_job_description"
  | "rank_select_evidence"
  | "generate_structured_content"
  | "verify_generated_content"
  | "render_deterministic_latex"
  | "compile_pdf"
  | "persist_artifacts";

export type PipelineMachineStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "succeeded_with_warnings"
  | "failed"
  | "skipped"
  | "retrying"
  | "fallback_applied"
  | "blocked"
  | "completed";

export type PipelineOverallStatus =
  | "idle"
  | "pending"
  | "running"
  | "succeeded"
  | "succeeded_with_warnings"
  | "failed"
  | "blocked";

export interface PipelineProgressEvent {
  event_id: string;
  run_id: string;
  event_type: PipelineProgressEventType;
  timestamp: string;
  stage_name?: PipelineStageName;
  human_message: string;
  machine_status: PipelineMachineStatus | string;
  progress_percent?: number;
  metadata?: Record<string, unknown>;
}

export interface PipelineStageProgress {
  stage_name: PipelineStageName;
  machine_status: PipelineMachineStatus | string;
  human_message: string;
  progress_percent?: number;
  updated_at: string;
  attempt_number?: number;
  failure_type?: string;
  retryable?: boolean;
  fallback_eligible?: boolean;
}

export interface PipelineProgressState {
  run_id: string;
  events: PipelineProgressEvent[];
  stages: PipelineStageProgress[];
  latest_event?: PipelineProgressEvent;
  progress_percent: number;
  connected: boolean;
  terminal: boolean;
  current_stage?: PipelineStageProgress;
  completed_stages: PipelineStageProgress[];
  retry_notices: PipelineProgressEvent[];
  fallback_notices: PipelineProgressEvent[];
  error?: string;
}

export interface GenerateResumeRequest {
  pipeline_run_id?: string;
  source_profile_id?: string;
  source_profile_path?: string;
  job_description_text: string;
  job_posting_url?: string;
  template_id?: string;
  render_job_id?: string;
  persist_intermediate_artifacts?: boolean;
  frontend_correlation_id?: string;
}

export interface AvailableOutput {
  kind: string;
  storage_kind: string;
  reference: string;
  content_type?: string;
}

export interface PipelineArtifactRef {
  artifact_id: string;
  kind: string;
  stage_name: PipelineStageName | string;
  storage_backend: string;
  schema_version: string;
  uri?: string;
  sha256?: string;
  size_bytes?: number;
  content_type?: string;
  metadata?: Record<string, unknown>;
}

export interface GenerateResumeResponse {
  run_id: string;
  status: Exclude<PipelineOverallStatus, "idle">;
  available_outputs: AvailableOutput[];
  warnings: string[];
  final_file_reference?: string;
  artifact_manifest: PipelineArtifactRef[];
  stage_events: Array<Record<string, unknown>>;
}

export interface ResumeGenerationError {
  message: string;
  failure_type?: string;
  stage_name?: PipelineStageName | string;
  retryable?: boolean;
  fallback_eligible?: boolean;
  run_id?: string;
  status_code?: number;
}

export interface ResumeGenerationState {
  run_id?: string;
  overall_status: PipelineOverallStatus;
  submitting: boolean;
  response?: GenerateResumeResponse;
  error?: ResumeGenerationError;
  warnings: string[];
  final_outputs: AvailableOutput[];
  progress: PipelineProgressState;
}

export const PIPELINE_STAGE_ORDER: PipelineStageName[] = [
  "load_source_profile",
  "normalize_source_data",
  "ingest_job_description",
  "parse_job_description",
  "rank_select_evidence",
  "generate_structured_content",
  "verify_generated_content",
  "render_deterministic_latex",
  "compile_pdf",
  "persist_artifacts",
];

export const PIPELINE_STAGE_LABELS: Record<PipelineStageName, string> = {
  load_source_profile: "Load source profile",
  normalize_source_data: "Normalize source data",
  ingest_job_description: "Ingest job description",
  parse_job_description: "Parse job description",
  rank_select_evidence: "Rank and select evidence",
  generate_structured_content: "Generate structured content",
  verify_generated_content: "Verify generated content",
  render_deterministic_latex: "Render LaTeX",
  compile_pdf: "Compile PDF",
  persist_artifacts: "Persist artifacts",
};
