from __future__ import annotations

from resume_optimizer.evidence_models import (
    EvidenceEnrichment,
    EvidenceParentLink,
    EvidenceProvenance,
    EvidenceSection,
    EvidenceSignals,
    EvidenceSourceType,
    EvidenceUnit,
)
from resume_optimizer.models import EvidenceStrength, ItemType, VerifiedStatus
from resume_optimizer.services.evidence_enrichment_service import EvidenceEnrichmentService


def _unit(
    *,
    text: str,
    domains: list[str] | None = None,
    tools: list[str] | None = None,
    role_hints: list[str] | None = None,
    leadership_signals=None,
    ownership_level="contributor",
    impact_types=None,
    impact_metrics_present: bool = False,
    business_outcomes: list[str] | None = None,
    source_title: str = "Software Engineer",
) -> EvidenceUnit:
    return EvidenceUnit(
        evidence_id="evidence.test",
        source_type=EvidenceSourceType.EXPERIENCE_BULLET,
        parent_link=EvidenceParentLink(
            source_section=EvidenceSection.EXPERIENCE,
            source_parent_id="exp.test",
            source_parent_type=ItemType.EXPERIENCE,
            source_child_id="bullet.test",
            source_child_type="bullet",
            source_child_index=0,
        ),
        canonical_text=text,
        raw_text=text,
        normalized_skills=[],
        normalized_tools=tools or [],
        normalized_domains=domains or [],
        signals=EvidenceSignals(
            ownership_level=ownership_level,
            leadership_signals=leadership_signals or [],
            delivery_scope="system",
            impact_types=impact_types or [],
            impact_metrics_present=impact_metrics_present,
            role_family_hints=role_hints or [],
            business_outcome_hints=business_outcomes or [],
            seniority_signals=[],
            signal_tokens=[],
            tags=[],
        ),
        enrichment=EvidenceEnrichment(),
        evidence_strength=EvidenceStrength.STRONG,
        verified_status=VerifiedStatus.CORROBORATED,
        dedupe_fingerprint="dedupe.test",
        provenance=EvidenceProvenance(
            source_section=EvidenceSection.EXPERIENCE,
            source_item_type=ItemType.EXPERIENCE,
            source_parent_id="exp.test",
            source_parent_title=source_title,
            source_child_id="bullet.test",
            source_child_type="bullet",
            source_child_index=0,
            extraction_method="experience_bullet",
        ),
    )


def test_enrichment_detects_architecture_only_with_meaningful_support() -> None:
    service = EvidenceEnrichmentService()
    strong = service.enrich(
        _unit(
            text="Architected a distributed service platform and redesigned API boundaries, improving reliability by 30%.",
            domains=["backend", "platform"],
            tools=["Kubernetes", "PostgreSQL"],
            impact_types=["reliability", "performance"],
            impact_metrics_present=True,
        )
    )
    weak = service.enrich(
        _unit(
            text="Worked on architecture discussions for the team.",
            domains=[],
            tools=[],
            impact_types=[],
            impact_metrics_present=False,
        )
    )

    assert strong.enrichment.architecture_system_design_score == 0.9
    assert "architecture_supported" in strong.enrichment.triggered_rules
    assert weak.enrichment.architecture_system_design_score < 0.7


def test_enrichment_does_not_inflate_leadership_from_plain_ic_language() -> None:
    service = EvidenceEnrichmentService()
    ic = service.enrich(
        _unit(
            text="Built backend APIs and improved query performance for reporting endpoints.",
            domains=["backend", "data"],
            tools=["PostgreSQL"],
            impact_types=["performance"],
        )
    )

    assert ic.enrichment.leadership_score == 0.0
    assert ic.enrichment.mentoring_score == 0.0
    assert "leadership_explicit" not in ic.enrichment.triggered_rules


def test_enrichment_detects_explicit_leadership_and_mentoring() -> None:
    service = EvidenceEnrichmentService()
    unit = service.enrich(
        _unit(
            text="Mentored four engineers, partnered with product and design, and led cross-functional rollout planning.",
            domains=["frontend"],
            role_hints=["frontend"],
            leadership_signals=["mentorship", "cross_functional_leadership", "technical_leadership"],
        )
    )

    assert unit.enrichment.leadership_score >= 0.85
    assert unit.enrichment.mentoring_score == 0.85
    assert unit.enrichment.stakeholder_management_score >= 0.6
    assert "mentoring_explicit" in unit.enrichment.triggered_rules


def test_enrichment_detects_business_outcome_quantified_impact_and_customer_facing() -> None:
    service = EvidenceEnrichmentService()
    unit = service.enrich(
        _unit(
            text="Redesigned the customer-facing checkout flow, increasing conversion 18% and reducing support tickets.",
            domains=["frontend", "e-commerce"],
            impact_types=["growth", "customer_experience"],
            impact_metrics_present=True,
            business_outcomes=["revenue_growth", "customer_adoption"],
        )
    )

    assert unit.enrichment.business_outcome_score >= 0.85
    assert unit.enrichment.quantified_impact_score >= 0.8
    assert unit.enrichment.customer_facing_score == 0.8


def test_enrichment_detects_internal_platform_automation_and_reliability() -> None:
    service = EvidenceEnrichmentService()
    unit = service.enrich(
        _unit(
            text="Built internal platform automation for deployment workflows, reducing incidents and improving uptime.",
            domains=["platform", "devops"],
            tools=["GitHub Actions", "Kubernetes"],
            role_hints=["devops"],
            impact_types=["reliability"],
            impact_metrics_present=True,
        )
    )

    assert unit.enrichment.internal_platform_score == 0.85
    assert unit.enrichment.automation_score == 0.8
    assert unit.enrichment.reliability_score == 0.85
    assert "internal_platform" in unit.enrichment.triggered_rules


def test_enrichment_detects_security_without_ownership_inflation() -> None:
    service = EvidenceEnrichmentService()
    unit = service.enrich(
        _unit(
            text="Implemented secure authentication controls and compliance checks for customer data handling.",
            domains=["security"],
            impact_types=["security", "compliance"],
            impact_metrics_present=False,
            ownership_level="contributor",
        )
    )

    assert unit.enrichment.compliance_security_score == 0.9
    assert unit.enrichment.ownership_score <= 0.2
