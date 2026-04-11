# Phase 1 Pipeline Integration Notes

## Current pipeline contract

The `parse_job_description` stage now carries two explicit views at once:

- Rebuilt Phase 1:
  - `ParseJobDescriptionOutput.phase1_result`
  - `ParseJobDescriptionOutput.deterministic_extraction`
  - `ParseJobDescriptionOutput.llm_enrichment_payload`
  - `ParseJobDescriptionOutput.final_analysis`
- Legacy compatibility:
  - `ParseJobDescriptionOutput.raw_analysis`
  - `ParseJobDescriptionOutput.normalized_analysis`

`normalized_analysis` remains the current downstream contract for Phase 2, Phase 3, and the Phase 6 verification gate. It is produced explicitly by `backend/app/orchestration/adapters/phase1_contract_adapter.py` from the rebuilt Phase 1 output. No downstream stage is relying on silent schema coercion.

## Artifact behavior

The orchestration layer now persists separate Parse-stage artifacts:

- `raw_job_description`
- `job_analysis`
  - Full `ParseJobDescriptionOutput` envelope for compatibility and traceability.
- `phase1_deterministic_extraction`
- `phase1_llm_enrichment`
- `phase1_final_analysis`

`phase1_final_analysis` artifact metadata includes:

- `parser_confidence`
- `jd_quality_score`

The full inline JSON payload for `phase1_final_analysis` also contains those fields, plus the complete merged Phase 1 contract.

## Downstream migration rules

Consumers should migrate in this order:

1. Read `ParseJobDescriptionOutput.final_analysis` when the caller needs recruiter intent, JD quality breakdown, role-family vs org-mode separation, or requirement-level confidence.
2. Keep using `ParseJobDescriptionOutput.normalized_analysis` only for legacy Phase 2/3/4 interfaces that still depend on `NormalizedJobAnalysis`.
3. Do not infer rebuilt Phase 1 fields back out of `normalized_analysis`. That projection is lossy by design.

## Known compatibility boundaries

- `NormalizedJobAnalysis.role_type` is still an org-mode compatibility projection, not a functional role family.
- `ParsedJobAnalysisResponse.role_type` remains a legacy ambiguous field exposed only for backward compatibility.
- `Phase1ParseResult.enriched_analysis` is retained as a compatibility alias for the merged final analysis. New pipeline code should prefer `merged_analysis` or `final_analysis`.

## Files to update next when downstream migration starts

- `src/resume_optimizer/phase2_models.py`
  - Add an optional rebuilt Phase 1 attachment or dedicated richer job-analysis input type.
- `src/resume_optimizer/services/phase3_service.py`
  - Consume recruiter-intent and JD-quality surfaces directly instead of relying on flattened `NormalizedJobAnalysis`.
- `backend/app/services/verification/orchestrator.py`
  - Accept rebuilt Phase 1 fields for more precise requirement verification and ambiguity handling.
