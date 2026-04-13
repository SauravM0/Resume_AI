export type ResumeGenerationRunStatus =
  | "idle"
  | "validating_input"
  | "submitting"
  | "queued"
  | "phase_running"
  | "phase_completed"
  | "success"
  | "partial_success"
  | "failed"
  | "cancelled";

export type ResumeRunView =
  | "form"
  | "progress"
  | "result"
  | "error";

export type PipelineProgressEventType =
  | "run_started"
  | "stage_started"
  | "stage_progress"
  | "stage_completed"
  | "stage_failed"
  | "warning"
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
  | "pending"
  | "running"
  | "succeeded"
  | "succeeded_with_warnings"
  | "failed"
  | "blocked";

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
  generation_preferences?: Record<string, unknown>;
}

export interface ResumeSettings {
  page_length_pages: 1 | 2;
  template_id: string;
  debug_mode: boolean;
  strict_mode: boolean;
  show_detailed_diagnostics_after_run: boolean;
}

export type BackendHealthStatus = "healthy" | "degraded" | "unavailable" | "checking";

export interface BackendHealthState {
  status: BackendHealthStatus;
  summary: string;
  detail?: string;
  http_status_code?: number;
  checked_at?: string;
  api?: boolean;
  profile_path_configured?: boolean;
  template_configured?: boolean;
}

export type ReadinessState = "ready" | "warning" | "unavailable" | "unknown";

export interface ReadinessIndicator {
  key: string;
  label: string;
  state: ReadinessState;
  summary: string;
  detail?: string;
}

export interface RunMetadata {
  run_id: string;
  started_at?: string;
  finished_at?: string;
  source_profile_id?: string;
  source_profile_path?: string;
  template_id?: string;
  render_job_id?: string;
  frontend_correlation_id?: string;
  request_fingerprint?: string;
  idempotency_status?: string;
  page_length_pages?: 1 | 2;
  page_mode?: string;
  summary_state?: string;
  selected_experience_count?: number;
  selected_project_count?: number;
  selected_skill_count?: number;
  resume_ready?: boolean;
}

export interface SelectedExperience {
  id: string;
  title?: string;
  company?: string;
  summary?: string;
  score?: number;
  rationale?: string;
  evidence?: string[];
  metadata?: Record<string, unknown>;
}

export interface SelectedProject {
  id: string;
  name?: string;
  summary?: string;
  score?: number;
  rationale?: string;
  evidence?: string[];
  metadata?: Record<string, unknown>;
}

export interface SelectedSkill {
  id: string;
  name: string;
  category?: string;
  score?: number;
  rationale?: string;
  metadata?: Record<string, unknown>;
}

export interface VerificationWarning {
  code?: string;
  message: string;
  severity?: "info" | "warning" | "error";
  field?: string;
  source?: string;
  metadata?: Record<string, unknown>;
}

export interface FallbackRepairMetadata {
  stage_name?: PipelineStageName | string;
  applied: boolean;
  strategy?: string;
  reason?: string;
  repair_status?: "not_needed" | "attempted" | "applied" | "failed";
  operator_message?: string;
  metadata?: Record<string, unknown>;
}

export interface RunDiagnostics {
  summary?: string;
  failure_type?: string;
  failure_category?: string;
  retryable?: boolean;
  fallback_eligible?: boolean;
  correlation_id?: string;
  messages: string[];
  warnings: VerificationWarning[];
  fallback_repairs: FallbackRepairMetadata[];
  metadata?: Record<string, unknown>;
}

export interface DownloadableOutput {
  kind: string;
  storage_kind: string;
  reference: string;
  content_type?: string;
  file_name?: string;
  label?: string;
  size_bytes?: number;
  preview_reference?: string;
}

export interface RenderArtifact {
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

export type ArtifactAvailabilityState =
  | "available"
  | "unavailable"
  | "failed"
  | "partial"
  | "downloading";

export interface ArtifactItemViewModel {
  kind: "pdf" | "latex" | "structured_json" | "diagnostics_bundle" | string;
  label: string;
  state: ArtifactAvailabilityState;
  download_url?: string;
  preview_url?: string;
  file_name: string;
  content_type?: string;
  size_bytes?: number;
  message: string;
  source: "output" | "artifact" | "derived";
}

export interface BackendErrorPayload {
  message: string;
  failure_type?: string;
  failure_category?: string;
  stage_name?: PipelineStageName | string;
  retryable?: boolean;
  fallback_eligible?: boolean;
  run_id?: string;
  status_code?: number;
  diagnostics?: RunDiagnostics;
  metadata?: Record<string, unknown>;
  error_source?: "backend" | "frontend" | "transport" | "validation";
  backend_detail?: string;
  transport_detail?: string;
  suggested_next_step?: string;
  transport_target?: "generate_resume" | "progress_stream" | "health";
}

export type ErrorClassification =
  | "validation"
  | "backend_unavailable"
  | "api_route_not_found"
  | "sse_route_not_found"
  | "job_analysis_failed"
  | "selection_failed"
  | "generation_failed"
  | "verification_failed"
  | "rendering_failed"
  | "artifact_unavailable"
  | "timeout"
  | "transport_network_error"
  | "frontend_exception"
  | "unknown_internal_error";

export interface ErrorDisplayModel {
  classification: ErrorClassification;
  title: string;
  explanation: string;
  phase_label?: string;
  retry_recommendation: string;
  next_action_label: string;
}

export interface PhaseStatus {
  stage_name: PipelineStageName;
  machine_status: PipelineMachineStatus | string;
  human_message: string;
  progress_percent?: number;
  updated_at: string;
  attempt_number?: number;
  failure_type?: string;
  failure_category?: string;
  retryable?: boolean;
  fallback_eligible?: boolean;
  fallback_metadata?: FallbackRepairMetadata;
  metadata?: Record<string, unknown>;
}

export interface PipelineProgressEventBase {
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

export interface PhaseStartedProgressEvent extends PipelineProgressEventBase {
  event_type: "stage_started";
  stage_name: PipelineStageName;
}

export interface PhaseUpdatedProgressEvent extends PipelineProgressEventBase {
  event_type: "stage_progress";
  stage_name: PipelineStageName;
}

export interface PhaseCompletedProgressEvent extends PipelineProgressEventBase {
  event_type: "stage_completed";
  stage_name: PipelineStageName;
}

export interface PhaseFailedProgressEvent extends PipelineProgressEventBase {
  event_type: "stage_failed";
  stage_name: PipelineStageName;
}

export interface WarningProgressEvent extends PipelineProgressEventBase {
  event_type: "warning";
}

export interface RetryScheduledProgressEvent extends PipelineProgressEventBase {
  event_type: "retry_scheduled";
  stage_name?: PipelineStageName;
}

export interface FallbackAppliedProgressEvent extends PipelineProgressEventBase {
  event_type: "fallback_applied";
  stage_name?: PipelineStageName;
}

export interface RunCompletedProgressEvent extends PipelineProgressEventBase {
  event_type: "run_completed";
}

export interface RunFailedProgressEvent extends PipelineProgressEventBase {
  event_type: "run_failed";
}

export interface RunStartedProgressEvent extends PipelineProgressEventBase {
  event_type: "run_started";
}

export type PipelineProgressEvent =
  | RunStartedProgressEvent
  | PhaseStartedProgressEvent
  | PhaseUpdatedProgressEvent
  | PhaseCompletedProgressEvent
  | PhaseFailedProgressEvent
  | WarningProgressEvent
  | RetryScheduledProgressEvent
  | FallbackAppliedProgressEvent
  | RunCompletedProgressEvent
  | RunFailedProgressEvent;

export interface ProgressConnectionState {
  enabled: boolean;
  connected: boolean;
  transport: "sse" | "polling" | "none";
  last_error?: string;
}

export interface PipelineProgressState {
  run_id: string;
  events: PipelineProgressEvent[];
  stages: PhaseStatus[];
  latest_event?: PipelineProgressEvent;
  progress_percent: number;
  terminal: boolean;
  current_stage?: PhaseStatus;
  completed_stages: PhaseStatus[];
  retry_notices: PipelineProgressEvent[];
  fallback_notices: PipelineProgressEvent[];
  connection: ProgressConnectionState;
}

export type ProgressPhaseKey =
  | "input_accepted"
  | "job_description_analysis"
  | "evidence_extraction_ranking"
  | "content_generation"
  | "verification_repair"
  | "rendering_pdf_assembly"
  | "finalization";

export type ProgressPhaseStatus =
  | "pending"
  | "active"
  | "completed"
  | "warning"
  | "failed"
  | "skipped"
  | "retrying";

export interface ProgressPhaseViewModel {
  key: ProgressPhaseKey;
  label: string;
  description: string;
  status: ProgressPhaseStatus;
  updated_at?: string;
  elapsed_seconds?: number;
  detail_text?: string;
  backend_stages: PhaseStatus[];
  fallback_used: boolean;
  retry_in_progress: boolean;
  warning_text?: string;
  failed: boolean;
}

export interface RunProgressOverview {
  run_id: string;
  overall_status: ResumeGenerationRunStatus;
  started_at?: string;
  elapsed_seconds?: number;
  current_backend_message?: string;
  run_health: "healthy" | "warning" | "failed";
  run_health_text: string;
  queued: boolean;
  timeout_warning?: string;
  retry_in_progress: boolean;
  partial_recovery: boolean;
  hard_failure: boolean;
  connection: ProgressConnectionState;
}

export interface GenerationResultData {
  run_metadata: RunMetadata;
  overall_status: PipelineOverallStatus;
  selected_experiences: SelectedExperience[];
  selected_projects: SelectedProject[];
  selected_skills: SelectedSkill[];
  verification_warnings: VerificationWarning[];
  diagnostics?: RunDiagnostics;
  render_artifacts: RenderArtifact[];
  downloadable_outputs: DownloadableOutput[];
  final_file_reference?: string;
  raw_response: GenerateResumeResponse;
}

export interface ResumeGenerationState {
  status: ResumeGenerationRunStatus;
  view: ResumeRunView;
  run: RunMetadata | null;
  current_phase: PhaseStatus | null;
  progress: PipelineProgressState | null;
  result: GenerationResultData | null;
  error: BackendErrorPayload | null;
  debug_visible: boolean;
  retrying: boolean;
  submitted_request: GenerateResumeRequest | null;
  last_completed_stage: PhaseStatus | null;
  validation_errors: string[];
}

export interface GenerateResumeResponse {
  run_id: string;
  status: PipelineOverallStatus;
  available_outputs: DownloadableOutput[];
  warnings: string[];
  final_file_reference?: string;
  artifact_manifest: RenderArtifact[];
  stage_events: Array<Record<string, unknown>>;
  diagnostics?: RunDiagnostics;
  selected_experiences: SelectedExperience[];
  selected_projects: SelectedProject[];
  selected_skills: SelectedSkill[];
  verification_warnings: VerificationWarning[];
  fallback_repairs: FallbackRepairMetadata[];
  run_metadata?: (Partial<RunMetadata> & Record<string, unknown>);
}
