# Phase 1 Rebuild Final

## Purpose

This document is the final engineering closeout for the Phase 1 job-description understanding rebuild.

It answers four review questions:

1. What changed.
2. Why it changed.
3. How it should be used now.
4. How to verify Phase 1 is complete and stable.

## Old Phase 1

### Old execution shape

Old Phase 1 centered on these files:

- `src/resume_optimizer/job_models.py`
- `src/resume_optimizer/ai_service.py`
- `src/resume_optimizer/job_normalizers.py`
- `src/resume_optimizer/prompts/phase1_job_analysis_prompt.txt`

Old flow:

1. Send raw JD text directly to an LLM prompt.
2. Parse a shallow JSON response into `ParsedJobAnalysisResponse`.
3. Run light deterministic post-processing in `normalize_job_analysis(...)`.
4. Collapse everything into `NormalizedJobAnalysis`.
5. Pass that flattened object into later phases.

### Old schema limits

Old output could represent only:

- `technical_skills`
- `soft_skills`
- `seniority_level`
- `role_type`
- `industry_domain`
- `key_action_verbs`
- `must_have_requirements`
- `nice_to_have_requirements`
- `company_culture_signals`
- `years_experience_required`
- `prioritized_skills`

### Old technical problems

- `role_type` mixed two separate concepts:
  - technical family like `backend`, `frontend`, `data`
  - org mode like `individual_contributor`, `lead`, `manager`
- seniority normalization collided with org-mode signals like `lead` and `manager`
- deterministic extraction was shallow:
  - sentence-level marker matching
  - whole-text token scans
  - weak section awareness
- no strict confidence contract for extracted items
- no recruiter-intent model
- no JD quality scoring model
- no typed intermediate artifact separating:
  - deterministic facts
  - LLM inference
  - merged final output
- downstream phases had to compensate for missing or lossy Phase 1 structure

## New Phase 1

### New execution shape

Current Phase 1 is built around these files:

- Schema:
  - `src/resume_optimizer/phase1_models.py`
- Role modeling:
  - `src/resume_optimizer/phase1_role_modeling.py`
- Deterministic extraction:
  - `src/resume_optimizer/phase1_deterministic_models.py`
  - `src/resume_optimizer/phase1_deterministic_canonicalizers.py`
  - `src/resume_optimizer/phase1_deterministic_extractors.py`
- LLM enrichment:
  - `src/resume_optimizer/phase1_parser.py`
  - `src/resume_optimizer/prompts/phase1_job_enrichment_prompt.txt`
- Merge and confidence:
  - `src/resume_optimizer/phase1_merge.py`
  - `src/resume_optimizer/phase1_merge_confidence.py`
  - `src/resume_optimizer/phase1_merge_normalization.py`
- Recruiter intent and JD quality:
  - `src/resume_optimizer/phase1_recruiter_intent.py`
  - `src/resume_optimizer/phase1_jd_quality.py`
- Legacy compatibility:
  - `src/resume_optimizer/phase1_legacy_adapter.py`
  - `backend/app/orchestration/adapters/phase1_contract_adapter.py`

New flow:

1. Build deterministic extraction from raw JD text.
2. Send raw JD text plus deterministic artifact to the Phase 1 enrichment prompt.
3. Parse strict JSON from the model.
4. Retry or repair malformed output conservatively.
5. Merge deterministic findings with LLM enrichment.
6. Validate the merged result against `Phase1JobAnalysis`.
7. Project the merged result into legacy pipeline contracts where needed.

### New schema

`Phase1JobAnalysis` now includes:

- raw job text
- title and company
- functional role family
- organizational role mode
- seniority
- responsibility clusters
- must-have and nice-to-have skills
- required tools/platforms
- required domains
- must-have behaviors
- business-goal signals
- impact signals
- years/education/leadership/delivery scope requirements
- constraint signals
- work model signals
- industry domain
- action verbs
- recruiter intent
- JD quality breakdown
- overall JD quality score
- parser confidence
- item-level requirement confidence
- extraction notes
- normalized keywords
- prioritized requirements

### Problems fixed

- Functional role family is now independent from organizational role mode.
- Deterministic extraction is first-class instead of hidden inside a normalizer.
- LLM enrichment no longer replaces explicit JD facts.
- Item-level confidence is explicit and schema-validated.
- Recruiter intent is structured for downstream ranking and planning.
- JD quality is structured for downstream caution and fallback behavior.
- Pipeline artifacts now preserve:
  - raw JD
  - deterministic extraction
  - LLM enrichment payload
  - merged final Phase 1 output

## How The New Pieces Work

### Deterministic extraction

Implemented in `src/resume_optimizer/phase1_deterministic_extractors.py`.

This layer extracts inspectable typed findings for:

- title candidates
- company candidates
- years of experience
- requirement markers
- tools/platforms
- repeated keywords
- action verbs
- work model signals
- leadership signals
- scope indicators
- education markers
- domain signals
- section boundaries

This is the baseline fact layer. It is intentionally explainable and auditable.

### LLM enrichment

Implemented in `src/resume_optimizer/phase1_parser.py` with prompt in `src/resume_optimizer/prompts/phase1_job_enrichment_prompt.txt`.

The model is used for inference where deterministic parsing is insufficient:

- hidden priorities
- recruiter-intent framing
- role-family nuance when implicit
- org-mode nuance when implicit
- delivery scope and leadership expectation
- business-goal and impact emphasis

The model is not allowed to be the sole source of truth. Output is parsed as strict JSON and validated.

### Merge logic

Implemented in `src/resume_optimizer/phase1_merge.py`.

Merge rules:

- deterministic explicit facts outrank low-confidence LLM guesses
- LLM-only values are retained only when grounded and defensible
- ambiguous or conflicting signals are surfaced in notes
- repeated JD signals increase confidence
- weak JD quality lowers parser confidence

### Confidence scoring

Implemented in `src/resume_optimizer/phase1_merge_confidence.py`.

Current scoring surfaces include:

- job title confidence
- functional role family confidence
- organizational role mode confidence
- requirement confidence
- overall parser confidence

Confidence is not a single opaque number only. Item-level confidence is stored in `requirement_confidence_by_item`.

### Recruiter intent

Implemented in `src/resume_optimizer/phase1_recruiter_intent.py`.

Output includes:

- likely success shape
- emphasis profile:
  - architecture
  - execution
  - collaboration
  - leadership
- persuasive evidence types
- pace/environment signals
- domain-specific emphasis
- breadth preference
- intent confidence

This is designed for later phases that need to choose evidence and shape the candidate story.

### JD quality scoring

Implemented in `src/resume_optimizer/phase1_jd_quality.py`.

Output includes:

- completeness score
- specificity score
- ambiguity score
- consistency score
- downstream-risk score
- overall `jd_quality_score`

This gives downstream phases an explicit caution signal for weak or contradictory JDs.

## How Downstream Code Should Use Phase 1

### Current pipeline contract

The Parse stage now returns both rebuilt and legacy views in `ParseJobDescriptionOutput`:

- rebuilt:
  - `phase1_result`
  - `deterministic_extraction`
  - `llm_enrichment_payload`
  - `final_analysis`
- compatibility:
  - `raw_analysis`
  - `normalized_analysis`

### Required downstream rule

Use:

- `final_analysis` when richer semantics are needed
- `normalized_analysis` only for legacy consumers that still require `NormalizedJobAnalysis`

Do not reconstruct rebuilt semantics from `normalized_analysis`. That projection is lossy.

### Current compatibility boundary

- `NormalizedJobAnalysis.role_type` is an org-mode compatibility projection.
- It is not a functional role family.
- `ParsedJobAnalysisResponse.role_type` remains legacy and ambiguous.

## Migration Note

Current migration state:

- Phase 6 orchestration is integrated with rebuilt Phase 1.
- Downstream phases still consume `normalized_analysis`.
- The compatibility mapping is explicit in:
  - `src/resume_optimizer/phase1_legacy_adapter.py`
  - `backend/app/orchestration/adapters/phase1_contract_adapter.py`

Next downstream migrations should target:

1. `src/resume_optimizer/phase2_models.py`
2. `src/resume_optimizer/services/phase3_service.py`
3. `backend/app/services/verification/orchestrator.py`

Reason:

- these layers still consume flattened `NormalizedJobAnalysis`
- they cannot yet use recruiter intent, JD quality breakdown, or separated role axes directly

## Parsed Output Examples

Example from `backend/app/tests/fixtures/phase1/full_job_analysis.json`:

```json
{
  "job_title": "Senior Backend Platform Engineer",
  "company_name": "Acme Cloud",
  "functional_role_family": "platform",
  "organizational_role_mode": "tech_lead",
  "seniority_level": "senior",
  "must_have_skills": [
    "Python",
    "PostgreSQL",
    "Distributed Systems"
  ],
  "nice_to_have_skills": [
    "Terraform",
    "Observability"
  ],
  "required_tools_platforms": [
    "AWS",
    "Kubernetes",
    "GitHub Actions"
  ],
  "primary_responsibility_clusters": [
    "Design backend APIs and platform services",
    "Improve reliability and developer infrastructure",
    "Coordinate delivery across product, security, and engineering"
  ],
  "recruiter_intent": {
    "likely_success_shape": "Shows architecture ownership that improves system reliability and delivery at team scale.",
    "breadth_preference": "balanced",
    "confidence": 0.82
  },
  "jd_quality_breakdown": {
    "completeness_score": 0.9,
    "specificity_score": 0.87,
    "ambiguity_score": 0.14,
    "consistency_score": 0.88,
    "downstream_risk_score": 0.18
  },
  "jd_quality_score": 0.88,
  "parser_confidence": 0.84
}
```

Interpretation:

- `platform` answers what kind of work the role does
- `tech_lead` answers how the role operates in the org
- recruiter intent favors architecture plus execution evidence
- JD quality is strong, so downstream ranking and planning can trust the structure more heavily

## How To Run Phase 1 Evaluation

### Gold eval pack

Dataset and harness:

- `backend/app/tests/fixtures/phase1_eval/eval_cases.json`
- `backend/app/tests/fixtures/phase1_eval/README.md`
- `src/resume_optimizer/phase1_eval.py`
- `scripts/run_phase1_eval.py`

Run locally:

```bash
PYTHONPATH=src:. python3 scripts/run_phase1_eval.py
```

JSON output:

```bash
PYTHONPATH=src:. python3 scripts/run_phase1_eval.py --json
```

The eval pack currently covers 45 realistic JDs across:

- frontend
- backend
- fullstack
- platform/devops
- data/analytics
- ML
- product
- design
- startup
- enterprise
- junior
- senior
- manager/lead
- vague/noisy JDs
- highly structured JDs

### Integration and regression checks

Phase 1 and pipeline integration verification:

```bash
PYTHONPATH=src:. python3 -m pytest \
  backend/app/tests/unit/test_phase1_models.py \
  backend/app/tests/unit/test_phase1_role_modeling.py \
  backend/app/tests/unit/test_phase1_deterministic_extractors.py \
  backend/app/tests/unit/test_phase1_recruiter_intent_quality.py \
  backend/app/tests/unit/test_phase1_merge.py \
  backend/app/tests/unit/test_phase1_parser.py \
  backend/app/tests/unit/test_phase2_pipeline_integration.py \
  backend/app/tests/unit/test_phase2_end_to_end_artifacts.py \
  backend/app/tests/unit/test_stage_adapters.py \
  backend/app/tests/integration/test_phase1_pipeline_integration.py \
  backend/tests/orchestration/test_pipeline_regression_harness.py \
  -q -s
```

Last recorded result during integration:

- `53 passed in 13.00s`

## Acceptance Checklist

Phase 1 is complete only when every item below is true.

- [x] Functional role family is separated from organizational role mode.
- [x] Strong typed Phase 1 schema exists and validates required structure.
- [x] Deterministic extraction layer is implemented before LLM enrichment.
- [x] LLM enrichment is implemented with strict JSON parsing and validation.
- [x] Retry/repair handling exists for malformed or invalid model outputs.
- [x] Merge logic is deterministic and preserves explicit JD facts over weak inference.
- [x] Confidence scoring is implemented for major Phase 1 decisions.
- [x] Recruiter-intent extraction is implemented as typed output.
- [x] JD-quality scoring is implemented as typed output.
- [x] Gold eval pack exists with realistic JD coverage.
- [x] Pipeline/orchestration integration is in place.
- [x] Raw JD, deterministic extraction, LLM enrichment, and final Phase 1 output are all persisted as artifacts.
- [x] Backward compatibility adapters are explicit.
- [x] Integration tests pass without breaking Phase 2 compatibility.

## Completion Checks

Reviewers can treat Phase 1 as complete when all of these checks pass:

1. Schema check
   - `Phase1JobAnalysis` validates fixture payloads in `backend/app/tests/fixtures/phase1/full_job_analysis.json`.
2. Role modeling check
   - `functional_role_family` and `organizational_role_mode` are both present and independently inferred.
3. Deterministic extraction check
   - deterministic extractor tests pass across messy, startup, enterprise, and vague JDs.
4. LLM parser check
   - malformed JSON retry and partial repair tests pass.
5. Merge check
   - deterministic facts win over weak conflicting LLM guesses.
6. Recruiter-intent and JD-quality check
   - strong, weak, and ambiguous JDs produce different typed outputs.
7. Evaluation check
   - gold eval suite runs locally and reports passing cases.
8. Pipeline integration check
   - Parse-stage artifacts include:
     - `phase1_deterministic_extraction`
     - `phase1_llm_enrichment`
     - `phase1_final_analysis`
9. Compatibility check
   - later phases still receive `normalized_analysis` through explicit adapters.

## Reviewer Summary

Phase 1 is no longer a shallow LLM-first keyword extractor.

It is now:

- deterministic-first
- strongly typed
- confidence-aware
- role-model corrected
- recruiter-intent aware
- JD-quality aware
- pipeline-integrated
- eval-backed

The remaining work is downstream migration off the lossy legacy `NormalizedJobAnalysis` projection, not additional Phase 1 rebuild work.
