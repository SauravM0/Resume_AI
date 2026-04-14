"""Typed candidate evidence schema for Phase 2 extraction and downstream reuse."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .models import (
    EvidenceStrength,
    ItemType,
    NonEmptyStr,
    ScoreValue,
    SourceLink,
    StableId,
    StrictModel,
    VerifiedStatus,
)

EVIDENCE_GRAPH_SCHEMA_VERSION = "phase2.candidate-evidence.v1"


class EvidenceSourceType(StrEnum):
    """Supported evidence-unit source categories extracted from the candidate profile."""

    PERSONAL_SUMMARY = "personal_summary"
    EXPERIENCE_BULLET = "experience_bullet"
    EXPERIENCE_SUMMARY = "experience_summary"
    PROJECT_BULLET = "project_bullet"
    PROJECT_SUMMARY = "project_summary"
    EDUCATION_ACHIEVEMENT = "education_achievement"
    CERTIFICATION = "certification"
    SKILL_DECLARATION = "skill_declaration"
    VERIFIED_SKILL = "verified_skill"
    AWARD = "award"


class EvidenceSection(StrEnum):
    PERSONAL_PROFILE = "personal_profile"
    EXPERIENCE = "experience"
    PROJECTS = "projects"
    EDUCATION = "education"
    CERTIFICATIONS = "certifications"
    AWARDS = "awards"
    SKILLS = "skills"


class EvidenceChildType(StrEnum):
    """Typed child-link targets under a source parent item."""

    BULLET = "bullet"
    HONOR = "honor"
    SUMMARY = "summary"


class WeakEvidenceTag(StrEnum):
    """Weakness tags that downstream ranking or review can use for diagnostics."""

    VAGUE = "vague"
    LOW_INFORMATION = "low_information"
    UNSUPPORTED_SKILL_MENTION = "unsupported_skill_mention"
    DUPLICATE = "duplicate"
    NEAR_DUPLICATE = "near_duplicate"


class EvidenceRelationshipType(StrEnum):
    """Typed overlap relationships between two evidence units."""

    EXACT_DUPLICATE = "exact_duplicate"
    NEAR_DUPLICATE = "near_duplicate"
    PARENT_CHILD_RESTATEMENT = "parent_child_restatement"
    SUPPORTING_EVIDENCE = "supporting_evidence"


class EvidenceQualityBand(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    POOR = "poor"


class CoverageBand(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    EMERGING = "emerging"
    SPARSE = "sparse"


class OwnershipLevel(StrEnum):
    UNKNOWN = "unknown"
    CONTRIBUTOR = "contributor"
    DRIVER = "driver"
    OWNER = "owner"
    FOUNDER = "founder"


class LeadershipSignal(StrEnum):
    NONE = "none"
    MENTORSHIP = "mentorship"
    TECHNICAL_LEADERSHIP = "technical_leadership"
    PEOPLE_MANAGEMENT = "people_management"
    CROSS_FUNCTIONAL_LEADERSHIP = "cross_functional_leadership"
    EXECUTIVE_LEADERSHIP = "executive_leadership"


class DeliveryScope(StrEnum):
    UNKNOWN = "unknown"
    TASK = "task"
    FEATURE = "feature"
    SYSTEM = "system"
    PLATFORM = "platform"
    PRODUCT = "product"
    ORGANIZATION = "organization"
    COMPANY = "company"
    EXTERNAL = "external"


class ImpactType(StrEnum):
    NONE = "none"
    DELIVERY = "delivery"
    EFFICIENCY = "efficiency"
    COST = "cost"
    REVENUE = "revenue"
    GROWTH = "growth"
    RELIABILITY = "reliability"
    PERFORMANCE = "performance"
    QUALITY = "quality"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    CUSTOMER_EXPERIENCE = "customer_experience"


class RewriteSafetyLevel(StrEnum):
    SAFE = "safe"
    CAUTION = "caution"
    RESTRICTED = "restricted"


class EvidenceTagCategory(StrEnum):
    SKILL = "skill"
    TOOL = "tool"
    DOMAIN = "domain"
    ROLE_FAMILY = "role_family"
    BUSINESS_OUTCOME = "business_outcome"
    SIGNAL = "signal"
    WARNING = "warning"


class RoleSpecialty(StrEnum):
    ARCHITECTURE = "architecture"
    BACKEND = "backend"
    FRONTEND = "frontend"
    FULLSTACK = "fullstack"
    DATA = "data"
    DEVOPS = "devops"
    ML = "ml"
    MOBILE = "mobile"
    PRODUCT = "product"
    DESIGN = "design"


class EvidenceEnrichment(StrictModel):
    """Deterministic strategist-facing signals derived from explicit evidence patterns."""

    role_specialties: list[RoleSpecialty] = Field(default_factory=list)
    architecture_system_design_score: ScoreValue | None = None
    ownership_score: ScoreValue | None = None
    leadership_score: ScoreValue | None = None
    mentoring_score: ScoreValue | None = None
    stakeholder_management_score: ScoreValue | None = None
    delivery_execution_score: ScoreValue | None = None
    scaling_performance_score: ScoreValue | None = None
    optimization_score: ScoreValue | None = None
    experimentation_score: ScoreValue | None = None
    reliability_score: ScoreValue | None = None
    automation_score: ScoreValue | None = None
    domain_specificity_score: ScoreValue | None = None
    compliance_security_score: ScoreValue | None = None
    business_outcome_score: ScoreValue | None = None
    quantified_impact_score: ScoreValue | None = None
    customer_facing_score: ScoreValue | None = None
    internal_platform_score: ScoreValue | None = None
    triggered_rules: list[NonEmptyStr] = Field(default_factory=list)


class RecencyMetadata(StrictModel):
    """Structured recency metadata preserved on each evidence unit."""

    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    is_current: bool = False
    source_recency_score: ScoreValue | None = None


class EvidenceParentLink(StrictModel):
    """Typed link back to the source parent item and optional child record."""

    source_section: EvidenceSection
    source_parent_id: StableId
    source_parent_type: ItemType
    source_child_id: StableId | None = None
    source_child_type: EvidenceChildType | None = None
    source_child_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_child_shape(self) -> "EvidenceParentLink":
        has_child_ref = self.source_child_id is not None or self.source_child_type is not None
        if (self.source_child_id is None) != (self.source_child_type is None):
            raise ValueError("source_child_id and source_child_type must be provided together")
        if self.source_child_index is not None and not has_child_ref:
            raise ValueError("source_child_index requires a child reference")
        return self


class EvidenceTag(StrictModel):
    """Structured signal tag attached to one evidence unit."""

    category: EvidenceTagCategory
    value: NonEmptyStr
    confidence_score: ScoreValue | None = None


class EvidenceSignals(StrictModel):
    """Typed signal bundle reserved for future ranking and composition."""

    ownership_level: OwnershipLevel = OwnershipLevel.UNKNOWN
    leadership_signals: list[LeadershipSignal] = Field(default_factory=list)
    delivery_scope: DeliveryScope = DeliveryScope.UNKNOWN
    impact_types: list[ImpactType] = Field(default_factory=list)
    impact_metrics_present: bool = False
    role_family_hints: list[NonEmptyStr] = Field(default_factory=list)
    business_outcome_hints: list[NonEmptyStr] = Field(default_factory=list)
    seniority_signals: list[NonEmptyStr] = Field(default_factory=list)
    signal_tokens: list[NonEmptyStr] = Field(default_factory=list)
    tags: list[EvidenceTag] = Field(default_factory=list)


class EvidenceQuality(StrictModel):
    """Evidence quality attributes kept separate from ranking logic."""

    clarity_score: ScoreValue | None = None
    specificity_score: ScoreValue | None = None
    metric_presence_score: ScoreValue | None = None
    outcome_clarity_score: ScoreValue | None = None
    ownership_clarity_score: ScoreValue | None = None
    tool_specificity_score: ScoreValue | None = None
    scope_clarity_score: ScoreValue | None = None
    recency_score: ScoreValue | None = None
    readability_score: ScoreValue | None = None
    rewrite_safety_score: ScoreValue | None = None
    strategic_usefulness_score: ScoreValue | None = None
    overall_quality_score: ScoreValue | None = None
    quality_band: EvidenceQualityBand | None = None
    omit_risk: bool = False
    weak_evidence_tags: list[WeakEvidenceTag] = Field(default_factory=list)


class EvidenceRewriteSafety(StrictModel):
    """Structured guidance for how safely downstream phases may rewrite evidence."""

    level: RewriteSafetyLevel = RewriteSafetyLevel.SAFE
    rewrite_allowed: bool = True
    paraphrase_safe: bool = True
    merge_safe: bool = True
    preserve_metrics: bool = False
    preserve_named_entities: bool = False


class EvidenceCoverage(StrictModel):
    """Coverage metadata describing how much source support backs an evidence unit."""

    source_item_count: int = Field(default=1, ge=1)
    source_child_count: int = Field(default=0, ge=0)
    source_metric_count: int = Field(default=0, ge=0)
    source_link_count: int = Field(default=0, ge=0)
    multi_source_support: bool = False


class EvidenceProvenance(StrictModel):
    """Traceability payload linking an evidence unit back to source truth."""

    source_section: EvidenceSection
    source_item_type: ItemType
    source_parent_id: StableId
    source_parent_title: NonEmptyStr | None = None
    source_organization: NonEmptyStr | None = None
    source_child_id: StableId | None = None
    source_child_type: EvidenceChildType | None = None
    source_child_index: int | None = Field(default=None, ge=0)
    source_links: list[SourceLink] = Field(default_factory=list)
    extraction_method: NonEmptyStr
    metric_ids: list[StableId] = Field(default_factory=list)
    source_excerpt: NonEmptyStr | None = None
    provenance_notes: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_child_shape(self) -> "EvidenceProvenance":
        has_child_ref = self.source_child_id is not None or self.source_child_type is not None
        if (self.source_child_id is None) != (self.source_child_type is None):
            raise ValueError("source_child_id and source_child_type must be provided together")
        if self.source_child_index is not None and not has_child_ref:
            raise ValueError("source_child_index requires a child reference")
        return self

    @property
    def source_entity_id(self) -> str:
        return self.source_parent_id

    @property
    def source_entity_title(self) -> str | None:
        return self.source_parent_title

    @property
    def source_bullet_id(self) -> str | None:
        if self.source_child_type == EvidenceChildType.BULLET:
            return self.source_child_id
        return None


class EvidenceUnit(StrictModel):
    """First-class typed evidence record used across ranking, generation, and verification."""

    evidence_id: StableId
    source_type: EvidenceSourceType
    parent_link: EvidenceParentLink
    canonical_text: NonEmptyStr
    raw_text: NonEmptyStr
    normalized_skills: list[NonEmptyStr] = Field(default_factory=list)
    normalized_tools: list[NonEmptyStr] = Field(default_factory=list)
    normalized_domains: list[NonEmptyStr] = Field(default_factory=list)
    signals: EvidenceSignals = Field(default_factory=EvidenceSignals)
    enrichment: EvidenceEnrichment = Field(default_factory=EvidenceEnrichment)
    quality: EvidenceQuality = Field(default_factory=EvidenceQuality)
    rewrite_safety: EvidenceRewriteSafety = Field(default_factory=EvidenceRewriteSafety)
    coverage: EvidenceCoverage = Field(default_factory=EvidenceCoverage)
    recency: RecencyMetadata = Field(default_factory=RecencyMetadata)
    evidence_strength: EvidenceStrength
    verified_status: VerifiedStatus
    dedupe_fingerprint: NonEmptyStr
    provenance: EvidenceProvenance
    duplicate_of: StableId | None = None

    @model_validator(mode="after")
    def validate_source_alignment(self) -> "EvidenceUnit":
        if self.parent_link.source_parent_id != self.provenance.source_parent_id:
            raise ValueError("parent_link.source_parent_id must match provenance.source_parent_id")
        if self.parent_link.source_section != self.provenance.source_section:
            raise ValueError("parent_link.source_section must match provenance.source_section")
        if self.parent_link.source_parent_type != self.provenance.source_item_type:
            raise ValueError("parent_link.source_parent_type must match provenance.source_item_type")
        if self.parent_link.source_child_id != self.provenance.source_child_id:
            raise ValueError("parent_link.source_child_id must match provenance.source_child_id")
        if self.parent_link.source_child_type != self.provenance.source_child_type:
            raise ValueError("parent_link.source_child_type must match provenance.source_child_type")
        if self.parent_link.source_child_index != self.provenance.source_child_index:
            raise ValueError("parent_link.source_child_index must match provenance.source_child_index")
        return self

    @property
    def evidence_unit_id(self) -> str:
        return self.evidence_id

    @property
    def source_entity_id(self) -> str:
        return self.parent_link.source_parent_id

    @property
    def source_bullet_id(self) -> str | None:
        if self.parent_link.source_child_type == EvidenceChildType.BULLET:
            return self.parent_link.source_child_id
        return None

    @property
    def inferred_role_types(self) -> list[str]:
        return self.signals.role_family_hints

    @property
    def seniority_signals(self) -> list[str]:
        return self.signals.seniority_signals

    @property
    def impact_signals(self) -> list[str]:
        return self.signals.signal_tokens

    @property
    def metrics_present(self) -> bool:
        return self.signals.impact_metrics_present

    @property
    def rewrite_allowed(self) -> bool:
        return self.rewrite_safety.rewrite_allowed

    @property
    def clarity_score(self) -> float | None:
        return self.quality.clarity_score

    @property
    def weak_evidence_tags(self) -> list[WeakEvidenceTag]:
        return self.quality.weak_evidence_tags

    @property
    def role_family_hints(self) -> list[str]:
        return self.signals.role_family_hints

    @property
    def business_outcome_hints(self) -> list[str]:
        return self.signals.business_outcome_hints


class EvidenceOverlapLink(StrictModel):
    """Non-destructive overlap relationship retained alongside source truth."""

    relationship_id: StableId
    relationship_type: EvidenceRelationshipType
    primary_evidence_id: StableId
    related_evidence_id: StableId
    confidence_score: ScoreValue | None = None
    same_parent: bool = False
    suppress_as_repeat: bool = False
    prefer_primary: bool = True
    shared_tokens: list[NonEmptyStr] = Field(default_factory=list)
    shared_skills: list[NonEmptyStr] = Field(default_factory=list)
    shared_tools: list[NonEmptyStr] = Field(default_factory=list)
    shared_domains: list[NonEmptyStr] = Field(default_factory=list)
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def validate_distinct_evidence_ids(self) -> "EvidenceOverlapLink":
        if self.primary_evidence_id == self.related_evidence_id:
            raise ValueError("overlap links must reference two distinct evidence ids")
        return self


class CoverageDimension(StrictModel):
    """Candidate-level coverage facet derived from the evidence graph."""

    area: NonEmptyStr
    score: ScoreValue = 0.0
    band: CoverageBand = CoverageBand.SPARSE
    evidence_count: int = Field(default=0, ge=0)
    strong_evidence_count: int = Field(default=0, ge=0)
    quality_weighted_evidence: ScoreValue = 0.0
    evidence_ids: list[StableId] = Field(default_factory=list)
    rationale_signals: list[NonEmptyStr] = Field(default_factory=list)


class CoverageGap(StrictModel):
    """Under-supported area surfaced for later messaging and planning."""

    area: NonEmptyStr
    band: CoverageBand = CoverageBand.SPARSE
    reason: NonEmptyStr
    related_evidence_ids: list[StableId] = Field(default_factory=list)


class CoverageHighlight(StrictModel):
    """High-level coverage highlight with linked evidence references."""

    area: NonEmptyStr
    score: ScoreValue = 0.0
    band: CoverageBand = CoverageBand.SPARSE
    summary: NonEmptyStr
    evidence_ids: list[StableId] = Field(default_factory=list)


class CandidateEvidenceCoverageMap(StrictModel):
    """Deterministic candidate-level strengths and weak zones derived from Phase 2 evidence."""

    candidate_profile_id: StableId
    schema_version: NonEmptyStr = "phase2.candidate-evidence-coverage.v1"
    total_evidence_units: int = Field(default=0, ge=0)
    primary_evidence_units: int = Field(default=0, ge=0)
    suppressed_repeat_units: int = Field(default=0, ge=0)
    weak_evidence_units: int = Field(default=0, ge=0)
    declared_skill_units: int = Field(default=0, ge=0)
    role_family_strengths: list[CoverageDimension] = Field(default_factory=list)
    leadership_depth: CoverageDimension = Field(default_factory=lambda: CoverageDimension(area="leadership_depth"))
    ownership_depth: CoverageDimension = Field(default_factory=lambda: CoverageDimension(area="ownership_depth"))
    architecture_system_design_strength: CoverageDimension = Field(
        default_factory=lambda: CoverageDimension(area="architecture_system_design")
    )
    delivery_execution_strength: CoverageDimension = Field(
        default_factory=lambda: CoverageDimension(area="delivery_execution")
    )
    domain_strengths: list[CoverageDimension] = Field(default_factory=list)
    core_technical_clusters: list[CoverageDimension] = Field(default_factory=list)
    cloud_platform_strength: CoverageDimension = Field(
        default_factory=lambda: CoverageDimension(area="cloud_platform_strength")
    )
    product_stakeholder_strength: CoverageDimension = Field(
        default_factory=lambda: CoverageDimension(area="product_stakeholder_strength")
    )
    experimentation_analytics_strength: CoverageDimension = Field(
        default_factory=lambda: CoverageDimension(area="experimentation_analytics_strength")
    )
    certifications_strength: CoverageDimension = Field(
        default_factory=lambda: CoverageDimension(area="certifications_strength")
    )
    awards_distinction_strength: CoverageDimension = Field(
        default_factory=lambda: CoverageDimension(area="awards_distinction_strength")
    )
    sparsity_weak_zones: list[CoverageGap] = Field(default_factory=list)
    high_level_strengths: list[CoverageHighlight] = Field(default_factory=list)
    weak_match_flags: list[CoverageGap] = Field(default_factory=list)


class CandidateEvidenceGraph(StrictModel):
    """Top-level aggregate holding all typed evidence derived from one candidate profile."""

    schema_version: NonEmptyStr = EVIDENCE_GRAPH_SCHEMA_VERSION
    candidate_profile_id: StableId
    evidence_units: list[EvidenceUnit] = Field(default_factory=list)
    overlap_links: list[EvidenceOverlapLink] = Field(default_factory=list)


# Backward-compatible alias used by the existing ranking and scoring layers.
CanonicalEvidenceUnit = EvidenceUnit


__all__ = [
    "CanonicalEvidenceUnit",
    "CandidateEvidenceGraph",
    "CandidateEvidenceCoverageMap",
    "CoverageBand",
    "CoverageDimension",
    "CoverageGap",
    "CoverageHighlight",
    "EvidenceChildType",
    "EvidenceCoverage",
    "EvidenceEnrichment",
    "EvidenceOverlapLink",
    "EvidenceParentLink",
    "EvidenceProvenance",
    "EvidenceQuality",
    "EvidenceQualityBand",
    "EvidenceRelationshipType",
    "EvidenceRewriteSafety",
    "EvidenceSection",
    "EvidenceSignals",
    "EvidenceSourceType",
    "EvidenceTag",
    "EvidenceTagCategory",
    "EvidenceUnit",
    "ImpactType",
    "LeadershipSignal",
    "OwnershipLevel",
    "RecencyMetadata",
    "RoleSpecialty",
    "RewriteSafetyLevel",
    "WeakEvidenceTag",
]
