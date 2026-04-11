"""Run the realistic Phase 6 verification evaluation suite."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.schemas.verification import Phase3VerificationInput, VerificationIssue
from backend.app.services.verification.audit_artifact import build_verification_audit_artifact
from backend.app.services.verification.orchestrator import (
    SemanticVerificationPolicy,
    VerificationOrchestrator,
)
from backend.app.services.verification.semantic_validator import (
    OverclaimDimension,
    SemanticCheckResponse,
    SemanticValidationError,
    SemanticValidationInput,
    SemanticValidationResult,
    SemanticVerdict,
)
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
    SemanticVerifierUnavailableBehavior,
)
from resume_optimizer.job_models import NormalizedJobAnalysis
from resume_optimizer.models import (
    AwardEntry,
    BulletEntry,
    CertificationEntry,
    EducationEntry,
    ExperienceEntry,
    ItemType,
    MasterProfile,
    PersonalProfile,
    ProjectEntry,
    SeniorityLevel,
    SkillEntry,
)
from resume_optimizer.phase3_models import (
    BulletRewriteStrategy,
    GeneratedBullet,
    GeneratedExperience,
    GeneratedProject,
    GeneratedSkillHighlight,
    GeneratedSummary,
    GenerationMetadata,
    Phase3GenerationPayload,
    Phase3GenerationResult,
    Phase3RoleContext,
    Phase3SelectedCertificationPayload,
    Phase3SelectedProjectPayload,
    Phase3SelectedSkillPayload,
    Phase3ValidationMetadata,
    SourceReference,
    SupportLevel,
)

DEFAULT_FIXTURE_DIR = (
    REPO_ROOT / "backend" / "app" / "tests" / "fixtures" / "phase6_verification_eval"
)


@dataclass(frozen=True, slots=True)
class EvalCase:
    """One realistic Phase 6 verification fixture case."""

    id: str
    category: str
    item_type: str
    source_item_id: str
    source_bullet_ids: list[str]
    generated_text: str
    semantic_mode: str = "pass"
    semantic_issue_category: str | None = None
    semantic_dimensions: list[str] | None = None
    semantic_fallback_behavior: str = SemanticVerifierUnavailableBehavior.BLOCK.value
    semantic_strict_mode: bool = True
    expected_item_status: str = "passed"
    expected_report_status: str = "passed"
    expected_decision_outcome: str = "pass"
    expected_renderable: bool = True
    expected_fallback_action: str = FallbackAction.PASS_AS_IS.value
    expected_issue_categories: list[str] = None  # type: ignore[assignment]
    expected_repair_status: str = "not_needed"
    expected_degraded_mode: bool = False
    expected_requires_regeneration: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "expected_issue_categories",
            list(self.expected_issue_categories or []),
        )


@dataclass(frozen=True, slots=True)
class EvalCaseResult:
    """Observed end-to-end Phase 6 result for one fixture case."""

    case: EvalCase
    passed_expectations: bool
    item_status: str
    report_status: str
    decision_outcome: str
    renderable: bool
    fallback_action: str
    issue_categories: list[str]
    issue_count: int
    repair_status: str
    degraded_mode: bool
    requires_regeneration: bool
    artifact_issue_count: int
    artifact_internal_summary: str
    artifact_final_decision: str


class FixtureSemanticValidator:
    """Deterministic semantic validator used by the fixture harness."""

    def __init__(self, case: EvalCase) -> None:
        self.case = case
        self.calls = 0

    def validate_item(self, validation_input: SemanticValidationInput) -> SemanticValidationResult:
        self.calls += 1
        if self.case.semantic_mode == "degraded":
            raise SemanticValidationError(f"fixture semantic outage for {self.case.id}")

        verdict = SemanticVerdict(self.case.semantic_mode)
        dimensions = [
            OverclaimDimension(value)
            for value in (self.case.semantic_dimensions or [])
        ]
        issue_category = (
            IssueCategory(self.case.semantic_issue_category)
            if self.case.semantic_issue_category
            else None
        )
        response = SemanticCheckResponse(
            verdict=verdict,
            confidence=0.92 if verdict == SemanticVerdict.PASS else 0.66,
            issue_category=issue_category,
            explanation=f"Fixture semantic verdict for {self.case.id}: {verdict.value}.",
            overclaim_dimensions=dimensions,
        )
        issues: list[VerificationIssue] = []
        if verdict != SemanticVerdict.PASS:
            issues.append(
                VerificationIssue(
                    id=f"issue.semantic_faithfulness.{validation_input.item_id}",
                    category=issue_category
                    or (
                        IssueCategory.PROVENANCE_WEAK
                        if verdict == SemanticVerdict.WEAK_SUPPORT
                        else IssueCategory.UNSUPPORTED_CLAIM
                    ),
                    severity=(
                        IssueSeverity.MEDIUM
                        if verdict == SemanticVerdict.WEAK_SUPPORT
                        else IssueSeverity.HIGH
                    ),
                    message=response.explanation,
                    generated_item_id=validation_input.item_id,
                    source_item_ids=sorted(
                        {match.source_entity_id for match in validation_input.provenance_matches}
                    ),
                    source_bullet_ids=sorted(
                        {
                            match.source_bullet_id
                            for match in validation_input.provenance_matches
                            if match.source_bullet_id is not None
                        }
                    ),
                    evidence_strength=(
                        EvidenceStrength.WEAK
                        if verdict == SemanticVerdict.WEAK_SUPPORT
                        else EvidenceStrength.NONE
                    ),
                    suggested_fallback=(
                        FallbackAction.MARK_NEEDS_REVIEW
                        if verdict == SemanticVerdict.WEAK_SUPPORT
                        else FallbackAction.REQUIRE_HUMAN_REVIEW
                    ),
                    validator_name="semantic_faithfulness_validator",
                )
            )
        return SemanticValidationResult(
            item_id=validation_input.item_id,
            response=response,
            issues=issues,
        )


def load_eval_cases(fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> list[EvalCase]:
    """Load all realistic Phase 6 evaluation cases from JSON fixtures."""

    cases: list[EvalCase] = []
    for path in sorted(fixture_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for raw_case in payload["cases"]:
            cases.append(
                EvalCase(
                    id=str(raw_case["id"]),
                    category=str(raw_case["category"]),
                    item_type=str(raw_case["item_type"]),
                    source_item_id=str(raw_case["source_item_id"]),
                    source_bullet_ids=list(raw_case["source_bullet_ids"]),
                    generated_text=str(raw_case["generated_text"]),
                    semantic_mode=str(raw_case.get("semantic_mode", "pass")),
                    semantic_issue_category=raw_case.get("semantic_issue_category"),
                    semantic_dimensions=raw_case.get("semantic_dimensions"),
                    semantic_fallback_behavior=str(
                        raw_case.get(
                            "semantic_fallback_behavior",
                            SemanticVerifierUnavailableBehavior.BLOCK.value,
                        )
                    ),
                    semantic_strict_mode=bool(raw_case.get("semantic_strict_mode", True)),
                    expected_item_status=str(raw_case["expected_item_status"]),
                    expected_report_status=str(raw_case["expected_report_status"]),
                    expected_decision_outcome=str(raw_case["expected_decision_outcome"]),
                    expected_renderable=bool(raw_case["expected_renderable"]),
                    expected_fallback_action=str(raw_case["expected_fallback_action"]),
                    expected_issue_categories=list(raw_case.get("expected_issue_categories", [])),
                    expected_repair_status=str(raw_case.get("expected_repair_status", "not_needed")),
                    expected_degraded_mode=bool(raw_case.get("expected_degraded_mode", False)),
                    expected_requires_regeneration=bool(
                        raw_case.get("expected_requires_regeneration", False)
                    ),
                )
            )
    return cases


def run_eval_cases(cases: list[EvalCase]) -> list[EvalCaseResult]:
    """Run the real Phase 6 orchestrator for every fixture case."""

    results: list[EvalCaseResult] = []
    for case in cases:
        verification_input = build_verification_input(case)
        orchestrator = VerificationOrchestrator(
            semantic_validator=FixtureSemanticValidator(case),
            semantic_policy=SemanticVerificationPolicy(
                enabled=True,
                strict_mode=case.semantic_strict_mode,
                fallback_behavior=SemanticVerifierUnavailableBehavior(
                    case.semantic_fallback_behavior
                ),
            ),
        )
        run_result = orchestrator.run(
            verification_input,
            verification_run_id=f"verify.{case.id}",
        )
        item = run_result.report.item_results[0]
        repair_record = next(
            (record for record in run_result.report.repair_audit.records if record.item_id == item.item_id),
            None,
        )
        artifact = build_verification_audit_artifact(
            run_id=run_result.verification_run_id,
            verification_timestamp=datetime.now(timezone.utc),
            report=run_result.report,
        )
        categories = sorted({issue.category.value for issue in item.issues})
        repair_status = repair_record.status.value if repair_record is not None else "not_needed"
        requires_regeneration = item.item_id in run_result.report.repair_audit.requires_regeneration_item_ids
        degraded_mode = bool(run_result.report.semantic_verification.degraded_item_ids)
        passed = (
            item.status.value == case.expected_item_status
            and run_result.report.status.value == case.expected_report_status
            and run_result.report.decision_outcome.value == case.expected_decision_outcome
            and run_result.report.renderable == case.expected_renderable
            and item.fallback_action.value == case.expected_fallback_action
            and categories == sorted(case.expected_issue_categories)
            and repair_status == case.expected_repair_status
            and degraded_mode == case.expected_degraded_mode
            and requires_regeneration == case.expected_requires_regeneration
            and artifact.final_decision.value == case.expected_decision_outcome
        )
        results.append(
            EvalCaseResult(
                case=case,
                passed_expectations=passed,
                item_status=item.status.value,
                report_status=run_result.report.status.value,
                decision_outcome=run_result.report.decision_outcome.value,
                renderable=run_result.report.renderable,
                fallback_action=item.fallback_action.value,
                issue_categories=categories,
                issue_count=len(item.issues),
                repair_status=repair_status,
                degraded_mode=degraded_mode,
                requires_regeneration=requires_regeneration,
                artifact_issue_count=artifact.issue_count,
                artifact_internal_summary=artifact.internal_summary,
                artifact_final_decision=artifact.final_decision.value,
            )
        )
    return results


def build_verification_input(case: EvalCase) -> Phase3VerificationInput:
    """Build a realistic Phase 3 to Phase 6 handoff for one evaluation case."""

    profile = _fixture_profile()
    payload = _fixture_generation_payload(profile.id)
    job_analysis = NormalizedJobAnalysis(
        role_type="individual_contributor",
        seniority_level="senior",
        technical_skills=["Python", "PostgreSQL", "React"],
        must_have_requirements=["Python APIs", "platform"],
    )
    return Phase3VerificationInput(
        source_profile_id=profile.id,
        job_analysis=job_analysis,
        source_profile=profile,
        generation_payload=payload,
        phase3_result=_phase3_result_for_case(case, profile.id),
    )


def summarize_results(results: list[EvalCaseResult]) -> dict[str, Any]:
    """Compute concise regression metrics from the fixture suite."""

    total = len(results)
    issue_cases = [result for result in results if result.case.expected_issue_categories]
    safe_cases = [result for result in results if not result.case.expected_issue_categories]
    repaired_cases = [result for result in results if result.repair_status == "applied"]
    degraded_cases = [result for result in results if result.degraded_mode]
    blocked_cases = [result for result in results if not result.renderable]
    return {
        "total_cases": total,
        "passed_expectations": sum(1 for result in results if result.passed_expectations),
        "failed_expectations": sum(1 for result in results if not result.passed_expectations),
        "issue_detection_rate": _rate(sum(1 for result in issue_cases if result.issue_count > 0), len(issue_cases)),
        "false_positive_count": sum(1 for result in safe_cases if result.issue_count > 0),
        "repair_success_rate": _rate(len(repaired_cases), sum(1 for result in results if result.case.expected_repair_status == "applied")),
        "degraded_case_count": len(degraded_cases),
        "blocked_case_count": len(blocked_cases),
    }


def render_summary(results: list[EvalCaseResult]) -> str:
    """Render local CLI output for the Phase 6 regression suite."""

    summary = summarize_results(results)
    lines = [
        "Phase 6 Verification Eval Summary",
        f"cases: {summary['total_cases']}",
        f"passed expectations: {summary['passed_expectations']}",
        f"failed expectations: {summary['failed_expectations']}",
        f"issue detection rate: {summary['issue_detection_rate']:.2%}",
        f"false positive count: {summary['false_positive_count']}",
        f"repair success rate: {summary['repair_success_rate']:.2%}",
        f"degraded case count: {summary['degraded_case_count']}",
        f"blocked case count: {summary['blocked_case_count']}",
    ]
    for result in results:
        status = "PASS" if result.passed_expectations else "FAIL"
        lines.append(
            f"{status} {result.case.id}: item_status={result.item_status}; "
            f"report_status={result.report_status}; decision={result.decision_outcome}; "
            f"issues={result.issue_categories}; repair={result.repair_status}; "
            f"renderable={str(result.renderable).lower()}"
        )
    return "\n".join(lines)


def main() -> int:
    results = run_eval_cases(load_eval_cases())
    print(render_summary(results))
    return 0 if all(result.passed_expectations for result in results) else 1


def _fixture_profile() -> MasterProfile:
    return MasterProfile(
        id="profile.phase6.eval",
        personal_profile=PersonalProfile(
            id="personal.phase6.eval",
            full_name="Alex Verification",
            summary="Senior backend engineer focused on Python APIs and platform workflows.",
            seniority_level=SeniorityLevel.SENIOR,
        ),
        experience=[
            ExperienceEntry(
                id="exp.platform",
                organization="Acme",
                title="Senior Backend Engineer",
                seniority_level=SeniorityLevel.SENIOR,
                start_date={"raw_value": "2019-01"},
                tools=["Python", "PostgreSQL"],
                bullets=[
                    BulletEntry(
                        id="bullet.platform.api",
                        text="Implemented Python APIs that reduced latency by 25% for internal workflows.",
                        tools=["Python"],
                    ),
                    BulletEntry(
                        id="bullet.platform.reliability",
                        text="Contributed to PostgreSQL reliability improvements for data services.",
                        tools=["PostgreSQL"],
                    ),
                    BulletEntry(
                        id="bullet.platform.collab",
                        text="Partnered with product and design stakeholders to ship internal developer tooling for platform workflows.",
                        tools=["Python"],
                    ),
                    BulletEntry(
                        id="bullet.platform.teams",
                        text="Supported rollout of backend services used by 3 internal teams.",
                        tools=["Python"],
                    ),
                ],
                canonical_tags=["backend"],
                domain_tags=["platform"],
            )
        ],
        projects=[
            ProjectEntry(
                id="project.portal",
                name="Developer Portal",
                role="Frontend Lead",
                start_date={"raw_value": "2023-01"},
                end_date={"raw_value": "2023-09"},
                summary="Internal developer tooling for service onboarding.",
                tools=["React", "TypeScript", "Storybook"],
                bullets=[
                    BulletEntry(
                        id="bullet.project.portal.1",
                        text="Led adoption of a shared component library across three product surfaces.",
                        tools=["React", "TypeScript", "Storybook"],
                    )
                ],
                canonical_tags=["platform"],
                domain_tags=["developer tooling"],
            )
        ],
        education=[
            EducationEntry(
                id="edu.uw",
                institution="University of Washington",
                degree="B.S.",
                field_of_study="Informatics",
                start_date={"raw_value": "2015-09"},
                end_date={"raw_value": "2019-06"},
                honors=["Dean's List"],
            )
        ],
        certifications=[
            CertificationEntry(
                id="cert.aws",
                name="AWS Certified Solutions Architect - Associate",
                issuer="Amazon Web Services",
                issue_date={"raw_value": "2023-11"},
            )
        ],
        awards=[
            AwardEntry(
                id="award.customer-impact",
                title="Customer Impact Award",
                awarder="Acme",
                summary="Recognized for improving internal platform delivery quality.",
            )
        ],
        skills=[
            SkillEntry(id="skill.python", name="Python", category="language"),
            SkillEntry(id="skill.postgresql", name="PostgreSQL", category="database"),
            SkillEntry(id="skill.aws", name="AWS", category="platform"),
            SkillEntry(id="skill.platform", name="Platform Engineering", category="domain"),
        ],
    )


def _fixture_generation_payload(profile_id: str) -> Phase3GenerationPayload:
    return Phase3GenerationPayload(
        role_context=Phase3RoleContext(
            target_role_title="Backend Engineer",
            must_have_skills=["Python"],
        ),
        matched_skills=[
            Phase3SelectedSkillPayload(
                id="skill.python",
                skill_name="Python",
                relevance_score=0.95,
                evidence_strength="strong",
                verified_status="corroborated",
            ),
            Phase3SelectedSkillPayload(
                id="skill.aws",
                skill_name="AWS",
                relevance_score=0.71,
                evidence_strength="strong",
                verified_status="corroborated",
            ),
        ],
        selected_projects=[
            Phase3SelectedProjectPayload(
                id="project.portal",
                evidence_unit_ids=["evidence.project.portal"],
                name="Developer Portal",
                role="Frontend Lead",
                summary="Internal developer tooling for service onboarding.",
                relevance_score=0.84,
            )
        ],
        selected_certifications=[
            Phase3SelectedCertificationPayload(
                id="cert.aws",
                evidence_unit_ids=["evidence.cert.aws"],
                name="AWS Certified Solutions Architect - Associate",
                issuer="Amazon Web Services",
                relevance_score=0.72,
            )
        ],
        validation_metadata=Phase3ValidationMetadata(profile_id=profile_id),
    )


def _phase3_result_for_case(case: EvalCase, profile_id: str) -> Phase3GenerationResult:
    references = [
        SourceReference(
            source_item_id=_bullet_source_item_id(bullet_id),
            source_item_type=_bullet_source_item_type(bullet_id),
            source_bullet_id=bullet_id,
            support_level=(
                SupportLevel.SYNTHESIZED if case.item_type == "summary" or len(case.source_bullet_ids) > 1 else SupportLevel.DIRECT
            ),
        )
        for bullet_id in case.source_bullet_ids
    ]
    metadata = GenerationMetadata(source_profile_id=profile_id)
    if case.item_type == "summary":
        return Phase3GenerationResult(
            summary=GeneratedSummary(
                text=case.generated_text,
                source_item_ids=sorted({_bullet_source_item_id(bullet_id) for bullet_id in case.source_bullet_ids}),
                source_bullet_ids=list(case.source_bullet_ids),
                provenance=references,
                support_level=SupportLevel.SYNTHESIZED,
            ),
            metadata=metadata,
        )
    if case.item_type == "experience_bullet":
        return Phase3GenerationResult(
            selected_experiences=[
                GeneratedExperience(
                    source_item_id=case.source_item_id,
                    organization="Acme",
                    title="Senior Backend Engineer",
                    start_date={"raw_value": "2019-01"},
                    generated_bullets=[
                        GeneratedBullet(
                            id=f"gen.{case.id}",
                            source_item_id=case.source_item_id,
                            source_item_type=ItemType.EXPERIENCE,
                            source_bullet_ids=list(case.source_bullet_ids),
                            rewritten_text=case.generated_text,
                            rewrite_strategy=(
                                BulletRewriteStrategy.CONDENSED
                                if len(case.source_bullet_ids) == 1
                                else BulletRewriteStrategy.MERGED
                            ),
                            provenance=references,
                            support_level=(
                                SupportLevel.DIRECT
                                if len(case.source_bullet_ids) == 1
                                else SupportLevel.SYNTHESIZED
                            ),
                        )
                    ],
                    support_level=SupportLevel.DIRECT,
                )
            ],
            metadata=metadata,
        )
    if case.item_type == "project_bullet":
        return Phase3GenerationResult(
            selected_projects=[
                GeneratedProject(
                    source_item_id=case.source_item_id,
                    name="Developer Portal",
                    role="Frontend Lead",
                    start_date={"raw_value": "2023-01"},
                    generated_bullets=[
                        GeneratedBullet(
                            id=f"gen.{case.id}",
                            source_item_id=case.source_item_id,
                            source_item_type=ItemType.PROJECT,
                            source_bullet_ids=list(case.source_bullet_ids),
                            rewritten_text=case.generated_text,
                            rewrite_strategy=BulletRewriteStrategy.LIGHT_REWRITE,
                            provenance=references,
                            support_level=SupportLevel.DIRECT,
                        )
                    ],
                    support_level=SupportLevel.DIRECT,
                )
            ],
            metadata=metadata,
        )
    if case.item_type == "skill_statement":
        return Phase3GenerationResult(
            skills_to_highlight=[
                GeneratedSkillHighlight(
                    skill_name=case.generated_text,
                    source_item_ids=[case.source_item_id],
                    provenance=references,
                    support_level=SupportLevel.SYNTHESIZED,
                )
            ],
            metadata=metadata,
        )
    raise ValueError(f"Unsupported eval item_type: {case.item_type}")


def _bullet_source_item_id(bullet_id: str) -> str:
    if bullet_id.startswith("bullet.project.portal"):
        return "project.portal"
    return "exp.platform"


def _bullet_source_item_type(bullet_id: str) -> ItemType:
    if bullet_id.startswith("bullet.project.portal"):
        return ItemType.PROJECT
    return ItemType.EXPERIENCE


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


if __name__ == "__main__":
    raise SystemExit(main())
