# Phase 2 Pipeline Integration

## Current Integration Points

- Ranking entry:
  - `src/resume_optimizer/ranking_service.py`
  - `build_phase2_ranking_artifacts(...)`
  - Consumes the normalized `MasterProfile` and now builds the internal Phase 2 candidate artifact bundle first.
- Selection entry:
  - `src/resume_optimizer/ranking_service.py`
  - Selection still operates on the ranking-compatible evidence subset and returns the existing `Phase2SelectionResult`.
- Generation entry:
  - `src/resume_optimizer/phase3_assembler.py`
  - Phase 3 still consumes `Phase2SelectionResult`, `RankingResponse`, and `MasterProfile`.
  - The new evidence graph and coverage map are available upstream on `Phase2ServiceResult` and `Phase2RankingArtifacts` for future rebuild work.
- Verification/provenance entry:
  - `src/resume_optimizer/provenance.py`
  - Existing provenance payloads remain backward compatible and continue to expose source parent/child references used by later verification paths.

## New Internal Phase 2 Flow

1. `Phase2Service.run(...)` calls `build_phase2_ranking_artifacts(...)`.
2. `build_phase2_ranking_artifacts(...)` builds `Phase2CandidateArtifacts` from `MasterProfile`.
3. `Phase2CandidateArtifacts` includes:
   - `evidence_graph`
   - `coverage_map`
   - `ranking_compatible_evidence`
   - `extraction_summary`
4. Ranking and selection continue to use `ranking_compatible_evidence`.
5. The full evidence graph and coverage map are returned alongside legacy Phase 2 outputs.

## Compatibility Layer

- Adapter:
  - `src/resume_optimizer/evidence_adapters.py`
  - `adapt_master_profile_to_phase2_candidate_artifacts(...)`
- Internal artifact builder:
  - `src/resume_optimizer/phase2_artifacts.py`
  - `build_phase2_candidate_artifacts(...)`
- Log-safe diagnostics:
  - `src/resume_optimizer/phase2_artifacts.py`
  - `phase2_artifact_diagnostics_payload(...)`

## Developer Visibility

`Phase2Service` now logs:

- evidence graph size
- evidence source mix
- top role-family coverage areas
- top technical clusters
- weak-zone summary
- dedupe repeat count
- declared-skill count

## Transition Notes

- No downstream phase was rewritten to require the new graph yet.
- `RankingResponse` and `Phase2SelectionResult` remain the compatibility boundary for current Phase 3.
- Future Phase 3 rebuild work should prefer `Phase2ServiceResult.evidence_graph` and `Phase2ServiceResult.coverage_map` over re-deriving profile summaries from `MasterProfile`.
