import type {
  PipelineStageName,
  ResumeGenerationRunStatus,
} from "../types/pipeline";

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

export const RUN_STATUS_LABELS: Record<ResumeGenerationRunStatus, string> = {
  idle: "Idle",
  validating_input: "Validating input",
  submitting: "Submitting",
  queued: "Queued",
  phase_running: "Phase running",
  phase_completed: "Phase completed",
  success: "Success",
  partial_success: "Partial success",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const DEFAULT_SOURCE_PROFILE_PATH = "data/master_profile.example.json";
export const DEFAULT_TEMPLATE_ID = "ats_standard";
