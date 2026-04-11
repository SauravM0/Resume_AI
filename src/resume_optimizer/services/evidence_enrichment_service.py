"""Deterministic Phase 2 evidence enrichment and tagging service."""

from __future__ import annotations

import re

from ..evidence_models import (
    DeliveryScope,
    EvidenceEnrichment,
    EvidenceUnit,
    ImpactType,
    LeadershipSignal,
    OwnershipLevel,
    RoleSpecialty,
)
from ..normalization import normalize_evidence_text

_ARCHITECTURE_TERMS = re.compile(
    r"\b(architecture|architected|system design|distributed system|distributed systems|service design|platform design)\b",
    re.IGNORECASE,
)
_SYSTEM_CONTEXT_TERMS = re.compile(
    r"\b(system|service|platform|api|infrastructure|backend|scalability|reliability)\b",
    re.IGNORECASE,
)
_EXPERIMENTATION_TERMS = re.compile(
    r"\b(experiment|experimentation|a/b|ab test|hypothesis|variant|rollout test)\b",
    re.IGNORECASE,
)
_AUTOMATION_TERMS = re.compile(
    r"\b(automation|automated|automate|scripted|ci/cd|pipeline|workflow|self-serve|self serve)\b",
    re.IGNORECASE,
)
_CUSTOMER_FACING_TERMS = re.compile(
    r"\b(customer-facing|customer facing|customer|user|client|self-serve|self serve)\b",
    re.IGNORECASE,
)
_INTERNAL_PLATFORM_TERMS = re.compile(
    r"\b(internal platform|platform|developer tools|tooling|internal tooling|shared service|enablement)\b",
    re.IGNORECASE,
)
_MOBILE_TERMS = re.compile(r"\b(mobile|ios|android|react native)\b", re.IGNORECASE)


class EvidenceEnrichmentService:
    """Enrich evidence units with conservative, deterministic strategist signals."""

    def enrich(self, evidence_unit: EvidenceUnit) -> EvidenceUnit:
        bundle = normalize_evidence_text(
            evidence_unit.raw_text,
            title=evidence_unit.provenance.source_parent_title,
        )
        enrichment = EvidenceEnrichment(
            role_specialties=_role_specialties(evidence_unit, bundle),
            architecture_system_design_score=_architecture_score(evidence_unit, bundle),
            ownership_score=_ownership_score(evidence_unit, bundle),
            leadership_score=_leadership_score(evidence_unit, bundle),
            mentoring_score=_mentoring_score(evidence_unit, bundle),
            stakeholder_management_score=_stakeholder_score(bundle),
            delivery_execution_score=_delivery_execution_score(evidence_unit, bundle),
            scaling_performance_score=_scaling_performance_score(evidence_unit),
            optimization_score=_optimization_score(evidence_unit, bundle),
            experimentation_score=_experimentation_score(evidence_unit),
            reliability_score=_reliability_score(evidence_unit),
            automation_score=_automation_score(evidence_unit),
            domain_specificity_score=_domain_specificity_score(evidence_unit),
            compliance_security_score=_compliance_security_score(evidence_unit),
            business_outcome_score=_business_outcome_score(evidence_unit),
            quantified_impact_score=_quantified_impact_score(evidence_unit),
            customer_facing_score=_customer_facing_score(evidence_unit),
            internal_platform_score=_internal_platform_score(evidence_unit),
            triggered_rules=_triggered_rules(evidence_unit, bundle),
        )
        return evidence_unit.model_copy(update={"enrichment": enrichment})


DEFAULT_EVIDENCE_ENRICHMENT_SERVICE = EvidenceEnrichmentService()


def _role_specialties(evidence_unit: EvidenceUnit, bundle) -> list[RoleSpecialty]:
    specialties: list[RoleSpecialty] = []
    domain_map = {
        "backend": RoleSpecialty.BACKEND,
        "frontend": RoleSpecialty.FRONTEND,
        "fullstack": RoleSpecialty.FULLSTACK,
        "data": RoleSpecialty.DATA,
        "devops": RoleSpecialty.DEVOPS,
        "machine-learning": RoleSpecialty.ML,
        "artificial-intelligence": RoleSpecialty.ML,
    }
    role_map = {
        "backend": RoleSpecialty.BACKEND,
        "frontend": RoleSpecialty.FRONTEND,
        "fullstack": RoleSpecialty.FULLSTACK,
        "data": RoleSpecialty.DATA,
        "devops": RoleSpecialty.DEVOPS,
        "ml": RoleSpecialty.ML,
        "product": RoleSpecialty.PRODUCT,
        "design": RoleSpecialty.DESIGN,
    }
    for domain in evidence_unit.normalized_domains:
        specialty = domain_map.get(domain)
        if specialty is not None and specialty not in specialties:
            specialties.append(specialty)
    for role in evidence_unit.signals.role_family_hints:
        specialty = role_map.get(role)
        if specialty is not None and specialty not in specialties:
            specialties.append(specialty)
    if _ARCHITECTURE_TERMS.search(evidence_unit.raw_text):
        specialties.append(RoleSpecialty.ARCHITECTURE)
    if _MOBILE_TERMS.search(evidence_unit.raw_text):
        specialties.append(RoleSpecialty.MOBILE)
    return _dedupe_specialties(specialties)


def _architecture_score(evidence_unit: EvidenceUnit, bundle) -> float:
    has_architecture_term = bool(_ARCHITECTURE_TERMS.search(evidence_unit.raw_text))
    has_system_context = bool(_SYSTEM_CONTEXT_TERMS.search(evidence_unit.raw_text))
    has_support = (
        bool(evidence_unit.normalized_tools)
        or "backend" in evidence_unit.normalized_domains
        or "platform" in evidence_unit.normalized_domains
        or evidence_unit.coverage.source_metric_count > 0
    )
    if has_architecture_term and has_system_context and has_support:
        return 0.9
    if has_architecture_term and has_system_context:
        return 0.65
    return 0.0


def _ownership_score(evidence_unit: EvidenceUnit, bundle) -> float:
    if evidence_unit.signals.ownership_level == OwnershipLevel.OWNER:
        return 0.9
    if evidence_unit.signals.ownership_level == OwnershipLevel.DRIVER:
        return 0.65
    if bundle.ownership_phrases:
        return 0.55
    return 0.2 if evidence_unit.signals.delivery_scope in {DeliveryScope.SYSTEM, DeliveryScope.PLATFORM} else 0.0


def _leadership_score(evidence_unit: EvidenceUnit, bundle) -> float:
    signals = set(evidence_unit.signals.leadership_signals)
    if LeadershipSignal.PEOPLE_MANAGEMENT in signals:
        return 0.95
    if LeadershipSignal.EXECUTIVE_LEADERSHIP in signals:
        return 0.95
    if LeadershipSignal.CROSS_FUNCTIONAL_LEADERSHIP in signals and LeadershipSignal.TECHNICAL_LEADERSHIP in signals:
        return 0.85
    if LeadershipSignal.TECHNICAL_LEADERSHIP in signals:
        return 0.7
    if LeadershipSignal.CROSS_FUNCTIONAL_LEADERSHIP in signals:
        return 0.6
    if LeadershipSignal.MENTORSHIP in signals:
        return 0.45
    return 0.0


def _mentoring_score(evidence_unit: EvidenceUnit, bundle) -> float:
    return 0.85 if LeadershipSignal.MENTORSHIP in evidence_unit.signals.leadership_signals else 0.0


def _stakeholder_score(bundle) -> float:
    if any(term.canonical == "stakeholder_management" for term in bundle.stakeholder_phrases):
        return 0.85
    if any(term.canonical == "cross_functional_collaboration" for term in bundle.stakeholder_phrases):
        return 0.6
    if any(term.canonical == "customer_partnership" for term in bundle.stakeholder_phrases):
        return 0.55
    return 0.0


def _delivery_execution_score(evidence_unit: EvidenceUnit, bundle) -> float:
    verb_bonus = 0.15 if any(term.canonical in {"build", "launch", "lead", "manage"} for term in bundle.action_verbs) else 0.0
    scope_bonus = 0.15 if evidence_unit.signals.delivery_scope in {DeliveryScope.FEATURE, DeliveryScope.SYSTEM, DeliveryScope.PLATFORM, DeliveryScope.PRODUCT} else 0.0
    quantified_bonus = 0.2 if evidence_unit.signals.impact_metrics_present else 0.0
    base = 0.25 if bundle.action_verbs else 0.0
    return min(1.0, base + verb_bonus + scope_bonus + quantified_bonus)


def _scaling_performance_score(evidence_unit: EvidenceUnit) -> float:
    if ImpactType.PERFORMANCE in evidence_unit.signals.impact_types and ImpactType.RELIABILITY in evidence_unit.signals.impact_types:
        return 0.9
    if ImpactType.PERFORMANCE in evidence_unit.signals.impact_types:
        return 0.8
    return 0.0


def _optimization_score(evidence_unit: EvidenceUnit, bundle) -> float:
    if any(term.canonical in {"optimize", "reduce", "increase"} for term in bundle.action_verbs):
        return 0.8 if evidence_unit.signals.impact_metrics_present else 0.6
    return 0.0


def _experimentation_score(evidence_unit: EvidenceUnit) -> float:
    return 0.8 if _EXPERIMENTATION_TERMS.search(evidence_unit.raw_text) else 0.0


def _reliability_score(evidence_unit: EvidenceUnit) -> float:
    if ImpactType.RELIABILITY in evidence_unit.signals.impact_types:
        return 0.85
    return 0.0


def _automation_score(evidence_unit: EvidenceUnit) -> float:
    return 0.8 if _AUTOMATION_TERMS.search(evidence_unit.raw_text) else 0.0


def _domain_specificity_score(evidence_unit: EvidenceUnit) -> float:
    if len(evidence_unit.normalized_domains) >= 3:
        return 0.85
    if len(evidence_unit.normalized_domains) == 2:
        return 0.65
    if len(evidence_unit.normalized_domains) == 1:
        return 0.4
    return 0.0


def _compliance_security_score(evidence_unit: EvidenceUnit) -> float:
    if ImpactType.SECURITY in evidence_unit.signals.impact_types and ImpactType.COMPLIANCE in evidence_unit.signals.impact_types:
        return 0.9
    if ImpactType.SECURITY in evidence_unit.signals.impact_types:
        return 0.75
    if ImpactType.COMPLIANCE in evidence_unit.signals.impact_types:
        return 0.7
    return 0.0


def _business_outcome_score(evidence_unit: EvidenceUnit) -> float:
    if len(evidence_unit.signals.business_outcome_hints) >= 2:
        return 0.85
    if len(evidence_unit.signals.business_outcome_hints) == 1:
        return 0.65
    if any(
        impact in evidence_unit.signals.impact_types
        for impact in {ImpactType.COST, ImpactType.REVENUE, ImpactType.GROWTH, ImpactType.CUSTOMER_EXPERIENCE}
    ):
        return 0.55
    return 0.0


def _quantified_impact_score(evidence_unit: EvidenceUnit) -> float:
    if evidence_unit.signals.impact_metrics_present and evidence_unit.coverage.source_metric_count >= 2:
        return 0.95
    if evidence_unit.signals.impact_metrics_present:
        return 0.8
    if any(char.isdigit() for char in evidence_unit.raw_text):
        return 0.6
    return 0.0


def _customer_facing_score(evidence_unit: EvidenceUnit) -> float:
    return 0.8 if _CUSTOMER_FACING_TERMS.search(evidence_unit.raw_text) or ImpactType.CUSTOMER_EXPERIENCE in evidence_unit.signals.impact_types else 0.0


def _internal_platform_score(evidence_unit: EvidenceUnit) -> float:
    return 0.85 if _INTERNAL_PLATFORM_TERMS.search(evidence_unit.raw_text) or "platform" in evidence_unit.normalized_domains else 0.0


def _triggered_rules(evidence_unit: EvidenceUnit, bundle) -> list[str]:
    rules: list[str] = []
    if _architecture_score(evidence_unit, bundle) > 0:
        rules.append("architecture_supported")
    if _ownership_score(evidence_unit, bundle) >= 0.65:
        rules.append("ownership_explicit")
    if _leadership_score(evidence_unit, bundle) > 0:
        rules.append("leadership_explicit")
    if _mentoring_score(evidence_unit, bundle) > 0:
        rules.append("mentoring_explicit")
    if _stakeholder_score(bundle) > 0:
        rules.append("stakeholder_management")
    if _delivery_execution_score(evidence_unit, bundle) >= 0.5:
        rules.append("delivery_execution")
    if _scaling_performance_score(evidence_unit) > 0:
        rules.append("scaling_or_performance")
    if _optimization_score(evidence_unit, bundle) > 0:
        rules.append("optimization")
    if _experimentation_score(evidence_unit) > 0:
        rules.append("experimentation")
    if _reliability_score(evidence_unit) > 0:
        rules.append("reliability")
    if _automation_score(evidence_unit) > 0:
        rules.append("automation")
    if _compliance_security_score(evidence_unit) > 0:
        rules.append("security_or_compliance")
    if _business_outcome_score(evidence_unit) > 0:
        rules.append("business_outcome")
    if _quantified_impact_score(evidence_unit) > 0:
        rules.append("quantified_impact")
    if _customer_facing_score(evidence_unit) > 0:
        rules.append("customer_facing")
    if _internal_platform_score(evidence_unit) > 0:
        rules.append("internal_platform")
    return rules


def _dedupe_specialties(values: list[RoleSpecialty]) -> list[RoleSpecialty]:
    deduped: list[RoleSpecialty] = []
    seen: set[RoleSpecialty] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
