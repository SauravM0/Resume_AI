from __future__ import annotations

from resume_optimizer.evidence_models import (
    EvidenceEnrichment,
    EvidenceParentLink,
    EvidenceProvenance,
    EvidenceQuality,
    EvidenceSection,
    EvidenceSignals,
    EvidenceSourceType,
    EvidenceUnit,
)
from resume_optimizer.models import EvidenceStrength, ItemType, VerifiedStatus
from resume_optimizer.services.evidence_quality_service import EvidenceQualityService


def _unit(
    *,
    evidence_id: str,
    source_type,
    text: str,
    tools: list[str] | None = None,
    domains: list[str] | None = None,
    metric_count: int = 0,
    ownership_level="contributor",
    delivery_scope="task",
    business_outcomes: list[str] | None = None,
    recency_score: float | None = None,
    current: bool = False,
    rewrite_level="safe",
    rewrite_allowed: bool = True,
    architecture_score: float | None = None,
) -> EvidenceUnit:
    metric_ids = [f"metric.{index}" for index in range(metric_count)]
    is_cert = source_type == EvidenceSourceType.CERTIFICATION
    return EvidenceUnit(
        evidence_id=evidence_id,
        source_type=source_type,
        parent_link=EvidenceParentLink(
            source_section=EvidenceSection.CERTIFICATIONS if is_cert else EvidenceSection.EXPERIENCE,
            source_parent_id="parent.test",
            source_parent_type=ItemType.CERTIFICATION if is_cert else ItemType.EXPERIENCE,
            source_child_id="child.test" if not is_cert else None,
            source_child_type="bullet" if not is_cert else None,
            source_child_index=0 if not is_cert else None,
        ),
        canonical_text=text,
        raw_text=text,
        normalized_skills=[],
        normalized_tools=tools or [],
        normalized_domains=domains or [],
        signals=EvidenceSignals(
            ownership_level=ownership_level,
            leadership_signals=[],
            delivery_scope=delivery_scope,
            impact_types=[],
            impact_metrics_present=metric_count > 0,
            role_family_hints=[],
            business_outcome_hints=business_outcomes or [],
            seniority_signals=[],
            signal_tokens=[],
            tags=[],
        ),
        enrichment=EvidenceEnrichment(
            architecture_system_design_score=architecture_score,
        ),
        quality=EvidenceQuality(),
        rewrite_safety={
            "level": rewrite_level,
            "rewrite_allowed": rewrite_allowed,
            "paraphrase_safe": rewrite_allowed,
            "merge_safe": rewrite_allowed and rewrite_level == "safe",
            "preserve_metrics": metric_count > 0,
            "preserve_named_entities": metric_count > 0,
        },
        coverage={
            "source_item_count": 1,
            "source_child_count": 0 if source_type == EvidenceSourceType.CERTIFICATION else 1,
            "source_metric_count": metric_count,
            "source_link_count": 0,
            "multi_source_support": False,
        },
        recency={
            "start_date": "2024-01" if current else "2020-01",
            "end_date": None if current else "2021-06",
            "is_current": current,
            "source_recency_score": recency_score,
        },
        evidence_strength=EvidenceStrength.STRONG,
        verified_status=VerifiedStatus.CORROBORATED,
        dedupe_fingerprint=f"dedupe.{evidence_id}",
        provenance=EvidenceProvenance(
            source_section=EvidenceSection.CERTIFICATIONS if is_cert else EvidenceSection.EXPERIENCE,
            source_item_type=ItemType.CERTIFICATION if is_cert else ItemType.EXPERIENCE,
            source_parent_id="parent.test",
            source_parent_title="Senior Engineer",
            source_child_id="child.test" if not is_cert else None,
            source_child_type="bullet" if not is_cert else None,
            source_child_index=0 if not is_cert else None,
            extraction_method="test",
            metric_ids=metric_ids,
        ),
    )


def test_quality_scoring_prefers_strong_quantified_specific_evidence() -> None:
    service = EvidenceQualityService()
    strong = service.score(
        _unit(
            evidence_id="evidence.strong",
            source_type=EvidenceSourceType.EXPERIENCE_BULLET,
            text="Owned the checkout redesign using React and PostgreSQL, increasing conversion 18% and reducing support tickets by 22%.",
            tools=["React", "PostgreSQL"],
            domains=["frontend", "e-commerce"],
            metric_count=2,
            ownership_level="owner",
            delivery_scope="product",
            business_outcomes=["revenue_growth", "customer_adoption"],
            recency_score=0.92,
        )
    )
    weak = service.score(
        _unit(
            evidence_id="evidence.weak",
            source_type=EvidenceSourceType.EXPERIENCE_BULLET,
            text="Worked on checkout tasks for the team.",
            tools=[],
            domains=[],
            metric_count=0,
            ownership_level="contributor",
            delivery_scope="task",
            recency_score=0.92,
        )
    )

    assert strong.quality.overall_quality_score > weak.quality.overall_quality_score
    assert strong.quality.quality_band.value in {"strong", "medium"}
    assert weak.quality.quality_band.value in {"weak", "poor"}


def test_quality_scoring_prefers_quantified_over_vague_outcome_language() -> None:
    service = EvidenceQualityService()
    quantified = service.score(
        _unit(
            evidence_id="evidence.quantified",
            source_type=EvidenceSourceType.PROJECT_BULLET,
            text="Improved deployment throughput by 35% with CI automation.",
            tools=["GitHub Actions"],
            domains=["devops"],
            metric_count=1,
            delivery_scope="system",
        )
    )
    vague = service.score(
        _unit(
            evidence_id="evidence.vague",
            source_type=EvidenceSourceType.PROJECT_BULLET,
            text="Improved deployment processes for the team.",
            tools=[],
            domains=["devops"],
            metric_count=0,
            delivery_scope="system",
        )
    )

    assert quantified.quality.metric_presence_score > vague.quality.metric_presence_score
    assert quantified.quality.outcome_clarity_score > vague.quality.outcome_clarity_score
    assert quantified.quality.overall_quality_score > vague.quality.overall_quality_score


def test_quality_scoring_penalizes_passive_participation_language_vs_explicit_ownership() -> None:
    service = EvidenceQualityService()
    owner = service.score(
        _unit(
            evidence_id="evidence.owner",
            source_type=EvidenceSourceType.EXPERIENCE_BULLET,
            text="Owned service migration planning and delivered the cutover with zero downtime.",
            tools=["Kubernetes"],
            domains=["backend", "platform"],
            ownership_level="owner",
            delivery_scope="system",
        )
    )
    passive = service.score(
        _unit(
            evidence_id="evidence.passive",
            source_type=EvidenceSourceType.EXPERIENCE_BULLET,
            text="Helped with service migration tasks for the team.",
            tools=[],
            domains=["backend"],
            ownership_level="contributor",
            delivery_scope="task",
        )
    )

    assert owner.quality.ownership_clarity_score > passive.quality.ownership_clarity_score
    assert owner.quality.overall_quality_score > passive.quality.overall_quality_score


def test_recent_but_weak_evidence_does_not_outrank_old_strong_evidence() -> None:
    service = EvidenceQualityService()
    recent_weak = service.score(
        _unit(
            evidence_id="evidence.recentweak",
            source_type=EvidenceSourceType.EXPERIENCE_BULLET,
            text="Worked on backend services.",
            current=True,
            recency_score=0.98,
        )
    )
    older_strong = service.score(
        _unit(
            evidence_id="evidence.oldstrong",
            source_type=EvidenceSourceType.EXPERIENCE_BULLET,
            text="Designed a distributed API platform on Kubernetes and PostgreSQL, reducing p95 latency by 40% across critical services.",
            tools=["Kubernetes", "PostgreSQL"],
            domains=["backend", "platform"],
            metric_count=2,
            ownership_level="driver",
            delivery_scope="platform",
            recency_score=0.45,
            architecture_score=0.9,
        )
    )

    assert recent_weak.quality.recency_score > older_strong.quality.recency_score
    assert older_strong.quality.overall_quality_score > recent_weak.quality.overall_quality_score


def test_quality_scoring_behaves_sensibly_for_certifications() -> None:
    service = EvidenceQualityService()
    cert = service.score(
        _unit(
            evidence_id="evidence.cert",
            source_type=EvidenceSourceType.CERTIFICATION,
            text="AWS Solutions Architect certification from Amazon Web Services.",
            domains=["cloud"],
            recency_score=0.7,
            rewrite_level="caution",
        )
    )

    assert cert.quality.readability_score is not None
    assert cert.quality.rewrite_safety_score is not None
    assert cert.quality.quality_band is not None
    assert cert.quality.overall_quality_score is not None


def test_quality_thresholds_and_omit_risk_behave_sensibly() -> None:
    service = EvidenceQualityService()
    poor = service.score(
        _unit(
            evidence_id="evidence.poor",
            source_type=EvidenceSourceType.EXPERIENCE_BULLET,
            text="Worked on tasks.",
        )
    )

    assert poor.quality.quality_band.value == "poor"
    assert poor.quality.omit_risk is True
