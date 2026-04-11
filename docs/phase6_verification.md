# Phase 6 Verification

Phase 6 is the mandatory post-generation safety gate. Phase 3 can generate candidate resume content, but nothing reaches deterministic rendering until Phase 6 verifies it and returns an acceptable decision.

## Flow

1. Phase 3 produces `Phase3GenerationResult` plus provenance-ready generation payloads.
2. `VerificationOrchestrator.run(...)` flattens the generated summary, bullets, and skill highlights into verification items.
3. Provenance matching links each generated item to source-backed evidence.
4. Deterministic validators run first for unsupported metrics, tools, ownership, leadership, scope, domain, certification, keyword insertion, and other lexical overclaim patterns.
5. The dedicated `SummaryVerifier` runs claim-level checks for summary text instead of reusing the bullet path.
6. Semantic verification runs for summaries and rewritten bullets when enabled. If it cannot run, Phase 6 emits an explicit `semantic_verification_unavailable` issue instead of silently skipping.
7. `VerificationDecisionEngine` converts item issues into canonical outcomes:
   - `pass`
   - `pass_with_warnings`
   - `repair_and_pass`
   - `regenerate_target`
   - `fail_closed`
8. `FallbackRepairService` applies only conservative, auditable repairs. Repaired content replaces unsafe generated content downstream.
9. The orchestration gate allows rendering only for `pass`, `pass_with_warnings`, and `repair_and_pass`.
10. The pipeline persists a full verification report and, by default, a compact verification audit artifact.

## Canonical Contract

The public verification contract lives in [verification.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/schemas/verification.py).

Stable concepts:

- Issues use `IssueCategory` and `IssueSeverity`.
- Decisions use `VerificationDecisionOutcome`.
- Repairs use `FallbackAction` plus `VerificationRepairRecord`.
- Run-level audit uses `VerificationDecisionAudit`, `SemanticVerificationAudit`, and `VerificationRepairAudit`.

Compatibility note:

- Some schema ids and class names still include `phase4` because those contracts already existed. Runtime behavior and documentation should now be read as Phase 6.

## Adding A Validator

1. Add a pure or near-pure check in [deterministic_validators.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/services/verification/deterministic_validators.py) or [summary_verifier.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/services/verification/summary_verifier.py) when it is summary-specific.
2. Operate only on generated content, provenance-backed source context, and selected-content context.
3. Return canonical `VerificationIssue` objects. Do not return booleans or ad hoc warnings.
4. Reuse normalization helpers and configured allowlists/denylists before adding new phrase logic.
5. Add focused unit coverage and, if the behavior matters operationally, one realistic regression fixture.

Do not:

- bury decision logic inside the validator
- silently repair content inside the validator
- invent source support from job-description keywords alone

## Severity And Decision Policy

Severity levels:

- `info`
- `low`
- `medium`
- `high`
- `critical`

The decision engine is centralized in [decision_engine.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/services/verification/decision_engine.py).

High-level policy:

- Critical unsupported claims fail closed unless there is an explicit safe fallback.
- High-severity summary issues prefer safe summary fallback; otherwise they regenerate or block.
- Medium bullet issues prefer source-backed repair.
- Repeated medium issues within the same section escalate to targeted regeneration.
- Degraded semantic coverage lowers confidence and is visible in audit output.

## Fallback Repair

Repair logic lives in [fallback_repair.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/services/verification/fallback_repair.py).

Supported repair strategies:

- replace unsupported bullet rewrites with source bullets
- downgrade risky verbs to evidence-safe wording when deterministic
- rebuild summaries from controlled supported inputs
- remove unsupported skill highlights or replace with deterministic aliases
- strip unsupported certification, award, domain, scope, and leadership fragments when safe

Every repair attempt produces a `VerificationRepairRecord`. If safe repair is not possible, the record marks `requires_regeneration`.

## Semantic Verification

Semantic verification is configured through `Settings` in [config.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/src/resume_optimizer/config.py).

Defaults:

- `PHASE6_SEMANTIC_VERIFICATION_ENABLED=true`
- `PHASE6_SEMANTIC_VERIFICATION_STRICT_MODE=true`
- `PHASE6_SEMANTIC_VERIFIER_UNAVAILABLE_BEHAVIOR=block`
- `PHASE6_AUDIT_PERSISTENCE_ENABLED=true`

Backwards-compatible `PHASE4_*` environment names still work as fallbacks.

## Audit Artifacts

Audit artifact building lives in [audit_artifact.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/services/verification/audit_artifact.py).

By default, every real Phase 6 run persists:

- the full verification report
- the compact `verification_audit` artifact

The audit artifact includes:

- run ids and timestamp
- verifier coverage
- degraded mode indicators
- issue summaries
- counts by severity and issue type
- affected items
- repair summaries
- final decision and confidence
- concise internal summary text

Storage locations:

- `pipeline_artifacts` as `verification_audit`
- `verification_runs.raw_artifact_refs["verification_audit"]` when repository persistence is enabled

## Logs

High-signal runtime logs are emitted for:

- verification start and completion
- semantic degradation
- prepared summary fallback plans
- verification gate decisions

Logs should record status, decision, counts, and degraded mode, but not dump full generated content.

## Relevant Tests

- [test_deterministic_validators.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/tests/unit/test_deterministic_validators.py)
- [test_summary_verifier.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/tests/unit/test_summary_verifier.py)
- [test_verification_decision_engine.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/tests/unit/test_verification_decision_engine.py)
- [test_fallback_repair_service.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/tests/unit/test_fallback_repair_service.py)
- [test_phase6_verification_gate.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/tests/integration/test_phase6_verification_gate.py)
- [test_phase4_eval_suite.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/tests/integration/test_phase4_eval_suite.py)
