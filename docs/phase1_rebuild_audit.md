# Phase 1 Rebuild Audit And Migration Plan

## Scope

This document audits the current Phase 1 implementation that parses raw job descriptions into `NormalizedJobAnalysis`, and it defines the migration plan for rebuilding Phase 1 correctly without implementing that rebuild yet.

Audited code paths include:

- Phase 1 models, prompt loading, AI call wrapper, prompt template, normalization logic, and API entrypoints.
- Phase 6 orchestration hooks and adapters that execute or persist Phase 1 output.
- All later-phase consumers that read `NormalizedJobAnalysis` directly or read artifacts embedding it.
- Tests and fixtures that currently hard-code the legacy Phase 1 contract.

Generated mirror files under `build/lib/**` were inspected only as build output mirrors of `src/**` and `backend/**`. They are not source-of-truth and should not be edited directly during migration.

## Current Phase 1 Implementation

### Execution Flow

Current execution path:

1. Raw request enters `RawJobDescriptionRequest` in `src/resume_optimizer/job_models.py`.
2. `analyze_job_description()` in `src/resume_optimizer/ai_service.py` validates only that the JD text is non-empty, formats the Phase 1 prompt, and calls the OpenAI Responses API with `text.format = json_object`.
3. The model response is parsed into `ParsedJobAnalysisResponse`.
4. `normalize_job_analysis()` in `src/resume_optimizer/job_normalizers.py` merges the raw LLM output with deterministic extraction from the original JD text.
5. The result is emitted as `NormalizedJobAnalysis`.
6. That normalized object is used directly as the Phase 2, Phase 3, Phase 4, and Phase 6 handoff contract.

Primary source files:

- `src/resume_optimizer/job_models.py`
- `src/resume_optimizer/ai_service.py`
- `src/resume_optimizer/prompt_loader.py`
- `src/resume_optimizer/prompts/phase1_job_analysis_prompt.txt`
- `src/resume_optimizer/job_normalizers.py`
- `src/resume_optimizer/app.py`
- `backend/app/orchestration/adapters/job_parser_adapter.py`

### Current Schema Fields

#### Raw request schema

Defined in `src/resume_optimizer/job_models.py`.

| Model | Field | Type | Notes |
| --- | --- | --- | --- |
| `RawJobDescriptionRequest` | `job_description_text` | non-empty string | Required raw JD text |
| `RawJobDescriptionRequest` | `job_posting_url` | optional URL | Accepted at ingress but unused by the Phase 1 parser |

#### Raw LLM schema

Defined in `src/resume_optimizer/job_models.py`.

| Model | Field | Type | Notes |
| --- | --- | --- | --- |
| `ParsedJobAnalysisResponse` | `technical_skills` | `list[str]` | Free-text skill list |
| `ParsedJobAnalysisResponse` | `soft_skills` | `list[str]` | Free-text soft-skill list |
| `ParsedJobAnalysisResponse` | `seniority_level` | `str \| null` | Free-text; normalized later |
| `ParsedJobAnalysisResponse` | `role_type` | `str \| null` | Free-text; normalized later |
| `ParsedJobAnalysisResponse` | `industry_domain` | `str \| null` | Free-text |
| `ParsedJobAnalysisResponse` | `key_action_verbs` | `list[str]` | Free-text verbs |
| `ParsedJobAnalysisResponse` | `must_have_requirements` | `list[str]` | Requirement sentences/phrases |
| `ParsedJobAnalysisResponse` | `nice_to_have_requirements` | `list[str]` | Preferred requirement sentences/phrases |
| `ParsedJobAnalysisResponse` | `company_culture_signals` | `list[str]` | Free-text culture phrases |

#### Normalized Phase 1 schema

Defined in `src/resume_optimizer/job_models.py`.

| Model | Field | Type | Current meaning |
| --- | --- | --- | --- |
| `NormalizedJobAnalysis` | `role_type` | `RoleType \| null` | Supposed to be org role mode, but current taxonomy also tries to treat it as technical role family |
| `NormalizedJobAnalysis` | `seniority_level` | `SeniorityLevel \| null` | Target seniority |
| `NormalizedJobAnalysis` | `industry_domain` | `str \| null` | Single domain tag |
| `NormalizedJobAnalysis` | `technical_skills` | `list[str]` | Merged LLM + deterministic detected skills |
| `NormalizedJobAnalysis` | `soft_skills` | `list[str]` | Normalized free-text soft skills |
| `NormalizedJobAnalysis` | `key_action_verbs` | `list[str]` | Normalized action verbs |
| `NormalizedJobAnalysis` | `must_have_requirements` | `list[str]` | Merged LLM + deterministic requirement lines |
| `NormalizedJobAnalysis` | `nice_to_have_requirements` | `list[str]` | Merged LLM + deterministic preferred lines |
| `NormalizedJobAnalysis` | `company_culture_signals` | `list[str]` | Normalized free-text culture phrases |
| `NormalizedJobAnalysis` | `years_experience_required` | `int \| null` | Minimum explicit years found by regex |
| `NormalizedJobAnalysis` | `prioritized_skills` | `list[NormalizedSkillRequirement]` | Derived from the merged skill list using string containment against requirement text |

`NormalizedSkillRequirement` fields:

| Field | Type | Current meaning |
| --- | --- | --- |
| `skill_name` | `str` | Canonical skill name |
| `priority` | `core \| important \| nice_to_have` | Derived priority tier |
| `evidence` | `str \| null` | Unused by current normalizer |

### Current Parser Flow

#### LLM call contract

Defined by:

- `src/resume_optimizer/prompts/phase1_job_analysis_prompt.txt`
- `src/resume_optimizer/ai_service.py`
- `src/resume_optimizer/openai_client.py`

Current behavior:

- One prompt file is loaded from disk.
- The raw JD is interpolated into the prompt body with no additional system/user separation.
- The OpenAI Responses API is called with JSON-object output mode.
- If the first response is invalid JSON, the exact same prompt is retried once with an added instruction asking for valid JSON only.
- There is no typed tool schema, no explicit structured output schema beyond the prompt text, no confidence field, and no provenance/explanation of which JD span supported each extracted value.
- There is no parser-time distinction between deterministic extraction and LLM inference; both are collapsed before downstream use.

#### Deterministic post-processing

Defined in `src/resume_optimizer/job_normalizers.py`.

Current post-processing steps:

1. Normalize LLM `technical_skills`.
2. Detect technical keywords from the entire JD token stream via `normalize_skill_list()` and merge them into `technical_skills`.
3. Normalize LLM requirement arrays.
4. Split JD text into sentence-like chunks and classify any chunk containing a configured marker as must-have or nice-to-have.
5. Merge those deterministic requirement chunks into the LLM requirement arrays.
6. Derive `prioritized_skills` by checking whether each technical skill string appears inside merged must-have or nice-to-have requirement text.
7. Normalize `role_type`, `seniority_level`, domain, soft skills, verbs, and culture signals.
8. Extract years of experience with a regex and choose the minimum explicit value.

### Current Deterministic Extraction Logic

Implemented in `src/resume_optimizer/job_normalizers.py`.

| Logic | Implementation | Current behavior | Current problem |
| --- | --- | --- | --- |
| Skill detection | `detect_technical_keywords()` | Tokenizes the entire JD and runs taxonomy skill normalization over every token | Very shallow; no section awareness, no phrase ownership, no requirement weighting |
| Must-have extraction | `extract_requirement_markers()` with `MUST_HAVE_MARKERS` | Marks any sentence containing `must have`, `required`, `requirements`, `minimum qualifications`, `you will need` | Sentence-level substring match is brittle and over-broad |
| Nice-to-have extraction | `extract_requirement_markers()` with `NICE_TO_HAVE_MARKERS` | Marks any sentence containing `nice to have`, `preferred`, `preferred qualifications`, `bonus`, `plus` | Same brittleness; can misclassify incidental text |
| Years extraction | `extract_years_experience_requirement()` | Regex over whole JD, returns the minimum match | Can understate experience requirement when both min and preferred years appear |
| Skill priority derivation | `_skill_is_required()` and `_skill_is_preferred()` | Uses substring inclusion of skill name inside requirement text | No notion of section, bullet structure, or requirement strength |

### Current LLM Prompt Contract

Prompt file: `src/resume_optimizer/prompts/phase1_job_analysis_prompt.txt`

The current prompt contract requires only these fields:

- `technical_skills`
- `soft_skills`
- `seniority_level`
- `role_type`
- `industry_domain`
- `key_action_verbs`
- `must_have_requirements`
- `nice_to_have_requirements`
- `company_culture_signals`

What the prompt does not ask for:

- Explicit target title or title family
- Role family separate from org role mode
- Management scope or people-management requirement
- Technical depth areas
- Delivery scope
- Architecture/ownership expectations
- Stakeholder/cross-functional expectations
- Domain confidence or multiple domains
- Requirement provenance
- Requirement classification confidence
- Explicit hard constraints vs inferred preferences
- Remote/hybrid/onsite work mode
- Location or authorization constraints
- Education/certification constraints
- Distinction between core responsibilities and qualification filters

The prompt therefore cannot produce a rich job-understanding object even if the model performs well.

## Current Modeling Defects

### 1. `role_type` mixes technical role family with org role mode

This is the central schema defect.

Current enum in `src/resume_optimizer/models.py` defines `RoleType` as org mode values:

- `individual_contributor`
- `manager`
- `lead`
- `consultant`
- `founder`
- `researcher`
- `student`
- `advisor`

Current role taxonomy in `src/resume_optimizer/config/taxonomy/role_types.json` defines `role_types` as technical families plus org-like categories:

- `frontend`
- `backend`
- `fullstack`
- `devops`
- `data`
- `ml`
- `product`
- `design`
- `management`
- `individual_contributor`
- `leadership`

`normalize_role_type()` in `src/resume_optimizer/normalizers.py` tries to normalize against that taxonomy and then coerce the result into the `RoleType` enum. Consequences:

- A raw LLM `role_type = "backend"` normalizes to taxonomy canonical `backend`, but `backend` is not a valid `RoleType`, so the function falls back to a small alias map and ultimately returns `None`.
- A raw LLM `role_type = "engineering manager"` normalizes to taxonomy canonical `management`, but `management` is not a valid `RoleType`, so the same fallback happens.
- Title inference code in `src/resume_optimizer/normalization/engine.py` still emits `role_type_hint` values like `backend`, `frontend`, `management`, and `leadership`, which are not aligned with `RoleType`.

Result:

- The field name `role_type` is misleading.
- The taxonomy name `role_types.json` is misleading.
- The system currently conflates:
  - technical role family: backend, frontend, fullstack, data, ML, product, design
  - org role mode: IC, lead, manager, director, executive

This exact mixing point is why Phase 1 job understanding is shallow and semantically unstable downstream.

### 2. Seniority taxonomy contains values that the enum rejects

Current seniority enum in `src/resume_optimizer/models.py`:

- `intern`
- `junior`
- `mid`
- `senior`
- `staff`
- `principal`
- `director`
- `executive`

Current taxonomy in `src/resume_optimizer/config/taxonomy/seniority.json` also includes:

- `lead`
- `manager`

`normalize_seniority()` attempts to normalize to the taxonomy first, then coerce to the enum. Consequences:

- A raw `lead` seniority may normalize to `lead` but cannot be represented in `SeniorityLevel`.
- A raw `manager` seniority may normalize to `manager` but cannot be represented in `SeniorityLevel`.

This is another schema collision between level and org mode.

### 3. Phase 2 compensates for Phase 1 gaps with fallback inference

`adapt_job_analysis_to_ranking_features()` currently re-infers missing information from the already-normalized Phase 1 output:

- infers role type if missing
- infers seniority if missing
- derives skills from requirement text if sparse
- promotes top technical skills into must-have if explicit must-have skills are missing

This means downstream ranking quality already depends on compensating for weak Phase 1 extraction rather than trusting it.

### 4. Verification has a field-name bug already

`backend/app/services/verification/orchestrator.py` reads `preferred_requirements`, but `NormalizedJobAnalysis` exposes `nice_to_have_requirements`.

Current effect:

- verification keyword checks silently ignore preferred requirements from Phase 1

This is a concrete backward-compatibility risk for any migration that renames fields again without an adapter.

### 5. Current prompt and schema force single-value collapse

Current Phase 1 stores:

- one `role_type`
- one `seniority_level`
- one `industry_domain`

That flattening discards useful ambiguity:

- a role can require backend + platform + distributed systems
- a role can be IC today but with mentoring expectations
- a role can include both fintech and developer-tools context

The current schema leaves no room to represent this without overloading fields.

## Exact Downstream Dependency Map

This section lists every later-phase consumer of current Phase 1 output found in the repo.

### Dependency Map Summary

| Consumer | File | Reads from Phase 1 | Notes |
| --- | --- | --- | --- |
| Phase 1 API | `src/resume_optimizer/app.py` | whole `NormalizedJobAnalysis` | `/api/analyze-job` response |
| Phase 2 adapter | `src/resume_optimizer/job_feature_adapter.py` | all major fields | Converts Phase 1 into ranking features |
| Phase 2 service | `src/resume_optimizer/ranking_service.py` | whole `NormalizedJobAnalysis` | Builds ranking artifacts and headline suggestion |
| Phase 2 schemas | `src/resume_optimizer/phase2_models.py` | whole model embedded | `JobAnalysisInput` subclasses `NormalizedJobAnalysis` |
| Phase 2 service wrapper | `src/resume_optimizer/services/phase2_service.py` | whole model embedded and persisted | Persistence record stores `job_analysis` |
| Phase 3 schemas | `src/resume_optimizer/phase3_models.py` | whole model embedded | `Phase3JobAnalysisInput` subclasses `NormalizedJobAnalysis` |
| Phase 3 assembler | `src/resume_optimizer/phase3_assembler.py` | role, seniority, skills, requirements, culture, verbs | Produces generator-facing role context |
| Phase 4 schema | `backend/app/schemas/verification.py` | whole model embedded | `Phase3VerificationInput.job_analysis` |
| Phase 4 verification | `backend/app/services/verification/orchestrator.py` | `technical_skills`, `must_have_requirements`, attempted `preferred_requirements` | Existing bug |
| Phase 6 parser adapter | `backend/app/orchestration/adapters/job_parser_adapter.py` | raw + normalized output | Wraps parser for orchestration |
| Phase 6 pipeline IO | `backend/app/orchestration/pipeline_models.py` | whole model embedded | Parse, rank, generate, verify stages |
| Phase 6 orchestrator | `backend/app/orchestration/orchestrator.py` | whole model passed to later stages and persisted | Inline artifact snapshots |
| Verification-aware route | `backend/app/services/pipeline_service.py` | whole model passed to Phase 3 and Phase 4 | Legacy direct route |
| Direct Phase 3 route | `backend/app/api/routes/resume.py` | accepts Phase 3 input containing job analysis | API compatibility surface |
| Full pipeline route | `backend/app/api/routes/generate_resume.py` | reaches parse stage indirectly | Orchestration entrypoint |

### Detailed Field Consumption By Later Phase

#### Phase 2 ranking feature adapter

File: `src/resume_optimizer/job_feature_adapter.py`

Field-level use:

- `prioritized_skills`
- `technical_skills`
- `must_have_requirements`
- `nice_to_have_requirements`
- `role_type`
- `seniority_level`
- `industry_domain`
- `key_action_verbs`
- `soft_skills`
- `company_culture_signals`
- `years_experience_required`

Behavior:

- Builds `JobRankingFeatures`, which becomes the real job representation used for scoring.
- Re-derives must-have/nice-to-have skill buckets from Phase 1 strings.
- Converts role and seniority into scoring signals.
- Converts domain, verb, culture, and requirement text into derived feature buckets.

Migration implication:

- Any Phase 1 rebuild that changes field names or semantics must either:
  - update this file directly, or
  - introduce a dedicated adapter from the new Phase 1 contract to `JobRankingFeatures`

#### Phase 2 ranking service

File: `src/resume_optimizer/ranking_service.py`

Field-level use:

- Entire `NormalizedJobAnalysis` passed into `adapt_job_analysis_to_ranking_features()`
- `role_type` and `seniority_level` also used directly for `_build_headline_suggestion()`
- Entire `job_analysis` embedded inside `Phase2SelectionResult`

Migration implication:

- Phase 2 artifact persistence and downstream equality checks depend on serializing the legacy Phase 1 contract.

#### Phase 3 assembler

File: `src/resume_optimizer/phase3_assembler.py`

Field-level use:

- `prioritized_skills`
- `technical_skills`
- `role_type`
- `seniority_level`
- `industry_domain`
- `must_have_requirements`
- `nice_to_have_requirements`
- `company_culture_signals`
- `key_action_verbs`

Behavior:

- Builds `Phase3RoleContext`.
- Maps Phase 1 `nice_to_have_requirements` into Phase 3 `preferred_requirements`.

Migration implication:

- If Phase 1 stops exposing direct `role_type` and `seniority_level`, Phase 3 needs explicit new fields for target org mode, target role family, and target level.

#### Phase 4 verification

Schema file: `backend/app/schemas/verification.py`

Behavior:

- Embeds full `NormalizedJobAnalysis` into `Phase3VerificationInput`.

Orchestrator file: `backend/app/services/verification/orchestrator.py`

Field-level use:

- `technical_skills`
- `must_have_requirements`
- attempted `preferred_requirements` read, which is wrong for current schema

Migration implication:

- Verification currently uses Phase 1 mostly as a keyword list, not a real semantic job target model.
- Field rename migration needs an explicit compatibility adapter because verification is already inconsistent with the current contract.

#### Phase 6 orchestration

Files:

- `backend/app/orchestration/pipeline_models.py`
- `backend/app/orchestration/adapters/job_parser_adapter.py`
- `backend/app/orchestration/orchestrator.py`

Behavior:

- Phase 6 persists `ParseJobDescriptionOutput` inline as the `job_analysis` artifact.
- Phase 6 passes `parsed.normalized_analysis` directly into Phase 2, Phase 3, and Phase 4 stage inputs.

Migration implication:

- Artifact schema versioning matters.
- A new Phase 1 contract must not silently replace the persisted artifact payload without a versioned artifact change.

## Current Tests And Fixtures Coupled To Phase 1

### Direct Phase 1 test coverage

There are no live dedicated Phase 1 tests under `backend/app/tests/**`, `backend/tests/**`, or `src/**`.

Stale packaging metadata in `src/resume_optimizer.egg-info/SOURCES.txt` references `tests/test_phase1_core.py` and `tests/test_phase1_api.py`, but those files are not present in the working tree.

Migration implication:

- Phase 1 currently has weak direct regression protection.
- Rebuild work must add direct parser, normalization, and contract tests before removing legacy behavior.

### Tests and fixtures that instantiate the legacy contract

Observed direct dependencies:

- `backend/tests/orchestration/pipeline_harness.py`
- `backend/app/tests/unit/test_phase3_assembler_regression.py`
- `backend/app/tests/unit/test_verification_orchestrator.py`
- `backend/app/tests/unit/test_verification_schemas.py`
- `backend/app/tests/unit/test_phase2_skill_selection.py`
- `backend/app/tests/unit/test_phase2_resume_selection.py`
- `backend/app/tests/unit/test_phase2_pipeline_integration.py`
- `backend/app/tests/unit/test_phase2_end_to_end_artifacts.py`
- `backend/app/tests/unit/test_semantic_scoring.py`
- `backend/app/tests/fixtures/phase2_candidate_profiles.py`
- `backend/app/tests/fixtures/phase3_eval/eval_cases.json`
- `backend/app/scripts/run_phase4_eval.py`
- `backend/tests/orchestration/test_pipeline_regression_harness.py`

Migration implication:

- The test estate is mostly Phase 2+ tests that hard-code `NormalizedJobAnalysis`.
- Breaking the legacy contract without an adapter will cascade through Phase 2, Phase 3, verification, orchestration, eval harnesses, and fixtures.

## Files To Keep, Modify, Deprecate, And Add

### Keep

These remain valid concepts and should stay, though some will still require caller updates.

| File | Keep rationale |
| --- | --- |
| `src/resume_optimizer/openai_client.py` | Reusable OpenAI Responses API wrapper |
| `src/resume_optimizer/prompt_loader.py` | Keep prompt loading mechanism; update prompt paths and formatter functions as needed |
| `backend/app/orchestration/adapters/job_parser_adapter.py` | Keep adapter role; swap in rebuilt parser service |
| `backend/app/orchestration/pipeline_models.py` | Keep orchestration stage model structure; update Phase 1 payload types/versioning |
| `backend/app/orchestration/orchestrator.py` | Keep orchestration flow; update artifact schema versioning and parser output wiring |
| `src/resume_optimizer/job_feature_adapter.py` | Keep Phase 2 feature-adapter responsibility, but retarget to the new Phase 1 contract through an adapter layer |
| `src/resume_optimizer/ranking_service.py` | Keep ranking service; it should not own Phase 1 reconstruction logic |
| `src/resume_optimizer/phase3_assembler.py` | Keep Phase 3 assembly responsibility; update input mapping |
| `backend/app/services/verification/orchestrator.py` | Keep verification stage; update keyword extraction to new Phase 1 contract |

### Modify

These files require direct code changes during the rebuild.

| File | Required change |
| --- | --- |
| `src/resume_optimizer/job_models.py` | Freeze as legacy compatibility models or trim to only raw request + legacy adapter output; do not keep as the primary rebuilt Phase 1 schema |
| `src/resume_optimizer/ai_service.py` | Replace current single-call parser flow with rebuilt parser orchestration; stop returning the final product-contract directly |
| `src/resume_optimizer/prompts/phase1_job_analysis_prompt.txt` | Replace with a richer, explicit extraction contract or supersede with a new v2 prompt |
| `src/resume_optimizer/job_normalizers.py` | Reduce to legacy-adapter normalization only, or replace with new deterministic enrichment pipeline plus explicit compatibility mapping |
| `src/resume_optimizer/normalizers.py` | Split technical role-family normalization from org-role-mode normalization |
| `src/resume_optimizer/constants.py` | Separate org role mode vocabulary from technical role family vocabulary; remove mixed alias assumptions |
| `src/resume_optimizer/config/taxonomy/role_types.json` | Rename or replace taxonomy to reflect technical role family, not org role mode |
| `src/resume_optimizer/config/taxonomy/seniority.json` | Remove non-seniority categories such as `manager`, and move `lead` handling to the correct dimension |
| `src/resume_optimizer/normalization/engine.py` | Update title inference to emit distinct dimensions: role family, org role mode, seniority/level |
| `src/resume_optimizer/job_feature_adapter.py` | Consume the rebuilt contract or a dedicated Phase 1 -> Phase 2 adapter instead of assuming `NormalizedJobAnalysis` is the source-of-truth model |
| `src/resume_optimizer/phase2_models.py` | Stop subclassing the legacy Phase 1 model directly; use an explicit compatibility DTO if needed |
| `src/resume_optimizer/ranking_models.py` | Same compatibility update for request/response validation |
| `src/resume_optimizer/ranking_service.py` | Use compatibility adapter for legacy headline and persisted Phase 2 artifacts |
| `src/resume_optimizer/services/phase2_service.py` | Update persistence record format if `job_analysis` storage contract changes |
| `src/resume_optimizer/phase3_models.py` | Replace `Phase3JobAnalysisInput(NormalizedJobAnalysis)` with a dedicated Phase 3-facing target context input or compatibility DTO |
| `src/resume_optimizer/phase3_assembler.py` | Map rebuilt Phase 1 fields into explicit Phase 3 target context fields |
| `backend/app/schemas/verification.py` | Stop embedding the legacy Phase 1 contract directly if Phase 4 only needs a derived verification target contract |
| `backend/app/services/verification/orchestrator.py` | Fix `preferred_requirements` bug and update to new verification-facing Phase 1 adapter |
| `src/resume_optimizer/app.py` | `/api/analyze-job` should eventually return the rebuilt Phase 1 contract or a versioned response model; keep legacy endpoint shape only if explicitly required |
| `backend/app/services/pipeline_service.py` | Update Phase 3/Phase 4 handoff request creation |
| `backend/app/tests/**` and `backend/tests/**` files listed above | Update fixtures and assertions to new contract or compatibility DTO |

### Deprecate

These should not remain the long-term Phase 1 source-of-truth surface.

| File or contract | Deprecation action |
| --- | --- |
| `src/resume_optimizer/job_models.py::NormalizedJobAnalysis` | Deprecate as the primary Phase 1 domain model; keep temporarily as legacy compatibility output only |
| `src/resume_optimizer/job_models.py::ParsedJobAnalysisResponse` | Deprecate as the primary raw extraction schema; replace with richer raw extraction schema |
| `src/resume_optimizer/job_normalizers.py::normalize_job_analysis()` | Deprecate current implementation; retain only as a legacy adapter if needed |
| `src/resume_optimizer/prompts/phase1_job_analysis_prompt.txt` | Deprecate current prompt contract because it cannot represent the target job-understanding model |
| direct subclassing of `NormalizedJobAnalysis` in `src/resume_optimizer/phase2_models.py` and `src/resume_optimizer/phase3_models.py` | Deprecate; replace with explicit phase-specific inputs or compatibility DTOs |

### Add

These files should be added as part of the rebuild. This is the recommended exact file set to isolate the new Phase 1 domain model from the legacy compatibility surface.

| File | Purpose |
| --- | --- |
| `src/resume_optimizer/phase1_models.py` | New primary Phase 1 domain models: raw extraction, deterministic enrichment, canonical target-job contract |
| `src/resume_optimizer/phase1_parser.py` | End-to-end Phase 1 parser orchestration replacing the current logic in `ai_service.py` |
| `src/resume_optimizer/phase1_deterministic_extractors.py` | Deterministic JD structure parsing, requirement extraction, years extraction, section-aware keyword extraction |
| `src/resume_optimizer/phase1_legacy_adapter.py` | Explicit adapter from the new Phase 1 contract to legacy `NormalizedJobAnalysis` for downstream compatibility during migration |
| `src/resume_optimizer/prompts/phase1_job_analysis_v2_prompt.txt` | New prompt contract for richer role understanding |
| `backend/app/tests/unit/test_phase1_parser.py` | Direct parser flow tests |
| `backend/app/tests/unit/test_phase1_deterministic_extractors.py` | Deterministic extraction tests |
| `backend/app/tests/unit/test_phase1_legacy_adapter.py` | Compatibility tests proving the new contract can still feed current downstream consumers during migration |
| `backend/app/tests/fixtures/phase1_job_descriptions.json` | Stable JD fixtures for parser regression coverage |

## File-By-File Migration Checklist

### Phase 1 source files

- `src/resume_optimizer/job_models.py`
  - Keep `RawJobDescriptionRequest`.
  - Freeze `ParsedJobAnalysisResponse` and `NormalizedJobAnalysis` as legacy compatibility contracts only.
  - Add deprecation comments pointing callers to `phase1_models.py`.
- `src/resume_optimizer/ai_service.py`
  - Move parser orchestration responsibility into `phase1_parser.py`.
  - Leave only thin compatibility wrappers if existing imports need to keep working.
- `src/resume_optimizer/job_normalizers.py`
  - Split current logic into:
    - new deterministic extraction/enrichment in `phase1_deterministic_extractors.py`
    - legacy mapping in `phase1_legacy_adapter.py`
- `src/resume_optimizer/prompt_loader.py`
  - Add loader/formatter helpers for `phase1_job_analysis_v2_prompt.txt`.
  - Keep legacy loader until all callers are migrated.
- `src/resume_optimizer/prompts/phase1_job_analysis_prompt.txt`
  - Mark as legacy.
- `src/resume_optimizer/prompts/phase1_job_analysis_v2_prompt.txt`
  - Add new prompt with explicit contract for target title, technical role family, org role mode, seniority, hard requirements, preferred requirements, domain, and scope signals.

### Taxonomy and normalization

- `src/resume_optimizer/constants.py`
  - Separate vocabularies:
    - technical role family
    - org role mode
    - seniority/level
- `src/resume_optimizer/normalizers.py`
  - Add dedicated normalizers for:
    - technical role family
    - org role mode
    - seniority level
  - Stop using `normalize_role_type()` as the semantic catch-all.
- `src/resume_optimizer/config/taxonomy/role_types.json`
  - Replace with `technical_role_families.json` during rebuild.
- `src/resume_optimizer/config/taxonomy/seniority.json`
  - Remove non-level categories.
- `src/resume_optimizer/normalization/engine.py`
  - Update title inference to emit the new dimensions explicitly.

### Phase 2 integration

- `src/resume_optimizer/job_feature_adapter.py`
  - Add a formal adapter from the new Phase 1 contract to `JobRankingFeatures`.
  - Remove hidden fallback compensation that should live in Phase 1.
- `src/resume_optimizer/phase2_models.py`
  - Replace direct inheritance from `NormalizedJobAnalysis` with a dedicated Phase 2 target input DTO.
- `src/resume_optimizer/ranking_models.py`
  - Update coercion logic for the new Phase 2 target input DTO.
- `src/resume_optimizer/ranking_service.py`
  - Update headline suggestion logic to use explicit org role mode and level rather than the overloaded `role_type`.
- `src/resume_optimizer/services/phase2_service.py`
  - Decide whether persisted `job_analysis` remains legacy-compatible or versioned separately.

### Phase 3 integration

- `src/resume_optimizer/phase3_models.py`
  - Replace `Phase3JobAnalysisInput(NormalizedJobAnalysis)` with a dedicated Phase 3 target-context input model.
- `src/resume_optimizer/phase3_assembler.py`
  - Stop treating `role_type` as the single role descriptor.
  - Map technical role family, org role mode, seniority level, hard requirements, preferred requirements, and domain targets explicitly into `Phase3RoleContext`.

### Phase 4 integration

- `backend/app/schemas/verification.py`
  - Narrow Phase 4 input to only the Phase 1-derived fields verification actually needs.
  - If full embedding is kept, version it explicitly.
- `backend/app/services/verification/orchestrator.py`
  - Fix `preferred_requirements` vs `nice_to_have_requirements`.
  - Update keyword extraction to use the rebuilt field names and categories.

### Phase 6 orchestration and API

- `backend/app/orchestration/adapters/job_parser_adapter.py`
  - Point to the new parser service.
  - Emit both new and legacy artifacts if transitional compatibility is required.
- `backend/app/orchestration/pipeline_models.py`
  - Version the parse-stage output so the new Phase 1 artifact is distinguishable from the legacy one.
- `backend/app/orchestration/orchestrator.py`
  - Persist the new Phase 1 artifact schema version.
  - Keep downstream stage inputs stable through compatibility adapters until each phase is migrated.
- `src/resume_optimizer/app.py`
  - Decide whether `/api/analyze-job` stays legacy or becomes versioned.
- `backend/app/api/routes/resume.py`
  - Update if direct Phase 3 request shape changes.
- `backend/app/services/pipeline_service.py`
  - Update Phase 3 and verification request construction.

### Tests and fixtures

- Add direct Phase 1 tests before migrating downstream tests.
- Update all fixture builders that instantiate `NormalizedJobAnalysis`.
- Update orchestration harness snapshots if artifact payload shape changes.
- Add fixture cases that prove:
  - backend IC role
  - frontend IC role
  - staff/principal IC role
  - engineering manager role
  - director role
  - ambiguous lead role
  - multi-domain role

## Backward Compatibility Risks

1. `NormalizedJobAnalysis` is embedded directly in `Phase2SelectionResult`, `Phase3AssemblerInput`, `Phase3VerificationInput`, and Phase 6 stage outputs.
2. `Phase3AssemblerInput` and related models validate equality between `phase2_selection.job_analysis` and `job_analysis`. Any contract drift will trip model validation.
3. Verification already contains a field-name mismatch. A partial migration could create silent keyword-loss bugs.
4. Phase 6 persists inline artifacts for `job_analysis`; replacing payload shape without versioning breaks historical artifact interpretation.
5. Multiple tests and fixtures construct `NormalizedJobAnalysis` directly. Removing or renaming fields will produce broad test fallout even before behavior changes.
6. Headline generation in Phase 2 depends on current enum values like `individual_contributor`, `manager`, and `lead`. If those semantics move, headline logic must move too.
7. Current routes expose `NormalizedJobAnalysis` publicly through `/api/analyze-job` and consume it through `/api/rank-resume-content`.

## Concrete Implementation Risks

1. Mis-separating technical role family and org role mode will reintroduce the current defect under different names.
2. Keeping old field names but changing semantics will create silent regressions because many consumers only check model validation, not meaning.
3. Rebuilding Phase 1 without a legacy adapter will force a cross-phase rewrite instead of a staged migration.
4. Reusing `role_type` for any new concept will preserve existing ambiguity.
5. Treating `lead` as seniority in some places and org mode in others will keep selection, generation, and verification inconsistent.
6. Persisting only the new contract and dropping the raw extraction artifact will reduce debuggability compared with the current `raw_analysis + normalized_analysis` parse output.
7. Moving too much fallback logic into Phase 2 again will hide Phase 1 quality regressions.
8. Failing to add direct Phase 1 regression fixtures will make prompt revisions unsafe.

## Recommended Migration Sequence

1. Add the new Phase 1 domain model, deterministic extractors, parser orchestration, prompt, and direct tests.
2. Add a legacy adapter that maps the new contract into `NormalizedJobAnalysis`.
3. Swap Phase 6 and `/api/analyze-job` to run the new parser internally but keep emitting the legacy compatibility model.
4. Fix verification’s current field-name bug while introducing an explicit compatibility mapping.
5. Migrate Phase 2 to consume the new Phase 1 contract through a dedicated adapter rather than direct inheritance from `NormalizedJobAnalysis`.
6. Migrate Phase 3 target-context assembly to the new explicit role fields.
7. Narrow Phase 4 to a purpose-built verification input derived from the rebuilt contract.
8. After all later phases stop depending on `NormalizedJobAnalysis` as the source-of-truth contract, deprecate the legacy adapter and legacy prompt.

## Decisions Required Before Implementation

These are the design decisions the rebuild should lock before code changes begin.

1. Define separate canonical fields for:
   - technical role family
   - org role mode
   - seniority level
2. Decide whether target title is a first-class Phase 1 field or a derived convenience field.
3. Decide whether Phase 1 should produce one canonical job target or a scored list of candidate target interpretations when the JD is ambiguous.
4. Decide whether `/api/analyze-job` remains backward compatible or becomes a versioned endpoint.
5. Decide artifact versioning for Phase 6 persisted `job_analysis`.

## Bottom Line

The current Phase 1 implementation is not just shallow; its core contract is semantically inconsistent. The main break is that `role_type` is used as both technical role family and org role mode, while `seniority` also partially absorbs org-mode concepts such as `lead` and `manager`. Because `NormalizedJobAnalysis` is embedded directly across Phases 2 through 6, the rebuild must be staged behind an explicit legacy adapter rather than replacing the current contract in place.
