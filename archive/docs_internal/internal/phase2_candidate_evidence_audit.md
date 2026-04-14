# Phase 2 Candidate Evidence Audit

Compatibility note: this audit still refers to "Phase 4 verification" in some historical sections. Current runtime verification behavior is Phase 6.

## Scope

This document maps the current runtime paths that load candidate profile data, normalize it, represent profile entities, extract/rank/select evidence, and feed those artifacts into generation, verification, and rendering.

This is an implementation audit only. It does not propose a full redesign.

## End-to-End Flow

1. Profile JSON is loaded from disk or accepted inline as a `MasterProfile`.
2. Raw payloads are normalized and parsed into the strict source schema in [`src/resume_optimizer/models.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/models.py).
3. The normalized `MasterProfile` is converted into Phase 2 canonical evidence units by [`src/resume_optimizer/evidence_builder.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/evidence_builder.py).
4. Canonical units are scored and projected into legacy Phase 2 response contracts in [`src/resume_optimizer/ranking_service.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/ranking_service.py).
5. Phase 3 collapses selected evidence units back onto source profile entries and bullets in [`src/resume_optimizer/phase3_assembler.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/phase3_assembler.py).
6. The Phase 6 verification gate and Phase 5 rendering still consume the source `MasterProfile` directly for some sections, rather than depending only on a canonical evidence graph.

## Source Loading And Normalization

| Source file | Class / function | Purpose | Current input schema | Current output schema | Downstream dependents |
| --- | --- | --- | --- | --- | --- |
| [`src/resume_optimizer/loaders.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/loaders.py) | `load_master_profile(path)` | Read JSON and parse into strict source model | `str | Path` to JSON object payload | `MasterProfile` | `load_and_normalize_master_profile`, `Phase2Service.run_for_default_profile` |
| [`src/resume_optimizer/loaders.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/loaders.py) | `load_and_normalize_master_profile(path)` | Load and normalize a profile from disk | `str | Path` | `MasterProfile` | backend orchestrator `_load_source_profile`, `Phase2Service.run_for_default_profile` |
| [`src/resume_optimizer/loaders.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/loaders.py) | `load_validate_and_normalize(path)` | Load profile and return validation report | `str | Path` | `(MasterProfile, ProfileValidationReport)` | not on main pipeline path |
| [`src/resume_optimizer/validators.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/validators.py) | `parse_master_profile(payload)` | Normalize raw payload, then strict-validate | `Mapping[str, Any]` | `MasterProfile` | `load_master_profile` |
| [`src/resume_optimizer/normalizers.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/normalizers.py) | `normalize_master_profile_payload(payload)` | Pre-Pydantic payload cleanup and canonicalization | raw mapping with source-profile JSON shape | normalized `dict[str, Any]` | `parse_master_profile` |
| [`src/resume_optimizer/normalizers.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/normalizers.py) | `normalize_master_profile(profile)` | Post-parse model normalization | `MasterProfile` | normalized `MasterProfile` | loaders, backend orchestrator normalization stage |
| [`src/resume_optimizer/validators.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/validators.py) | `validate_master_profile(profile)` | Integrity checks beyond schema validation | `MasterProfile` | `ProfileValidationReport` | backend orchestrator normalization stage |
| [`backend/app/orchestration/orchestrator.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/orchestration/orchestrator.py) | `_load_source_profile(request)` | Phase 6 source profile entrypoint | `PipelineInput` | `LoadSourceProfileOutput(source_profile_id, source_profile, loaded_from)` | `_normalize_source_data`, artifact recorder |
| [`backend/app/orchestration/orchestrator.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/orchestration/orchestrator.py) | `_normalize_source_data(loaded)` | Normalize and validate profile before ranking | `LoadSourceProfileOutput` | `NormalizeSourceDataOutput(source_profile_id, normalized_profile, validation_warnings)` | ranking, generation, verification, rendering |

### Current normalization behavior

- String canonicalization exists for titles, role type, seniority, skill names, tool names, domain tags, and partial dates.
- Normalization is mostly field-level canonicalization, not evidence-level enrichment.
- The Phase 6 orchestrator currently normalizes twice for file-based profiles:
  - once inside `load_and_normalize_master_profile`
  - again inside `_normalize_source_data`
- Inline `request.source_profile` enters as an already-typed `MasterProfile`, then gets normalized later in `_normalize_source_data`.

## Current Profile Schema Representation

Primary schema lives in [`src/resume_optimizer/models.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/models.py).

| Entity | Current model | Key fields |
| --- | --- | --- |
| Candidate profile root | `MasterProfile` | `id`, `personal_profile`, `experience[]`, `projects[]`, `education[]`, `certifications[]`, `skills[]` |
| Personal profile | `PersonalProfile` | `full_name`, `headline`, `summary`, contact fields, `role_type`, `seniority_level` |
| Experience | `ExperienceEntry` | `organization`, `title`, `employment_type`, dates, `bullets[]`, `tools[]`, `metrics[]` |
| Project | `ProjectEntry` | `name`, `role`, dates, `summary`, `bullets[]`, `tools[]`, `metrics[]`, `link_url` |
| Education | `EducationEntry` | `institution`, `degree`, `field_of_study`, dates, `bullets[]`, `honors[]` |
| Certification | `CertificationEntry` | `name`, `issuer`, dates, credential fields |
| Skill | `SkillEntry` | `name`, `category`, `tools[]`, `metrics[]`, role/seniority hints |
| Bullet | `BulletEntry` | `id`, `text`, `tools[]`, `metrics[]`, ranking metadata |
| Metric | `MetricEntry` | `id`, `label`, `value`, `unit`, `context` |
| Source links | `SourceLink` | `source_type`, `source_id`, `source_url`, `excerpt`, `note` |

### Requested surface with current status

| Requested surface | Current status |
| --- | --- |
| experiences | modeled and used downstream |
| projects | modeled and used downstream |
| skills | modeled and used downstream |
| education | modeled but mostly bypassed by Phase 2 evidence extraction |
| certifications | modeled and partially used downstream |
| awards | not modeled anywhere in runtime code |

## Phase 2 Evidence Extraction And Ranking

| Source file | Class / function | Purpose | Current input schema | Current output schema | Downstream dependents |
| --- | --- | --- | --- | --- | --- |
| [`src/resume_optimizer/evidence_models.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/evidence_models.py) | `CanonicalEvidenceUnit` | Canonical rankable evidence record | normalized source-derived fields | canonical evidence unit | `ranking_service`, `provenance.py` |
| [`src/resume_optimizer/evidence_models.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/evidence_models.py) | `EvidenceProvenance` | Typed provenance attached to canonical evidence | source item/bullet metadata | typed provenance object | `ranking_service`, `provenance.py` |
| [`src/resume_optimizer/evidence_builder.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/evidence_builder.py) | `build_canonical_evidence_units(profile)` | Convert normalized source profile into rankable units | `MasterProfile` | `list[CanonicalEvidenceUnit]` | `ranking_service.build_phase2_ranking_artifacts` |
| [`src/resume_optimizer/evidence_builder.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/evidence_builder.py) | `_build_experience_units`, `_build_project_units`, `_build_certification_unit`, `_build_verified_skill_unit` | Per-entity evidence extraction | individual source entries | canonical evidence units | `build_canonical_evidence_units` |
| [`src/resume_optimizer/ranking_service.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/ranking_service.py) | `build_phase2_ranking_artifacts(job_analysis, source_profile)` | Main Phase 2 entrypoint: adapt job features, build evidence pool, score, rank, select | `NormalizedJobAnalysis`, `MasterProfile` | `Phase2RankingArtifacts(ranking_response, selection_result, job_features)` | ranker adapter, `Phase2Service`, eval harness |
| [`src/resume_optimizer/ranking_service.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/ranking_service.py) | `rank_evidence_for_job(...)` | Legacy wrapper over full artifact builder | `NormalizedJobAnalysis`, `MasterProfile` | `RankingResponse` | legacy/tests |
| [`src/resume_optimizer/ranking_models.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/ranking_models.py) | `RankingResponse` | Legacy Phase 2 response contract | ranked lists and summary hints | response DTO | Phase 3 assembler, orchestration pipeline, tests |
| [`src/resume_optimizer/phase2_models.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/phase2_models.py) | `Phase2SelectionResult` | Canonical Phase 2 selection output | scored evidence + selected subsets | selection DTO | Phase 3 assembler, orchestration pipeline |
| [`src/resume_optimizer/services/phase2_service.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/services/phase2_service.py) | `Phase2Service.run(...)` | Optional persistence and safe logging wrapper | `NormalizedJobAnalysis`, `MasterProfile` | `Phase2ServiceResult` | eval harness and future service integrations |
| [`backend/app/orchestration/adapters/ranker_adapter.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/orchestration/adapters/ranker_adapter.py) | `RankerAdapter.execute(...)` | Phase 6 adapter for Phase 2 | `RankSelectEvidenceInput(job_analysis, source_profile)` | `RankSelectEvidenceOutput(ranking_response, selection_result)` | Phase 6 orchestrator |

### What currently becomes evidence

- experience bullets
- experience summary units
- project bullets
- project summary units, only when `project.summary` exists
- certifications
- skills, only when not both `unverified` and `weak`

### What does not currently become Phase 2 evidence

- `personal_profile`
- `education`
- `education.bullets`
- `education.honors`
- `awards` because no runtime model exists

## Downstream Evidence Usage

### Phase 3 generation

| Source file | Class / function | Purpose | Current input schema | Current output schema | Downstream dependents |
| --- | --- | --- | --- | --- | --- |
| [`src/resume_optimizer/phase3_assembler.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/phase3_assembler.py) | `assemble_phase3_generation_payload(...)` | Main Phase 3 assembler entrypoint | `job_analysis`, `phase2_selection`, `source_profile`, `phase2_ranking` | `Phase3GenerationPayload` | `Phase3Service`, verification |
| [`src/resume_optimizer/phase3_assembler.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/phase3_assembler.py) | `_assemble_selected_experiences`, `_assemble_selected_projects` | Collapse evidence units back onto source entries and bullet IDs | `MasterProfile`, `Phase2SelectionResult` | compact Phase 3 selected payloads | generator |
| [`src/resume_optimizer/phase3_assembler.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/phase3_assembler.py) | `_assemble_matched_skills` | Lift selected skills from source profile | `MasterProfile`, `Phase2SelectionResult` | `Phase3SelectedSkillPayload[]` | generator |
| [`src/resume_optimizer/phase3_assembler.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/phase3_assembler.py) | `_assemble_selected_certifications` | Lift ranked certifications from ranking output | `MasterProfile`, `RankingResponse` | `Phase3SelectedCertificationPayload[]` | generator |
| [`src/resume_optimizer/services/phase3_service.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/services/phase3_service.py) | `Phase3Service.run(...)` | Assemble payload, plan, generate, validate | Phase 1 + Phase 2 outputs + source profile | `Phase3ServiceResult` | Phase 4 verification, Phase 6 orchestration |

### Phase 4 verification

| Source file | Class / function | Purpose | Current input schema | Current output schema | Downstream dependents |
| --- | --- | --- | --- | --- | --- |
| [`backend/app/schemas/verification.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/schemas/verification.py) | `Phase3VerificationInput` | Verification handoff contract | `source_profile_id`, `job_analysis`, `source_profile`, `generation_payload`, `phase3_result` | typed verification input | verification orchestrator |
| [`backend/app/services/verification/provenance_service.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/services/verification/provenance_service.py) | `ProvenanceService.build_for_phase3_result(...)` | Build provenance edges from Phase 3 output back to source truth | `MasterProfile`, `Phase3GenerationResult` | `ProvenanceMap` | verification orchestrator, persistence |
| [`backend/app/services/verification/matchers.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/services/verification/matchers.py) | `SourceIndex` | Build entity/bullet lookup index for deterministic matching | `MasterProfile` | in-memory index | provenance service |
| [`backend/app/services/verification/deterministic_validators.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/services/verification/deterministic_validators.py) | `_index_profile(source_profile)` and `SourceContext` builders | Flatten source profile text/tools for rule-based verification | `MasterProfile` | indexed dicts / aggregate validation context | deterministic validators |

### Phase 5 rendering

| Source file | Class / function | Purpose | Current input schema | Current output schema | Downstream dependents |
| --- | --- | --- | --- | --- | --- |
| [`backend/app/services/render_input_adapter.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/services/render_input_adapter.py) | `build_render_input_from_verified_output(...)` | Convert verified Phase 4 output plus source profile into render input | `MasterProfile`, `Phase4RenderingOutput`, `template_id`, `render_job_id` | `RenderJobInput` | render service |
| [`backend/app/services/render_input_adapter.py`](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/services/render_input_adapter.py) | `_build_education`, `_build_certifications`, `_build_personal_info` | Render sections still sourced directly from profile | `MasterProfile`, verification status | render section DTOs | render service |

## Current Input/Output Schema Notes

### Source profile shape

Current runtime source profile contract is `MasterProfile`, with top-level sections:

- `id`
- `personal_profile`
- `experience[]`
- `projects[]`
- `education[]`
- `certifications[]`
- `skills[]`

There is no top-level `awards[]`.

### Phase 2 canonical evidence shape

Current canonical evidence shape is `CanonicalEvidenceUnit`:

- identity: `evidence_unit_id`, `source_type`, `source_entity_id`, optional `source_bullet_id`
- content: `raw_text`
- normalized metadata: `normalized_skills`, `normalized_tools`, `normalized_domains`
- inferred metadata: `inferred_role_types`, `seniority_signals`, `impact_signals`
- support metadata: `metrics_present`, `recency`, `evidence_strength`, `verified_status`, `rewrite_allowed`
- provenance: typed `EvidenceProvenance`
- weakness metadata: `weak_evidence_tags`, `duplicate_of`

### Phase 2 legacy ranked shape

Current ranked payload shape is `ScoredEvidenceUnit`, projected for older consumers:

- `id` is the evidence-unit id, not the source profile id
- `source_item_id` is the source profile entity id
- `source_bullet_ids` holds source bullet ids when applicable
- `bullets` is only populated for bullet-backed evidence units
- `provenance` is downgraded to `dict[str, object]`

### Phase 2 selection shape

Current selection payload is `Phase2SelectionResult`:

- `scored_evidence[]` contains projected `ScoredEvidenceUnit`
- `selected_experiences[]` and `selected_projects[]` point back to `scored_evidence` through `source_item_id`, but that field stores the evidence-unit id in the selected models
- `candidate_profile_id` stores the root profile id only

This is valid per current code, but the naming is misleading and easy to misuse.

## Architectural Issues Blocking A Proper Evidence Model

1. `awards` are completely absent.
   No source schema, normalization path, evidence extraction path, ranking path, or downstream contracts exist for awards.

2. `education` is modeled but excluded from Phase 2 evidence.
   Education exists in `MasterProfile`, validators, and rendering, but `build_canonical_evidence_units` ignores it entirely.

3. Evidence coverage is partial and product behavior still depends on raw source profile objects.
   Verification and rendering still index or render directly from `MasterProfile` for education, certifications, personal info, and fallback matching.

4. ID semantics are inconsistent across Phase 2 contracts.
   In `ScoredEvidenceUnit`, `id` means evidence-unit id and `source_item_id` means source entity id. In `SelectedExperience` and `SelectedProject`, `source_item_id` actually points to a scored evidence id, not a source entity id.

5. Provenance is strongly typed in canonical evidence, then flattened into untyped dict payloads.
   `EvidenceProvenance` becomes `dict[str, object]` in `ScoredEvidenceUnit.provenance`, which weakens contract safety and encourages ad hoc downstream access.

6. Source type naming is ambiguous across layers.
   The source schema uses `SourceType` for document/source-link origin, while Phase 2 uses `EvidenceSourceType` for evidence categories. Both are called “source type” in adjacent contexts.

7. Parent-child linkage is incomplete.
   Metrics have IDs but no explicit parent references. Evidence units carry `metric_ids`, but cross-item lineage is reconstructed indirectly from parent entries and bullet ownership.

8. Duplicate flattening/indexing logic exists in multiple downstream consumers.
   Profile text and bullet indexing are rebuilt separately in:
   - `resume_optimizer.validators`
   - `resume_optimizer.provenance`
   - `backend.app.services.verification.matchers`
   - `backend.app.services.verification.deterministic_validators`

9. Enrichment points are weak and implicit.
   Current normalization canonicalizes strings, but there is no explicit post-normalization enrichment stage for:
   - source span extraction
   - bullet-to-skill support strength
   - metric normalization
   - entity/bullet relationship materialization
   - source-document provenance expansion

10. The pipeline currently normalizes the profile more than once.
    File-based profiles are normalized in `load_and_normalize_master_profile` and again in the orchestrator normalization stage. That is safe today, but it obscures the true canonicalization boundary for a future evidence model.

11. Project summary evidence is conditional and asymmetric with experience.
    Experience always emits a summary unit, while project summary evidence only exists when `project.summary` is present.

12. Personal profile evidence is outside the Phase 2 evidence model.
    Headline/summary/contact context exists in source data and later rendering, but not as evidence units or selection inputs.

## Misleading Or Risky Names

- `source_item_id` in `SelectedExperience` and `SelectedProject`
  Current meaning: scored evidence id, not source profile entry id.
- `RankingResponse.ranked_experiences` / `ranked_projects`
  Current contents: evidence units projected into a legacy shape, not pure source entries.
- `source_type`
  Used for both document provenance (`SourceLink.source_type`) and evidence category (`CanonicalEvidenceUnit.source_type`).

## Minimal Safe Notes For Later Phases

- Treat `CanonicalEvidenceUnit` as the closest current precursor to the intended candidate evidence model.
- Treat `Phase2SelectionResult` and `RankingResponse` as compatibility surfaces that should likely be preserved while internals change.
- Any Phase 2 rebuild must preserve:
  - stable source item ids
  - stable source bullet ids
  - current Phase 3 assembler expectations
  - Phase 4 provenance alignment requirements
  - Phase 5 rendering access to non-ranked profile sections

## Recommended Next Implementation Sequence

1. Define a single Phase 2 candidate evidence schema with explicit entity ids, parent ids, evidence ids, and provenance typing.
2. Add source coverage for currently missing sections:
   - education
   - awards
   - optional personal profile evidence
3. Introduce one deterministic source-to-evidence extraction layer that materializes parent-child links and metric lineage once.
4. Replace ambiguous Phase 2 field naming while keeping compatibility adapters for current `RankingResponse` and `Phase2SelectionResult`.
5. Centralize profile indexing/provenance helpers so verification and ranking stop rebuilding parallel indexes.
6. Move downstream consumers toward typed evidence/provenance contracts instead of `dict[str, object]`.
7. Remove duplicate normalization boundaries after the new evidence extraction stage is stable.
