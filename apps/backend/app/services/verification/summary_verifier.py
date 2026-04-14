"""Dedicated claim-level verifier for generated summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import re

from pydantic import Field

from backend.app.schemas.verification import VerificationIssue
from backend.app.services.verification.deterministic_validators import (
    DeterministicValidationInput,
    SelectedContentContext,
    SourceContext,
)
from backend.app.services.verification.normalization import normalize_phrase, phrase_in_text
from backend.app.services.verification.provenance_service import ProvenanceMatch
from backend.app.services.verification.semantic_validator import (
    SemanticValidationError,
    SemanticValidationInput,
    SemanticValidatorService,
)
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
)
from resume_optimizer.models import (
    MasterProfile,
    NonEmptyStr,
    SeniorityLevel,
    StableId,
    StrictModel,
)
from resume_optimizer.phase3_models import Phase3GenerationPayload

_YEARS_PATTERN = re.compile(r"\b(\d{1,2})\+?\s+years?\b", re.IGNORECASE)
_EXPERTISE_PATTERN = re.compile(
    r"\b(?:expert|expertise|experienced|specialized)\s+in\s+([^.]+)",
    re.IGNORECASE,
)

_SENIORITY_PHRASES = {
    "senior": SeniorityLevel.SENIOR,
    "staff": SeniorityLevel.STAFF,
    "principal": SeniorityLevel.PRINCIPAL,
    "director": SeniorityLevel.DIRECTOR,
    "head": SeniorityLevel.DIRECTOR,
}
_ROLE_FAMILY_PHRASES = (
    "backend",
    "frontend",
    "full-stack",
    "platform",
    "data",
    "machine learning",
    "ai/ml",
    "devops",
    "security",
    "mobile",
)
_LEADERSHIP_LEVEL_PHRASES = (
    "engineering leader",
    "leader",
    "leadership",
    "people manager",
    "manager",
    "mentored",
    "mentoring",
    "technical lead",
)
_FUNCTIONAL_SPECIALIZATION_PHRASES = (
    "backend",
    "frontend",
    "full-stack",
    "platform",
    "api",
    "developer tooling",
)
_ARCHITECTURE_PHRASES = (
    "architecture",
    "architected",
    "distributed systems",
    "platform",
    "system design",
)
_PRODUCT_OWNERSHIP_PHRASES = (
    "end-to-end ownership",
    "product ownership",
    "owned product",
    "owned the roadmap",
)
_STAKEHOLDER_PHRASES = (
    "cross-functional",
    "stakeholder management",
    "managed stakeholders",
    "partnered with stakeholders",
)


class SummaryClaimType(StrEnum):
    YEARS_EXPERIENCE = "years_experience"
    LEADERSHIP_LEVEL = "leadership_level"
    FUNCTIONAL_SPECIALIZATION = "functional_specialization"
    DOMAIN_EXPERTISE = "domain_expertise"
    ARCHITECTURE_SCOPE = "architecture_scope"
    PRODUCT_OWNERSHIP = "product_ownership"
    STAKEHOLDER_MANAGEMENT = "stakeholder_management"
    BREADTH = "breadth"
    SENIORITY = "seniority"
    ROLE_FAMILY = "role_family"


class SummaryClaim(StrictModel):
    """One extracted summary claim for claim-level verification."""

    claim_type: SummaryClaimType
    text: NonEmptyStr
    normalized_text: NonEmptyStr


class SummaryFallbackPlan(StrictModel):
    """Safe summary fallback generated from controlled, supported inputs."""

    strategy: NonEmptyStr
    safe_summary_text: NonEmptyStr
    removed_claims: list[NonEmptyStr] = Field(default_factory=list)
    notes: list[NonEmptyStr] = Field(default_factory=list)


class SummaryVerificationResult(StrictModel):
    """Summary-specific verification output including fallback guidance."""

    claims: list[SummaryClaim] = Field(default_factory=list)
    issues: list[VerificationIssue] = Field(default_factory=list)
    fallback_plan: SummaryFallbackPlan
    semantic_attempted: bool = False
    semantic_completed: bool = False
    semantic_degraded_message: NonEmptyStr | None = None


@dataclass(slots=True)
class SummaryVerifier:
    """Verify summaries at claim level against aggregate evidence."""

    def verify(
        self,
        *,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
        selected_context: SelectedContentContext,
        semantic_validator: SemanticValidatorService | None = None,
    ) -> SummaryVerificationResult:
        claims = extract_summary_claims(validation_input.generated_text)
        issues: list[VerificationIssue] = []
        issues.extend(
            self._validate_years_experience(claims, validation_input.source_profile, source_context)
        )
        issues.extend(self._validate_leadership_claims(claims, source_context))
        issues.extend(self._validate_functional_specialization(claims, source_context))
        issues.extend(self._validate_domain_claims(claims, source_context))
        issues.extend(self._validate_architecture_claims(claims, source_context))
        issues.extend(self._validate_ownership_claims(claims, source_context))
        issues.extend(self._validate_stakeholder_claims(claims, source_context))
        issues.extend(self._validate_breadth_claims(claims, source_context, selected_context))
        issues.extend(self._validate_seniority_claims(claims, validation_input.source_profile, source_context))
        issues.extend(self._validate_role_family_claims(claims, source_context))

        semantic_attempted = False
        semantic_completed = False
        semantic_degraded_message: str | None = None
        if semantic_validator is not None:
            semantic_attempted = True
            try:
                semantic_result = semantic_validator.validate_item(
                    SemanticValidationInput(
                        item_id=validation_input.item_id,
                        item_type=validation_input.item_type,
                        generated_text=validation_input.generated_text,
                        provenance_matches=validation_input.provenance_matches,
                    )
                )
                issues.extend(semantic_result.issues)
                semantic_completed = True
            except SemanticValidationError as exc:
                semantic_degraded_message = str(exc)

        fallback_plan = build_summary_fallback_plan(
            summary_text=validation_input.generated_text,
            claims=claims,
            issues=issues,
            source_context=source_context,
            selected_context=selected_context,
        )
        return SummaryVerificationResult(
            claims=claims,
            issues=issues,
            fallback_plan=fallback_plan,
            semantic_attempted=semantic_attempted,
            semantic_completed=semantic_completed,
            semantic_degraded_message=semantic_degraded_message,
        )

    def _validate_years_experience(
        self,
        claims: list[SummaryClaim],
        source_profile: MasterProfile,
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        max_years = _max_supported_years(source_profile)
        issues: list[VerificationIssue] = []
        for claim in claims:
            if claim.claim_type != SummaryClaimType.YEARS_EXPERIENCE:
                continue
            value = int(_YEARS_PATTERN.search(claim.text).group(1))
            if value <= max_years:
                continue
            issues.append(
                _summary_issue(
                    item_id="summary",
                    category=IssueCategory.UNSUPPORTED_YEARS_EXPERIENCE,
                    severity=IssueSeverity.CRITICAL,
                    message=(
                        f"Summary years-of-experience claim exceeds supported source history: {claim.text}"
                    ),
                    source_context=source_context,
                    validator_name="summary_years_experience_validator",
                )
            )
        return issues

    def _validate_leadership_claims(
        self,
        claims: list[SummaryClaim],
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        return [
            _summary_issue(
                item_id="summary",
                category=IssueCategory.UNSUPPORTED_LEADERSHIP,
                severity=IssueSeverity.HIGH,
                message=f"Summary leadership-level claim is not supported by source evidence: {claim.text}",
                source_context=source_context,
                validator_name="summary_leadership_level_validator",
            )
            for claim in claims
            if claim.claim_type == SummaryClaimType.LEADERSHIP_LEVEL
            and not _context_supports_phrase(source_context, claim.normalized_text)
        ]

    def _validate_functional_specialization(
        self,
        claims: list[SummaryClaim],
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        return [
            _summary_issue(
                item_id="summary",
                category=IssueCategory.ROLE_FAMILY_MISMATCH,
                severity=IssueSeverity.HIGH,
                message=f"Summary functional specialization is not supported by source evidence: {claim.text}",
                source_context=source_context,
                validator_name="summary_functional_specialization_validator",
            )
            for claim in claims
            if claim.claim_type == SummaryClaimType.FUNCTIONAL_SPECIALIZATION
            and not _context_supports_phrase(source_context, claim.normalized_text)
        ]

    def _validate_domain_claims(
        self,
        claims: list[SummaryClaim],
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        return [
            _summary_issue(
                item_id="summary",
                category=IssueCategory.UNSUPPORTED_DOMAIN,
                severity=IssueSeverity.HIGH,
                message=f"Summary domain expertise claim is not supported by source evidence: {claim.text}",
                source_context=source_context,
                validator_name="summary_domain_expertise_validator",
            )
            for claim in claims
            if claim.claim_type == SummaryClaimType.DOMAIN_EXPERTISE
            and not _context_supports_phrase(source_context, claim.normalized_text)
        ]

    def _validate_architecture_claims(
        self,
        claims: list[SummaryClaim],
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        return [
            _summary_issue(
                item_id="summary",
                category=IssueCategory.UNSUPPORTED_SCOPE,
                severity=IssueSeverity.HIGH,
                message=f"Summary architecture or platform claim is not supported by source evidence: {claim.text}",
                source_context=source_context,
                validator_name="summary_architecture_scope_validator",
            )
            for claim in claims
            if claim.claim_type == SummaryClaimType.ARCHITECTURE_SCOPE
            and not _context_supports_phrase(source_context, claim.normalized_text)
        ]

    def _validate_ownership_claims(
        self,
        claims: list[SummaryClaim],
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        return [
            _summary_issue(
                item_id="summary",
                category=IssueCategory.UNSUPPORTED_SCOPE,
                severity=IssueSeverity.HIGH,
                message=f"Summary end-to-end ownership claim is not supported by source evidence: {claim.text}",
                source_context=source_context,
                validator_name="summary_product_ownership_validator",
            )
            for claim in claims
            if claim.claim_type == SummaryClaimType.PRODUCT_OWNERSHIP
            and not _context_supports_phrase(source_context, claim.normalized_text)
        ]

    def _validate_stakeholder_claims(
        self,
        claims: list[SummaryClaim],
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        return [
            _summary_issue(
                item_id="summary",
                category=IssueCategory.UNSUPPORTED_LEADERSHIP,
                severity=IssueSeverity.HIGH,
                message=f"Summary stakeholder or cross-functional management claim is not supported by source evidence: {claim.text}",
                source_context=source_context,
                validator_name="summary_stakeholder_management_validator",
            )
            for claim in claims
            if claim.claim_type == SummaryClaimType.STAKEHOLDER_MANAGEMENT
            and not _context_supports_phrase(source_context, claim.normalized_text)
        ]

    def _validate_breadth_claims(
        self,
        claims: list[SummaryClaim],
        source_context: SourceContext,
        selected_context: SelectedContentContext,
    ) -> list[VerificationIssue]:
        supported_terms = {
            *source_context.tools,
            *source_context.all_skill_names,
            *source_context.domain_tags,
            *selected_context.selected_skill_names,
            *selected_context.selected_project_names,
            *selected_context.selected_certification_names,
        }
        supported_normalized = {normalize_phrase(term) for term in supported_terms}
        issues: list[VerificationIssue] = []
        for claim in claims:
            if claim.claim_type != SummaryClaimType.BREADTH:
                continue
            listed_terms = [
                normalize_phrase(part)
                for part in re.split(r",| and ", claim.text)
                if normalize_phrase(part)
            ]
            unsupported = [term for term in listed_terms if term not in supported_normalized]
            if len(unsupported) < 2:
                continue
            issues.append(
                _summary_issue(
                    item_id="summary",
                    category=IssueCategory.BREADTH_INFLATION,
                    severity=IssueSeverity.HIGH,
                    message=f"Summary breadth claim includes unsupported expertise areas: {claim.text}",
                    source_context=source_context,
                    validator_name="summary_breadth_inflation_validator",
                )
            )
        return issues

    def _validate_seniority_claims(
        self,
        claims: list[SummaryClaim],
        source_profile: MasterProfile,
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        supported_rank = _max_supported_seniority_rank(source_profile)
        issues: list[VerificationIssue] = []
        for claim in claims:
            if claim.claim_type != SummaryClaimType.SENIORITY:
                continue
            claim_rank = _seniority_rank_from_phrase(claim.normalized_text)
            if claim_rank <= supported_rank:
                continue
            issues.append(
                _summary_issue(
                    item_id="summary",
                    category=IssueCategory.SENIORITY_MISMATCH,
                    severity=IssueSeverity.CRITICAL,
                    message=f"Summary seniority claim exceeds supported source evidence: {claim.text}",
                    source_context=source_context,
                    validator_name="summary_seniority_mismatch_validator",
                )
            )
        return issues

    def _validate_role_family_claims(
        self,
        claims: list[SummaryClaim],
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        return [
            _summary_issue(
                item_id="summary",
                category=IssueCategory.ROLE_FAMILY_MISMATCH,
                severity=IssueSeverity.CRITICAL,
                message=f"Summary role-family repositioning is not supported by source evidence: {claim.text}",
                source_context=source_context,
                validator_name="summary_role_family_validator",
            )
            for claim in claims
            if claim.claim_type == SummaryClaimType.ROLE_FAMILY
            and not _context_supports_phrase(source_context, claim.normalized_text)
        ]


def extract_summary_claims(summary_text: str) -> list[SummaryClaim]:
    """Extract claim-level summary statements from one summary string."""

    claims: list[SummaryClaim] = []
    normalized_summary = normalize_phrase(summary_text)
    for match in _YEARS_PATTERN.finditer(summary_text):
        claims.append(
            SummaryClaim(
                claim_type=SummaryClaimType.YEARS_EXPERIENCE,
                text=match.group(0),
                normalized_text=normalize_phrase(match.group(0)),
            )
        )
    for phrase in _LEADERSHIP_LEVEL_PHRASES:
        if phrase_in_text(normalized_summary, phrase):
            claims.append(
                SummaryClaim(
                    claim_type=SummaryClaimType.LEADERSHIP_LEVEL,
                    text=phrase,
                    normalized_text=normalize_phrase(phrase),
                )
            )
    for phrase in _FUNCTIONAL_SPECIALIZATION_PHRASES:
        if phrase_in_text(normalized_summary, phrase):
            claims.append(
                SummaryClaim(
                    claim_type=SummaryClaimType.FUNCTIONAL_SPECIALIZATION,
                    text=phrase,
                    normalized_text=normalize_phrase(phrase),
                )
            )
    for phrase in _ARCHITECTURE_PHRASES:
        if phrase_in_text(normalized_summary, phrase):
            claims.append(
                SummaryClaim(
                    claim_type=SummaryClaimType.ARCHITECTURE_SCOPE,
                    text=phrase,
                    normalized_text=normalize_phrase(phrase),
                )
            )
    for phrase in _PRODUCT_OWNERSHIP_PHRASES:
        if phrase_in_text(normalized_summary, phrase):
            claims.append(
                SummaryClaim(
                    claim_type=SummaryClaimType.PRODUCT_OWNERSHIP,
                    text=phrase,
                    normalized_text=normalize_phrase(phrase),
                )
            )
    for phrase in _STAKEHOLDER_PHRASES:
        if phrase_in_text(normalized_summary, phrase):
            claims.append(
                SummaryClaim(
                    claim_type=SummaryClaimType.STAKEHOLDER_MANAGEMENT,
                    text=phrase,
                    normalized_text=normalize_phrase(phrase),
                )
            )
    for phrase in _ROLE_FAMILY_PHRASES:
        if phrase_in_text(normalized_summary, phrase):
            claims.append(
                SummaryClaim(
                    claim_type=SummaryClaimType.ROLE_FAMILY,
                    text=phrase,
                    normalized_text=normalize_phrase(phrase),
                )
            )
    for phrase in _SENIORITY_PHRASES:
        if phrase_in_text(normalized_summary, phrase):
            claims.append(
                SummaryClaim(
                    claim_type=SummaryClaimType.SENIORITY,
                    text=phrase,
                    normalized_text=normalize_phrase(phrase),
                )
            )
    for phrase in (
        "fintech",
        "healthcare",
        "payments",
        "security",
        "ai/ml",
        "machine learning",
        "distributed systems",
    ):
        if phrase_in_text(normalized_summary, phrase):
            claims.append(
                SummaryClaim(
                    claim_type=SummaryClaimType.DOMAIN_EXPERTISE,
                    text=phrase,
                    normalized_text=normalize_phrase(phrase),
                )
            )
    for match in _EXPERTISE_PATTERN.finditer(summary_text):
        claims.append(
            SummaryClaim(
                claim_type=SummaryClaimType.BREADTH,
                text=match.group(1).strip(),
                normalized_text=normalize_phrase(match.group(1)),
            )
        )
    return _dedupe_claims(claims)


def build_summary_fallback_plan(
    *,
    summary_text: str,
    claims: list[SummaryClaim],
    issues: list[VerificationIssue],
    source_context: SourceContext,
    selected_context: SelectedContentContext,
) -> SummaryFallbackPlan:
    """Build a conservative summary fallback from controlled supported inputs."""

    removed_claims = sorted(
        {claim.text for claim in claims if any(claim.text.casefold() in issue.message.casefold() for issue in issues)}
    )
    role_label = _safe_role_label(source_context)
    supported_signals: list[str] = []
    preferred_tools = sorted(source_context.tools)[:2]
    if preferred_tools:
        supported_signals.append("/".join(preferred_tools))
    if source_context.project_names:
        supported_signals.append("delivery-focused project work")
    if source_context.certification_names:
        supported_signals.append("one relevant certification")
    if not supported_signals and selected_context.selected_skill_names:
        supported_signals.append(", ".join(sorted(selected_context.selected_skill_names)[:2]))
    if not supported_signals:
        supported_signals.append("relevant software delivery experience")
    safe_summary_text = f"{role_label} with {supported_signals[0]}."
    if len(supported_signals) > 1:
        safe_summary_text = f"{role_label} with {supported_signals[0]} and {supported_signals[1]}."
    return SummaryFallbackPlan(
        strategy="rebuild_from_controlled_summary_inputs",
        safe_summary_text=safe_summary_text,
        removed_claims=removed_claims,
        notes=[
            "Drop unsupported summary claims.",
            "Shorten to source-backed wording only.",
        ],
    )


def _summary_issue(
    *,
    item_id: str,
    category: IssueCategory,
    severity: IssueSeverity,
    message: str,
    source_context: SourceContext,
    validator_name: str,
) -> VerificationIssue:
    return VerificationIssue(
        id=f"issue.{validator_name}.{item_id}",
        category=category,
        severity=severity,
        message=message,
        generated_item_id=item_id,
        source_item_ids=sorted(source_context.source_item_ids),
        source_bullet_ids=sorted(source_context.source_bullet_ids),
        evidence_strength=EvidenceStrength.NONE,
        suggested_fallback=FallbackAction.USE_SAFE_SUMMARY_FALLBACK,
        validator_name=validator_name,
    )


def _context_supports_phrase(source_context: SourceContext, phrase: str) -> bool:
    supported = {
        source_context.text,
        *source_context.tools,
        *source_context.all_skill_names,
        *source_context.domain_tags,
        *source_context.canonical_tags,
        *source_context.certification_names,
        *source_context.award_titles,
        *source_context.education_honors,
        *source_context.project_names,
        *source_context.education_fields,
        *source_context.education_degrees,
    }
    variants = _phrase_variants(phrase)
    return any(phrase_in_text(value, variant) for value in supported for variant in variants)


def _max_supported_years(source_profile: MasterProfile) -> int:
    starts = [entry.start_date.year for entry in [*source_profile.experience, *source_profile.projects] if entry.start_date is not None and entry.start_date.year is not None]
    if not starts:
        return 0
    earliest = min(starts)
    current_year = datetime.now(timezone.utc).year
    return max(0, current_year - earliest)


def _max_supported_seniority_rank(source_profile: MasterProfile) -> int:
    ranks = [
        _seniority_rank(level)
        for level in [
            source_profile.personal_profile.seniority_level,
            *[entry.seniority_level for entry in source_profile.experience],
            *[entry.seniority_level for entry in source_profile.projects],
        ]
        if level is not None
    ]
    title_ranks = [
        _seniority_rank_from_phrase(title)
        for title in [
            source_profile.personal_profile.headline or "",
            *[entry.title for entry in source_profile.experience],
            *[entry.role or "" for entry in source_profile.projects],
        ]
    ]
    return max([0, *ranks, *title_ranks])


def _seniority_rank(level: SeniorityLevel) -> int:
    order = {
        SeniorityLevel.INTERN: 0,
        SeniorityLevel.JUNIOR: 1,
        SeniorityLevel.MID: 2,
        SeniorityLevel.SENIOR: 3,
        SeniorityLevel.STAFF: 4,
        SeniorityLevel.PRINCIPAL: 5,
        SeniorityLevel.DIRECTOR: 6,
        SeniorityLevel.EXECUTIVE: 7,
    }
    return order[level]


def _seniority_rank_from_phrase(value: str) -> int:
    normalized = normalize_phrase(value)
    for phrase, level in _SENIORITY_PHRASES.items():
        if phrase_in_text(normalized, phrase):
            return _seniority_rank(level)
    return 0


def _safe_role_label(source_context: SourceContext) -> str:
    for phrase, label in (
        ("platform", "Platform engineer"),
        ("backend", "Backend engineer"),
        ("frontend", "Frontend engineer"),
        ("full stack", "Software engineer"),
    ):
        if _context_supports_phrase(source_context, phrase):
            return label
    return "Software engineer"


def _dedupe_claims(claims: list[SummaryClaim]) -> list[SummaryClaim]:
    seen: set[tuple[SummaryClaimType, str]] = set()
    deduped: list[SummaryClaim] = []
    for claim in claims:
        key = (claim.claim_type, claim.normalized_text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(claim)
    return deduped


def _phrase_variants(phrase: str) -> set[str]:
    normalized = normalize_phrase(phrase)
    variants = {normalized}
    if normalized and not normalized.endswith("s"):
        variants.add(f"{normalized}s")
    if normalized.endswith("s"):
        variants.add(normalized[:-1])
    return {variant for variant in variants if variant}
