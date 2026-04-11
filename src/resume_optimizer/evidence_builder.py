"""Deterministic candidate-evidence extraction and canonicalization."""

from __future__ import annotations

from hashlib import sha1
import re

from .evidence_models import (
    CanonicalEvidenceUnit,
    CandidateEvidenceGraph,
    DeliveryScope,
    EvidenceChildType,
    EvidenceCoverage,
    EvidenceParentLink,
    EvidenceProvenance,
    EvidenceQuality,
    EvidenceRewriteSafety,
    EvidenceSection,
    EvidenceSignals,
    EvidenceSourceType,
    EvidenceTag,
    EvidenceTagCategory,
    EvidenceUnit,
    ImpactType,
    LeadershipSignal,
    OwnershipLevel,
    RecencyMetadata,
    RewriteSafetyLevel,
    WeakEvidenceTag,
)
from .models import (
    AwardEntry,
    BulletEntry,
    CertificationEntry,
    EducationEntry,
    ExperienceEntry,
    MasterProfile,
    MetricEntry,
    PartialDate,
    PersonalProfile,
    ProjectEntry,
    SkillEntry,
    VerifiedStatus,
)
from .normalization import (
    normalize_evidence_text,
    normalize_role_taxonomy,
    normalize_seniority_taxonomy,
    normalize_skill_list,
    normalize_title_taxonomy,
    normalize_tool_list,
)

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9.+#/-]+")
_VAGUE_PATTERNS = (
    re.compile(r"\b(helped|worked on|involved in|responsible for|participated in)\b", re.IGNORECASE),
    re.compile(r"\b(various|multiple|several)\b", re.IGNORECASE),
)
_OWNERSHIP_OWNER_PATTERNS = (
    re.compile(r"\b(owned|owner|ownership|led|spearheaded|drove)\b", re.IGNORECASE),
)
_OWNERSHIP_DRIVER_PATTERNS = (
    re.compile(r"\b(built|launched|delivered|implemented|designed)\b", re.IGNORECASE),
)
_LEADERSHIP_SIGNAL_PATTERNS: tuple[tuple[LeadershipSignal, re.Pattern[str]], ...] = (
    (LeadershipSignal.PEOPLE_MANAGEMENT, re.compile(r"\b(managed|manager|hired|coached)\b", re.IGNORECASE)),
    (LeadershipSignal.CROSS_FUNCTIONAL_LEADERSHIP, re.compile(r"\b(cross-functional|stakeholder|partnered)\b", re.IGNORECASE)),
    (LeadershipSignal.TECHNICAL_LEADERSHIP, re.compile(r"\b(architected|led|tech lead|technical lead)\b", re.IGNORECASE)),
    (LeadershipSignal.MENTORSHIP, re.compile(r"\b(mentored|mentoring|guided)\b", re.IGNORECASE)),
    (LeadershipSignal.EXECUTIVE_LEADERSHIP, re.compile(r"\b(strategy|executive|vp|director)\b", re.IGNORECASE)),
)
_DELIVERY_SCOPE_PATTERNS: tuple[tuple[DeliveryScope, re.Pattern[str]], ...] = (
    (DeliveryScope.COMPANY, re.compile(r"\b(company|enterprise|org-wide|global)\b", re.IGNORECASE)),
    (DeliveryScope.ORGANIZATION, re.compile(r"\b(team|department|organization|cross-functional)\b", re.IGNORECASE)),
    (DeliveryScope.PLATFORM, re.compile(r"\b(platform|infrastructure|shared service)\b", re.IGNORECASE)),
    (DeliveryScope.SYSTEM, re.compile(r"\b(system|service|backend|api)\b", re.IGNORECASE)),
    (DeliveryScope.PRODUCT, re.compile(r"\b(product|customer-facing|application)\b", re.IGNORECASE)),
    (DeliveryScope.FEATURE, re.compile(r"\b(feature|workflow|module)\b", re.IGNORECASE)),
)
_IMPACT_PATTERNS: tuple[tuple[ImpactType, re.Pattern[str]], ...] = (
    (ImpactType.COST, re.compile(r"\b(cost|save|savings|budget)\b", re.IGNORECASE)),
    (ImpactType.REVENUE, re.compile(r"\b(revenue|sales|pipeline|upsell)\b", re.IGNORECASE)),
    (ImpactType.GROWTH, re.compile(r"\b(growth|adoption|conversion|retention|engagement)\b", re.IGNORECASE)),
    (ImpactType.RELIABILITY, re.compile(r"\b(reliability|availability|uptime|incident)\b", re.IGNORECASE)),
    (ImpactType.PERFORMANCE, re.compile(r"\b(latency|performance|throughput|speed)\b", re.IGNORECASE)),
    (ImpactType.QUALITY, re.compile(r"\b(quality|defect|bug|test)\b", re.IGNORECASE)),
    (ImpactType.SECURITY, re.compile(r"\b(security|secure|auth|compliance)\b", re.IGNORECASE)),
    (ImpactType.CUSTOMER_EXPERIENCE, re.compile(r"\b(customer|user|ux|satisfaction)\b", re.IGNORECASE)),
    (ImpactType.EFFICIENCY, re.compile(r"\b(automation|efficiency|productivity|time saved)\b", re.IGNORECASE)),
)
_BUSINESS_OUTCOME_HINT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cost_reduction", re.compile(r"\b(cost|savings|budget)\b", re.IGNORECASE)),
    ("revenue_growth", re.compile(r"\b(revenue|sales|pipeline|growth)\b", re.IGNORECASE)),
    ("customer_adoption", re.compile(r"\b(adoption|retention|engagement|customer)\b", re.IGNORECASE)),
    ("reliability", re.compile(r"\b(reliability|uptime|incident|availability)\b", re.IGNORECASE)),
    ("operational_efficiency", re.compile(r"\b(automation|efficiency|hours|manual)\b", re.IGNORECASE)),
)


def build_candidate_evidence_graph(profile: MasterProfile) -> CandidateEvidenceGraph:
    """Extract the full typed evidence graph from the normalized master profile."""

    units: list[EvidenceUnit] = []

    units.extend(_build_personal_summary_units(profile.personal_profile))
    for experience in profile.experience:
        units.extend(_build_experience_units(experience))
    for project in profile.projects:
        units.extend(_build_project_units(project))
    for education in profile.education:
        units.extend(_build_education_units(education))
    for certification in profile.certifications:
        units.append(_build_certification_unit(certification))
    for award in profile.awards:
        units.extend(_build_award_units(award))
    for skill in profile.skills:
        skill_unit = _build_verified_skill_unit(skill)
        if skill_unit is not None:
            units.append(skill_unit)

    from .services.evidence_overlap_service import DEFAULT_EVIDENCE_OVERLAP_RESOLUTION_SERVICE

    overlap_resolution = DEFAULT_EVIDENCE_OVERLAP_RESOLUTION_SERVICE.resolve(units)
    return CandidateEvidenceGraph(
        candidate_profile_id=profile.id,
        evidence_units=overlap_resolution.evidence_units,
        overlap_links=overlap_resolution.overlap_links,
    )


def build_canonical_evidence_units(profile: MasterProfile) -> list[CanonicalEvidenceUnit]:
    """Return the ranking-safe subset of the full candidate evidence graph."""

    graph = build_candidate_evidence_graph(profile)
    allowed = {
        EvidenceSourceType.EXPERIENCE_BULLET,
        EvidenceSourceType.EXPERIENCE_SUMMARY,
        EvidenceSourceType.PROJECT_BULLET,
        EvidenceSourceType.PROJECT_SUMMARY,
        EvidenceSourceType.CERTIFICATION,
        EvidenceSourceType.SKILL_DECLARATION,
        EvidenceSourceType.VERIFIED_SKILL,
    }
    return [unit for unit in graph.evidence_units if unit.source_type in allowed]


def generate_deterministic_evidence_unit_id(
    *,
    source_entity_id: str,
    source_type: EvidenceSourceType,
    raw_text: str,
    ordinal: int = 0,
) -> str:
    """Generate a stable deterministic id for evidence without native child ids."""

    digest = sha1(
        f"{source_entity_id}|{source_type.value}|{ordinal}|{_normalize_text(raw_text)}".encode("utf-8")
    ).hexdigest()[:12]
    return f"evidence.{source_type.value}.{digest}"


def _build_personal_summary_units(profile: PersonalProfile) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []
    if profile.headline:
        headline_bundle = normalize_evidence_text(profile.headline, title=profile.headline)
        units.append(
            _make_evidence_unit(
                evidence_id=generate_deterministic_evidence_unit_id(
                    source_entity_id=profile.id,
                    source_type=EvidenceSourceType.PERSONAL_SUMMARY,
                    raw_text=profile.headline,
                    ordinal=0,
                ),
                source_type=EvidenceSourceType.PERSONAL_SUMMARY,
                parent_link=EvidenceParentLink(
                    source_section=EvidenceSection.PERSONAL_PROFILE,
                    source_parent_id=profile.id,
                    source_parent_type=profile.item_type,
                ),
                canonical_text=_normalize_text(profile.headline),
                raw_text=profile.headline,
                normalized_skills=[term.canonical for term in _extract_known_skill_terms(profile.headline)],
                normalized_tools=_bundle_tool_terms(headline_bundle),
                normalized_domains=_merge_terms(
                    profile.domain_tags,
                    profile.canonical_tags,
                    [term.canonical for term in headline_bundle.domains_industries],
                ),
                signals=_build_signals(
                    raw_text=profile.headline,
                    role_values=[profile.role_type.value if profile.role_type else None],
                    seniority_values=[profile.seniority_level.value if profile.seniority_level else None],
                    metrics=[],
                    impact_score=None,
                    is_current=False,
                    tags=[],
                    normalization_bundle=headline_bundle,
                ),
                recency=RecencyMetadata(),
                evidence_strength=profile.evidence_strength,
                verified_status=profile.verified_status,
                rewrite_allowed=profile.rewrite_allowed,
                provenance=EvidenceProvenance(
                    source_section=EvidenceSection.PERSONAL_PROFILE,
                    source_item_type=profile.item_type,
                    source_parent_id=profile.id,
                    source_parent_title=profile.headline,
                    source_links=profile.source_links,
                    extraction_method="personal_headline",
                    metric_ids=[],
                ),
                metric_ids=[],
            )
        )
    if profile.summary:
        summary_bundle = normalize_evidence_text(profile.summary, title=profile.headline or profile.full_name)
        units.append(
            _make_evidence_unit(
                evidence_id=generate_deterministic_evidence_unit_id(
                    source_entity_id=profile.id,
                    source_type=EvidenceSourceType.PERSONAL_SUMMARY,
                    raw_text=profile.summary,
                    ordinal=1,
                ),
                source_type=EvidenceSourceType.PERSONAL_SUMMARY,
                parent_link=EvidenceParentLink(
                    source_section=EvidenceSection.PERSONAL_PROFILE,
                    source_parent_id=profile.id,
                    source_parent_type=profile.item_type,
                ),
                canonical_text=_normalize_text(profile.summary),
                raw_text=profile.summary,
                normalized_skills=[term.canonical for term in _extract_known_skill_terms(profile.summary)],
                normalized_tools=_bundle_tool_terms(summary_bundle),
                normalized_domains=_merge_terms(
                    profile.domain_tags,
                    profile.canonical_tags,
                    [term.canonical for term in summary_bundle.domains_industries],
                ),
                signals=_build_signals(
                    raw_text=profile.summary,
                    role_values=[profile.role_type.value if profile.role_type else None],
                    seniority_values=[profile.seniority_level.value if profile.seniority_level else None],
                    metrics=[],
                    impact_score=None,
                    is_current=False,
                    tags=[],
                    normalization_bundle=summary_bundle,
                ),
                recency=RecencyMetadata(),
                evidence_strength=profile.evidence_strength,
                verified_status=profile.verified_status,
                rewrite_allowed=profile.rewrite_allowed,
                provenance=EvidenceProvenance(
                    source_section=EvidenceSection.PERSONAL_PROFILE,
                    source_item_type=profile.item_type,
                    source_parent_id=profile.id,
                    source_parent_title=profile.headline or profile.full_name,
                    source_links=profile.source_links,
                    extraction_method="personal_summary",
                    metric_ids=[],
                ),
                metric_ids=[],
            )
        )
    return units


def _build_experience_units(entry: ExperienceEntry) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []

    for index, bullet in enumerate(entry.bullets):
        bullet_id = bullet.id or generate_deterministic_evidence_unit_id(
            source_entity_id=entry.id,
            source_type=EvidenceSourceType.EXPERIENCE_BULLET,
            raw_text=bullet.text,
            ordinal=index,
        )
        units.append(
            _make_bullet_unit(
                source_section=EvidenceSection.EXPERIENCE,
                parent_id=entry.id,
                parent_type=entry.item_type,
                child_id=bullet_id,
                child_index=index,
                source_type=EvidenceSourceType.EXPERIENCE_BULLET,
                raw_text=bullet.text,
                canonical_text=_normalize_text(bullet.text),
                entity_title=entry.title,
                entity_org=entry.organization,
                parent_tools=entry.tools,
                parent_domain_tags=entry.domain_tags,
                parent_canonical_tags=entry.canonical_tags,
                parent_role_value=entry.role_type.value if entry.role_type else None,
                parent_seniority_value=entry.seniority_level.value if entry.seniority_level else None,
                metrics=[*bullet.metrics, *entry.metrics],
                bullet_metrics=bullet.metrics,
                item_evidence_strength=bullet.evidence_strength,
                item_verified_status=bullet.verified_status,
                rewrite_allowed=bullet.rewrite_allowed,
                source_links=bullet.source_links or entry.source_links,
                recency=RecencyMetadata(
                    start_date=_normalize_date(entry.start_date),
                    end_date=None if entry.current else _normalize_date(entry.end_date),
                    is_current=entry.current,
                    source_recency_score=bullet.recency_score or entry.recency_score,
                ),
                tools=[*bullet.tools, *entry.tools],
                impact_score=bullet.impact_score or entry.impact_score,
                extraction_method="experience_bullet",
            )
        )

    summary_text = f"{entry.title} at {entry.organization}"
    summary_bundle = normalize_evidence_text(summary_text, title=entry.title)
    units.append(
        _make_evidence_unit(
            evidence_id=generate_deterministic_evidence_unit_id(
                source_entity_id=entry.id,
                source_type=EvidenceSourceType.EXPERIENCE_SUMMARY,
                raw_text=summary_text,
            ),
            source_type=EvidenceSourceType.EXPERIENCE_SUMMARY,
            parent_link=EvidenceParentLink(
                source_section=EvidenceSection.EXPERIENCE,
                source_parent_id=entry.id,
                source_parent_type=entry.item_type,
            ),
            canonical_text=summary_text,
            raw_text=summary_text,
            normalized_skills=[term.canonical for term in _extract_known_skill_terms(entry.title, *entry.tools)],
            normalized_tools=_merge_terms(
                [term.canonical for term in normalize_tool_list(entry.tools)],
                _bundle_tool_terms(summary_bundle),
            ),
            normalized_domains=_merge_terms(
                entry.domain_tags,
                entry.canonical_tags,
                [term.canonical for term in summary_bundle.domains_industries],
            ),
            signals=_build_signals(
                raw_text=summary_text,
                role_values=[entry.role_type.value if entry.role_type else None, normalize_title_taxonomy(entry.title).role_type_hint, entry.title],
                seniority_values=[entry.seniority_level.value if entry.seniority_level else None, normalize_title_taxonomy(entry.title).seniority_hint, entry.title],
                metrics=entry.metrics,
                impact_score=entry.impact_score,
                is_current=entry.current,
                tags=[],
                normalization_bundle=summary_bundle,
            ),
            recency=RecencyMetadata(
                start_date=_normalize_date(entry.start_date),
                end_date=None if entry.current else _normalize_date(entry.end_date),
                is_current=entry.current,
                source_recency_score=entry.recency_score,
            ),
            evidence_strength=entry.evidence_strength,
            verified_status=entry.verified_status,
            rewrite_allowed=entry.rewrite_allowed,
            provenance=EvidenceProvenance(
                source_section=EvidenceSection.EXPERIENCE,
                source_item_type=entry.item_type,
                source_parent_id=entry.id,
                source_parent_title=entry.title,
                source_organization=entry.organization,
                source_links=entry.source_links,
                extraction_method="experience_summary",
                metric_ids=[metric.id for metric in entry.metrics],
            ),
            metric_ids=[metric.id for metric in entry.metrics],
        )
    )
    return units


def _build_project_units(entry: ProjectEntry) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []

    for index, bullet in enumerate(entry.bullets):
        bullet_id = bullet.id or generate_deterministic_evidence_unit_id(
            source_entity_id=entry.id,
            source_type=EvidenceSourceType.PROJECT_BULLET,
            raw_text=bullet.text,
            ordinal=index,
        )
        units.append(
            _make_bullet_unit(
                source_section=EvidenceSection.PROJECTS,
                parent_id=entry.id,
                parent_type=entry.item_type,
                child_id=bullet_id,
                child_index=index,
                source_type=EvidenceSourceType.PROJECT_BULLET,
                raw_text=bullet.text,
                canonical_text=_normalize_text(bullet.text),
                entity_title=entry.name,
                entity_org=None,
                parent_tools=entry.tools,
                parent_domain_tags=entry.domain_tags,
                parent_canonical_tags=entry.canonical_tags,
                parent_role_value=entry.role_type.value if entry.role_type else None,
                parent_seniority_value=entry.seniority_level.value if entry.seniority_level else None,
                metrics=[*bullet.metrics, *entry.metrics],
                bullet_metrics=bullet.metrics,
                item_evidence_strength=bullet.evidence_strength,
                item_verified_status=bullet.verified_status,
                rewrite_allowed=bullet.rewrite_allowed,
                source_links=bullet.source_links or entry.source_links,
                recency=RecencyMetadata(
                    start_date=_normalize_date(entry.start_date),
                    end_date=_normalize_date(entry.end_date),
                    source_recency_score=bullet.recency_score or entry.recency_score,
                ),
                tools=[*bullet.tools, *entry.tools],
                impact_score=bullet.impact_score or entry.impact_score,
                extraction_method="project_bullet",
            )
        )

    if entry.summary:
        summary_bundle = normalize_evidence_text(entry.summary, title=entry.role or entry.name)
        units.append(
            _make_evidence_unit(
                evidence_id=generate_deterministic_evidence_unit_id(
                    source_entity_id=entry.id,
                    source_type=EvidenceSourceType.PROJECT_SUMMARY,
                    raw_text=entry.summary,
                ),
                source_type=EvidenceSourceType.PROJECT_SUMMARY,
                parent_link=EvidenceParentLink(
                    source_section=EvidenceSection.PROJECTS,
                    source_parent_id=entry.id,
                    source_parent_type=entry.item_type,
                ),
                canonical_text=_normalize_text(entry.summary),
                raw_text=entry.summary,
                normalized_skills=[term.canonical for term in _extract_known_skill_terms(entry.summary, *entry.tools)],
                normalized_tools=_merge_terms(
                    [term.canonical for term in normalize_tool_list(entry.tools)],
                    _bundle_tool_terms(summary_bundle),
                ),
                normalized_domains=_merge_terms(
                    entry.domain_tags,
                    entry.canonical_tags,
                    [term.canonical for term in summary_bundle.domains_industries],
                ),
                signals=_build_signals(
                    raw_text=entry.summary,
                    role_values=[entry.role_type.value if entry.role_type else None, normalize_title_taxonomy(entry.role or entry.name).role_type_hint, entry.role or entry.name],
                    seniority_values=[entry.seniority_level.value if entry.seniority_level else None, normalize_title_taxonomy(entry.role or entry.name).seniority_hint, entry.role or entry.name],
                    metrics=entry.metrics,
                    impact_score=entry.impact_score,
                    is_current=False,
                    tags=[],
                    normalization_bundle=summary_bundle,
                ),
                recency=RecencyMetadata(
                    start_date=_normalize_date(entry.start_date),
                    end_date=_normalize_date(entry.end_date),
                    source_recency_score=entry.recency_score,
                ),
                evidence_strength=entry.evidence_strength,
                verified_status=entry.verified_status,
                rewrite_allowed=entry.rewrite_allowed,
                provenance=EvidenceProvenance(
                    source_section=EvidenceSection.PROJECTS,
                    source_item_type=entry.item_type,
                    source_parent_id=entry.id,
                    source_parent_title=entry.name,
                    source_links=entry.source_links,
                    extraction_method="project_summary",
                    metric_ids=[metric.id for metric in entry.metrics],
                ),
                metric_ids=[metric.id for metric in entry.metrics],
            )
        )
    return units


def _build_education_units(entry: EducationEntry) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []
    for index, bullet in enumerate(entry.bullets):
        bullet_bundle = normalize_evidence_text(bullet.text, title=entry.degree)
        units.append(
            _make_evidence_unit(
                evidence_id=f"evidence.{bullet.id}",
                source_type=EvidenceSourceType.EDUCATION_ACHIEVEMENT,
                parent_link=EvidenceParentLink(
                    source_section=EvidenceSection.EDUCATION,
                    source_parent_id=entry.id,
                    source_parent_type=entry.item_type,
                    source_child_id=bullet.id,
                    source_child_type=EvidenceChildType.BULLET,
                    source_child_index=index,
                ),
                canonical_text=_normalize_text(bullet.text),
                raw_text=bullet.text,
                normalized_skills=[term.canonical for term in _extract_known_skill_terms(bullet.text, *bullet.tools)],
                normalized_tools=_merge_terms(
                    [term.canonical for term in normalize_tool_list(bullet.tools)],
                    _bundle_tool_terms(bullet_bundle),
                ),
                normalized_domains=_merge_terms(
                    entry.domain_tags,
                    entry.canonical_tags,
                    [term.canonical for term in bullet_bundle.domains_industries],
                ),
                signals=_build_signals(
                    raw_text=bullet.text,
                    role_values=[],
                    seniority_values=[],
                    metrics=bullet.metrics,
                    impact_score=bullet.impact_score,
                    is_current=False,
                    tags=[],
                    normalization_bundle=bullet_bundle,
                ),
                recency=RecencyMetadata(
                    start_date=_normalize_date(entry.start_date),
                    end_date=_normalize_date(entry.end_date),
                ),
                evidence_strength=bullet.evidence_strength,
                verified_status=bullet.verified_status,
                rewrite_allowed=bullet.rewrite_allowed,
                provenance=EvidenceProvenance(
                    source_section=EvidenceSection.EDUCATION,
                    source_item_type=entry.item_type,
                    source_parent_id=entry.id,
                    source_parent_title=entry.degree,
                    source_organization=entry.institution,
                    source_child_id=bullet.id,
                    source_child_type=EvidenceChildType.BULLET,
                    source_child_index=index,
                    source_links=bullet.source_links or entry.source_links,
                    extraction_method="education_bullet",
                    metric_ids=[metric.id for metric in bullet.metrics],
                ),
                metric_ids=[metric.id for metric in bullet.metrics],
            )
        )
    for index, honor in enumerate(entry.honors):
        honor_id = generate_deterministic_evidence_unit_id(
            source_entity_id=entry.id,
            source_type=EvidenceSourceType.EDUCATION_ACHIEVEMENT,
            raw_text=honor,
            ordinal=index,
        )
        units.append(
            _make_evidence_unit(
                evidence_id=honor_id,
                source_type=EvidenceSourceType.EDUCATION_ACHIEVEMENT,
                parent_link=EvidenceParentLink(
                    source_section=EvidenceSection.EDUCATION,
                    source_parent_id=entry.id,
                    source_parent_type=entry.item_type,
                    source_child_id=honor_id,
                    source_child_type=EvidenceChildType.HONOR,
                    source_child_index=index,
                ),
                canonical_text=_normalize_text(honor),
                raw_text=honor,
                normalized_skills=[term.canonical for term in _extract_known_skill_terms(honor)],
                normalized_tools=_bundle_tool_terms(normalize_evidence_text(honor, title=entry.degree)),
                normalized_domains=_merge_terms(
                    entry.domain_tags,
                    entry.canonical_tags,
                    [term.canonical for term in normalize_evidence_text(honor, title=entry.degree).domains_industries],
                ),
                signals=_build_signals(
                    raw_text=honor,
                    role_values=[],
                    seniority_values=[],
                    metrics=[],
                    impact_score=None,
                    is_current=False,
                    tags=[EvidenceTag(category=EvidenceTagCategory.SIGNAL, value="education_honor")],
                    normalization_bundle=normalize_evidence_text(honor, title=entry.degree),
                ),
                recency=RecencyMetadata(
                    start_date=_normalize_date(entry.start_date),
                    end_date=_normalize_date(entry.end_date),
                ),
                evidence_strength=entry.evidence_strength,
                verified_status=entry.verified_status,
                rewrite_allowed=entry.rewrite_allowed,
                provenance=EvidenceProvenance(
                    source_section=EvidenceSection.EDUCATION,
                    source_item_type=entry.item_type,
                    source_parent_id=entry.id,
                    source_parent_title=entry.degree,
                    source_organization=entry.institution,
                    source_child_id=honor_id,
                    source_child_type=EvidenceChildType.HONOR,
                    source_child_index=index,
                    source_links=entry.source_links,
                    extraction_method="education_honor",
                    metric_ids=[],
                ),
                metric_ids=[],
            )
        )
    return units


def _build_certification_unit(entry: CertificationEntry) -> EvidenceUnit:
    raw_text = f"{entry.name} certification from {entry.issuer}"
    bundle = normalize_evidence_text(raw_text, title=entry.name)
    return _make_evidence_unit(
        evidence_id=f"evidence.{entry.id}",
        source_type=EvidenceSourceType.CERTIFICATION,
        parent_link=EvidenceParentLink(
            source_section=EvidenceSection.CERTIFICATIONS,
            source_parent_id=entry.id,
            source_parent_type=entry.item_type,
        ),
        canonical_text=_normalize_text(raw_text),
        raw_text=raw_text,
        normalized_skills=[term.canonical for term in _extract_known_skill_terms(entry.name)],
        normalized_tools=_bundle_tool_terms(bundle),
        normalized_domains=_merge_terms(
            entry.domain_tags,
            entry.canonical_tags,
            [term.canonical for term in bundle.domains_industries],
        ),
        signals=_build_signals(
            raw_text=raw_text,
            role_values=[],
            seniority_values=[],
            metrics=[],
            impact_score=None,
            is_current=entry.expiration_date is None,
            tags=[],
            normalization_bundle=bundle,
        ),
        recency=RecencyMetadata(
            start_date=_normalize_date(entry.issue_date),
            end_date=_normalize_date(entry.expiration_date),
            is_current=entry.expiration_date is None,
        ),
        evidence_strength=entry.evidence_strength,
        verified_status=entry.verified_status,
        rewrite_allowed=entry.rewrite_allowed,
        provenance=EvidenceProvenance(
            source_section=EvidenceSection.CERTIFICATIONS,
            source_item_type=entry.item_type,
            source_parent_id=entry.id,
            source_parent_title=entry.name,
            source_links=entry.source_links,
            extraction_method="certification_entry",
            metric_ids=[],
        ),
        metric_ids=[],
    )


def _build_award_units(entry: AwardEntry) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []
    if entry.bullets:
        for index, bullet in enumerate(entry.bullets):
            bundle = normalize_evidence_text(bullet.text, title=entry.title)
            units.append(
                _make_evidence_unit(
                    evidence_id=f"evidence.{bullet.id}",
                    source_type=EvidenceSourceType.AWARD,
                    parent_link=EvidenceParentLink(
                        source_section=EvidenceSection.AWARDS,
                        source_parent_id=entry.id,
                        source_parent_type=entry.item_type,
                        source_child_id=bullet.id,
                        source_child_type=EvidenceChildType.BULLET,
                        source_child_index=index,
                    ),
                    canonical_text=_normalize_text(bullet.text),
                    raw_text=bullet.text,
                    normalized_skills=[term.canonical for term in _extract_known_skill_terms(bullet.text, *bullet.tools)],
                    normalized_tools=_merge_terms(
                        [term.canonical for term in normalize_tool_list(bullet.tools)],
                        _bundle_tool_terms(bundle),
                    ),
                    normalized_domains=_merge_terms(
                        entry.domain_tags,
                        entry.canonical_tags,
                        [term.canonical for term in bundle.domains_industries],
                    ),
                    signals=_build_signals(
                        raw_text=bullet.text,
                        role_values=[],
                        seniority_values=[],
                        metrics=bullet.metrics,
                        impact_score=bullet.impact_score,
                        is_current=False,
                        tags=[EvidenceTag(category=EvidenceTagCategory.SIGNAL, value="award")],
                        normalization_bundle=bundle,
                    ),
                    recency=RecencyMetadata(start_date=_normalize_date(entry.award_date)),
                    evidence_strength=bullet.evidence_strength,
                    verified_status=bullet.verified_status,
                    rewrite_allowed=bullet.rewrite_allowed,
                    provenance=EvidenceProvenance(
                        source_section=EvidenceSection.AWARDS,
                        source_item_type=entry.item_type,
                        source_parent_id=entry.id,
                        source_parent_title=entry.title,
                        source_organization=entry.awarder,
                        source_child_id=bullet.id,
                        source_child_type=EvidenceChildType.BULLET,
                        source_child_index=index,
                        source_links=bullet.source_links or entry.source_links,
                        extraction_method="award_bullet",
                        metric_ids=[metric.id for metric in bullet.metrics],
                    ),
                    metric_ids=[metric.id for metric in bullet.metrics],
                )
            )
        return units

    raw_text = entry.summary or entry.title
    bundle = normalize_evidence_text(raw_text, title=entry.title)
    units.append(
        _make_evidence_unit(
            evidence_id=f"evidence.{entry.id}",
            source_type=EvidenceSourceType.AWARD,
            parent_link=EvidenceParentLink(
                source_section=EvidenceSection.AWARDS,
                source_parent_id=entry.id,
                source_parent_type=entry.item_type,
            ),
            canonical_text=_normalize_text(raw_text),
            raw_text=raw_text,
            normalized_skills=[term.canonical for term in _extract_known_skill_terms(raw_text)],
            normalized_tools=_bundle_tool_terms(bundle),
            normalized_domains=_merge_terms(
                entry.domain_tags,
                entry.canonical_tags,
                [term.canonical for term in bundle.domains_industries],
            ),
            signals=_build_signals(
                raw_text=raw_text,
                role_values=[],
                seniority_values=[],
                metrics=[],
                impact_score=None,
                is_current=False,
                tags=[EvidenceTag(category=EvidenceTagCategory.SIGNAL, value="award")],
                normalization_bundle=bundle,
            ),
            recency=RecencyMetadata(start_date=_normalize_date(entry.award_date)),
            evidence_strength=entry.evidence_strength,
            verified_status=entry.verified_status,
            rewrite_allowed=entry.rewrite_allowed,
            provenance=EvidenceProvenance(
                source_section=EvidenceSection.AWARDS,
                source_item_type=entry.item_type,
                source_parent_id=entry.id,
                source_parent_title=entry.title,
                source_organization=entry.awarder,
                source_links=entry.source_links,
                extraction_method="award_summary",
                metric_ids=[],
            ),
            metric_ids=[],
        )
    )
    return units


def _build_verified_skill_unit(entry: SkillEntry) -> EvidenceUnit | None:
    if entry.verified_status == VerifiedStatus.UNVERIFIED and entry.evidence_strength.value == "weak":
        return None

    skill_terms = _extract_known_skill_terms(entry.name, *entry.tools)
    tags: list[EvidenceTag] = [EvidenceTag(category=EvidenceTagCategory.SKILL, value=entry.name)]
    if entry.verified_status == VerifiedStatus.SELF_REPORTED:
        tags.append(EvidenceTag(category=EvidenceTagCategory.WARNING, value=WeakEvidenceTag.UNSUPPORTED_SKILL_MENTION.value))
    bundle = normalize_evidence_text(entry.name, title=entry.name)

    return _make_evidence_unit(
        evidence_id=f"evidence.{entry.id}",
        source_type=EvidenceSourceType.SKILL_DECLARATION,
        parent_link=EvidenceParentLink(
            source_section=EvidenceSection.SKILLS,
            source_parent_id=entry.id,
            source_parent_type=entry.item_type,
        ),
        canonical_text=_normalize_text(entry.name),
        raw_text=entry.name,
        normalized_skills=[term.canonical for term in skill_terms],
        normalized_tools=_merge_terms(
            [term.canonical for term in normalize_tool_list(entry.tools)],
            _bundle_tool_terms(bundle),
        ),
        normalized_domains=_merge_terms(entry.domain_tags, [entry.category], entry.canonical_tags, [term.canonical for term in bundle.domains_industries]),
        signals=_build_signals(
            raw_text=entry.name,
            role_values=[entry.role_type.value if entry.role_type else None],
            seniority_values=[entry.seniority_level.value if entry.seniority_level else None],
            metrics=entry.metrics,
            impact_score=None,
            is_current=False,
            tags=tags,
            normalization_bundle=bundle,
        ),
        recency=RecencyMetadata(source_recency_score=entry.recency_score),
        evidence_strength=entry.evidence_strength,
        verified_status=entry.verified_status,
        rewrite_allowed=entry.rewrite_allowed,
        provenance=EvidenceProvenance(
            source_section=EvidenceSection.SKILLS,
            source_item_type=entry.item_type,
            source_parent_id=entry.id,
            source_parent_title=entry.name,
            source_links=entry.source_links,
            extraction_method="verified_skill_entry",
            metric_ids=[metric.id for metric in entry.metrics],
        ),
        metric_ids=[metric.id for metric in entry.metrics],
    )


def _make_bullet_unit(
    *,
    source_section: EvidenceSection,
    parent_id: str,
    parent_type,
    child_id: str,
    child_index: int,
    source_type: EvidenceSourceType,
    raw_text: str,
    canonical_text: str,
    entity_title: str,
    entity_org: str | None,
    parent_tools: list[str],
    parent_domain_tags: list[str],
    parent_canonical_tags: list[str],
    parent_role_value: str | None,
    parent_seniority_value: str | None,
    metrics: list[MetricEntry],
    bullet_metrics: list[MetricEntry],
    item_evidence_strength,
    item_verified_status,
    rewrite_allowed: bool,
    source_links,
    recency: RecencyMetadata,
    tools: list[str],
    impact_score: float | None,
    extraction_method: str,
) -> EvidenceUnit:
    bundle = normalize_evidence_text(raw_text, title=entity_title)
    normalized_skills = _extract_known_skill_terms(raw_text, *tools)
    weak_tags = _weak_tags_for_text(raw_text, has_supporting_detail=bool(tools or bullet_metrics))
    if normalized_skills and not bullet_metrics and not tools:
        weak_tags.append(WeakEvidenceTag.UNSUPPORTED_SKILL_MENTION)
    tags: list[EvidenceTag] = []
    if normalized_skills:
        tags.extend(EvidenceTag(category=EvidenceTagCategory.SKILL, value=term.canonical) for term in normalized_skills)
    return _make_evidence_unit(
        evidence_id=f"evidence.{child_id}",
        source_type=source_type,
        parent_link=EvidenceParentLink(
            source_section=source_section,
            source_parent_id=parent_id,
            source_parent_type=parent_type,
            source_child_id=child_id,
            source_child_type=EvidenceChildType.BULLET,
            source_child_index=child_index,
        ),
        canonical_text=canonical_text,
        raw_text=raw_text,
        normalized_skills=[term.canonical for term in normalized_skills],
        normalized_tools=_merge_terms(
            [term.canonical for term in normalize_tool_list(tools)],
            _bundle_tool_terms(bundle),
        ),
        normalized_domains=_merge_terms(
            parent_domain_tags,
            parent_canonical_tags,
            [term.canonical for term in bundle.domains_industries],
        ),
        signals=_build_signals(
            raw_text=raw_text,
            role_values=[parent_role_value, normalize_title_taxonomy(entity_title).role_type_hint, entity_title],
            seniority_values=[parent_seniority_value, normalize_title_taxonomy(entity_title).seniority_hint, entity_title],
            metrics=metrics,
            impact_score=impact_score,
            is_current=recency.is_current,
            tags=tags,
            normalization_bundle=bundle,
        ),
        recency=recency,
        evidence_strength=item_evidence_strength,
        verified_status=item_verified_status,
        rewrite_allowed=rewrite_allowed,
        provenance=EvidenceProvenance(
            source_section=source_section,
            source_item_type=parent_type,
            source_parent_id=parent_id,
            source_parent_title=entity_title,
            source_organization=entity_org,
            source_child_id=child_id,
            source_child_type=EvidenceChildType.BULLET,
            source_child_index=child_index,
            source_links=source_links,
            extraction_method=extraction_method,
            metric_ids=[metric.id for metric in bullet_metrics],
        ),
        metric_ids=[metric.id for metric in bullet_metrics],
        weak_tags=_dedupe_weak_tags(weak_tags),
    )


def _make_evidence_unit(
    *,
    evidence_id: str,
    source_type: EvidenceSourceType,
    parent_link: EvidenceParentLink,
    canonical_text: str,
    raw_text: str,
    normalized_skills: list[str],
    normalized_tools: list[str],
    normalized_domains: list[str],
    signals: EvidenceSignals,
    recency: RecencyMetadata,
    evidence_strength,
    verified_status,
    rewrite_allowed: bool,
    provenance: EvidenceProvenance,
    metric_ids: list[str],
    weak_tags: list[WeakEvidenceTag] | None = None,
) -> EvidenceUnit:
    dedupe_fingerprint = _dedupe_signature(canonical_text)
    quality = _build_quality(
        canonical_text,
        normalized_tools=normalized_tools,
        metric_ids=metric_ids,
        weak_tags=weak_tags or _weak_tags_for_text(raw_text, has_supporting_detail=bool(normalized_tools or metric_ids)),
    )
    rewrite_safety = _build_rewrite_safety(
        rewrite_allowed=rewrite_allowed,
        metric_ids=metric_ids,
        verified_status=verified_status,
    )
    coverage = EvidenceCoverage(
        source_item_count=1,
        source_child_count=1 if parent_link.source_child_id is not None else 0,
        source_metric_count=len(metric_ids),
        source_link_count=len(provenance.source_links),
        multi_source_support=bool(provenance.source_links) and len(provenance.source_links) > 1,
    )
    unit = EvidenceUnit(
        evidence_id=evidence_id,
        source_type=source_type,
        parent_link=parent_link,
        canonical_text=_normalize_text(canonical_text),
        raw_text=_normalize_text(raw_text),
        normalized_skills=_merge_terms(normalized_skills),
        normalized_tools=_merge_terms(normalized_tools),
        normalized_domains=_merge_terms(normalized_domains),
        signals=signals,
        quality=quality,
        rewrite_safety=rewrite_safety,
        coverage=coverage,
        recency=recency,
        evidence_strength=evidence_strength,
        verified_status=verified_status,
        dedupe_fingerprint=dedupe_fingerprint,
        provenance=provenance,
    )
    from .services.evidence_enrichment_service import DEFAULT_EVIDENCE_ENRICHMENT_SERVICE
    from .services.evidence_quality_service import DEFAULT_EVIDENCE_QUALITY_SERVICE

    enriched = DEFAULT_EVIDENCE_ENRICHMENT_SERVICE.enrich(unit)
    return DEFAULT_EVIDENCE_QUALITY_SERVICE.score(enriched)


def _build_signals(
    *,
    raw_text: str,
    role_values: list[str | None],
    seniority_values: list[str | None],
    metrics: list[MetricEntry],
    impact_score: float | None,
    is_current: bool,
    tags: list[EvidenceTag],
    normalization_bundle=None,
) -> EvidenceSignals:
    impact_types = _infer_impact_types(raw_text, metrics)
    signal_tokens: list[str] = []
    if metrics:
        signal_tokens.append("metrics_present")
    if impact_score is not None and impact_score >= 0.7:
        signal_tokens.append("high_impact_score")
    if is_current:
        signal_tokens.append("current_scope")
    leadership_signals = _infer_leadership_signals(raw_text, normalization_bundle=normalization_bundle)
    if leadership_signals:
        signal_tokens.append("leadership_signal")
    if normalization_bundle is not None:
        signal_tokens.extend(term.canonical for term in normalization_bundle.action_verbs)
        signal_tokens.extend(term.canonical for term in normalization_bundle.stakeholder_phrases)
    return EvidenceSignals(
        ownership_level=_infer_ownership_level(raw_text, normalization_bundle=normalization_bundle),
        leadership_signals=leadership_signals,
        delivery_scope=_infer_delivery_scope(raw_text, normalization_bundle=normalization_bundle),
        impact_types=impact_types,
        impact_metrics_present=bool(metrics),
        role_family_hints=_collect_role_types(*role_values),
        business_outcome_hints=_infer_business_outcome_hints(raw_text),
        seniority_signals=_collect_seniority(*seniority_values),
        signal_tokens=_merge_terms(signal_tokens),
        tags=tags,
    )


def _build_quality(
    raw_text: str,
    *,
    normalized_tools: list[str],
    metric_ids: list[str],
    weak_tags: list[WeakEvidenceTag],
) -> EvidenceQuality:
    token_count = len(_TOKEN_PATTERN.findall(raw_text))
    has_detail = bool(normalized_tools or metric_ids or any(char.isdigit() for char in raw_text))
    clarity = 0.9 if token_count >= 12 and has_detail else 0.7 if token_count >= 8 else 0.45
    specificity = 0.9 if has_detail else 0.55 if token_count >= 8 else 0.35
    return EvidenceQuality(
        clarity_score=round(clarity, 4),
        specificity_score=round(specificity, 4),
        weak_evidence_tags=_dedupe_weak_tags(weak_tags),
    )


def _build_rewrite_safety(
    *,
    rewrite_allowed: bool,
    metric_ids: list[str],
    verified_status,
) -> EvidenceRewriteSafety:
    preserve_metrics = bool(metric_ids)
    preserve_named_entities = preserve_metrics or verified_status.value in {"corroborated", "verified"}
    if not rewrite_allowed:
        level = RewriteSafetyLevel.RESTRICTED
    elif preserve_metrics or preserve_named_entities:
        level = RewriteSafetyLevel.CAUTION
    else:
        level = RewriteSafetyLevel.SAFE
    return EvidenceRewriteSafety(
        level=level,
        rewrite_allowed=rewrite_allowed,
        paraphrase_safe=rewrite_allowed,
        merge_safe=rewrite_allowed and not preserve_metrics,
        preserve_metrics=preserve_metrics,
        preserve_named_entities=preserve_named_entities,
    )


def _weak_tags_for_text(raw_text: str, *, has_supporting_detail: bool) -> list[WeakEvidenceTag]:
    tags: list[WeakEvidenceTag] = []
    token_count = len(_TOKEN_PATTERN.findall(raw_text))
    if token_count < 6 or not has_supporting_detail:
        tags.append(WeakEvidenceTag.LOW_INFORMATION)
    if any(pattern.search(raw_text) for pattern in _VAGUE_PATTERNS):
        tags.append(WeakEvidenceTag.VAGUE)
    return _dedupe_weak_tags(tags)


def _infer_ownership_level(raw_text: str, *, normalization_bundle=None) -> OwnershipLevel:
    if normalization_bundle is not None and normalization_bundle.ownership_phrases:
        canonical_values = {term.canonical for term in normalization_bundle.ownership_phrases}
        if "ownership" in canonical_values:
            return OwnershipLevel.OWNER
        if "execution_drive" in canonical_values:
            return OwnershipLevel.DRIVER
        if "operational_responsibility" in canonical_values:
            return OwnershipLevel.CONTRIBUTOR
    if any(pattern.search(raw_text) for pattern in _OWNERSHIP_OWNER_PATTERNS):
        return OwnershipLevel.OWNER
    if any(pattern.search(raw_text) for pattern in _OWNERSHIP_DRIVER_PATTERNS):
        return OwnershipLevel.DRIVER
    return OwnershipLevel.CONTRIBUTOR


def _infer_leadership_signals(raw_text: str, *, normalization_bundle=None) -> list[LeadershipSignal]:
    if normalization_bundle is not None and normalization_bundle.leadership_phrases:
        mapping = {
            "technical_leadership": LeadershipSignal.TECHNICAL_LEADERSHIP,
            "people_management": LeadershipSignal.PEOPLE_MANAGEMENT,
            "mentorship": LeadershipSignal.MENTORSHIP,
            "cross_functional_leadership": LeadershipSignal.CROSS_FUNCTIONAL_LEADERSHIP,
        }
        values = [
            mapping[term.canonical]
            for term in normalization_bundle.leadership_phrases
            if term.canonical in mapping
        ]
        if values:
            return _dedupe_leadership_signals(values)
    return [signal for signal, pattern in _LEADERSHIP_SIGNAL_PATTERNS if pattern.search(raw_text)]


def _infer_delivery_scope(raw_text: str, *, normalization_bundle=None) -> DeliveryScope:
    if normalization_bundle is not None and normalization_bundle.delivery_scope_phrases:
        mapping = {
            "feature_scope": DeliveryScope.FEATURE,
            "system_scope": DeliveryScope.SYSTEM,
            "platform_scope": DeliveryScope.PLATFORM,
            "product_scope": DeliveryScope.PRODUCT,
            "organizational_scope": DeliveryScope.ORGANIZATION,
            "company_scope": DeliveryScope.COMPANY,
        }
        for term in normalization_bundle.delivery_scope_phrases:
            if term.canonical in mapping:
                return mapping[term.canonical]
    for scope, pattern in _DELIVERY_SCOPE_PATTERNS:
        if pattern.search(raw_text):
            return scope
    return DeliveryScope.TASK


def _infer_impact_types(raw_text: str, metrics: list[MetricEntry]) -> list[ImpactType]:
    matches = [impact_type for impact_type, pattern in _IMPACT_PATTERNS if pattern.search(raw_text)]
    if metrics and ImpactType.DELIVERY not in matches:
        matches.append(ImpactType.DELIVERY)
    if not matches:
        matches.append(ImpactType.NONE)
    return matches


def _infer_business_outcome_hints(raw_text: str) -> list[str]:
    return [value for value, pattern in _BUSINESS_OUTCOME_HINT_PATTERNS if pattern.search(raw_text)]


def _bundle_tool_terms(bundle) -> list[str]:
    return _merge_terms(
        [term.canonical for term in bundle.tool_platforms],
        [term.canonical for term in bundle.cloud_services],
        [term.canonical for term in bundle.frameworks_libraries],
        [term.canonical for term in bundle.programming_languages],
    )


def _dedupe_leadership_signals(values: list[LeadershipSignal]) -> list[LeadershipSignal]:
    deduped: list[LeadershipSignal] = []
    seen: set[LeadershipSignal] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _collect_role_types(*values: str | None) -> list[str]:
    role_types: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        normalized = normalize_role_taxonomy(value)
        canonical = normalized.canonical
        if canonical in seen or normalized.status.value == "passthrough":
            continue
        seen.add(canonical)
        role_types.append(canonical)
    return role_types


def _collect_seniority(*values: str | None) -> list[str]:
    seniority: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        normalized = normalize_seniority_taxonomy(value)
        canonical = normalized.canonical
        if canonical in seen or normalized.status.value == "passthrough":
            continue
        seen.add(canonical)
        seniority.append(canonical)
    return seniority


def _merge_terms(*groups: list[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            cleaned = _normalize_text(value).casefold()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            values.append(cleaned)
    return values


def _extract_known_skill_terms(*values: str) -> list:
    candidates: list[str] = []
    for value in values:
        if not value:
            continue
        candidates.append(value)
        candidates.extend(_candidate_terms_from_text(value))
    terms = normalize_skill_list(candidates)
    return [term for term in terms if term.status.value != "passthrough"]


def _candidate_terms_from_text(value: str) -> list[str]:
    lowered_tokens = [token.casefold() for token in _TOKEN_PATTERN.findall(value)]
    candidates = list(lowered_tokens)
    for ngram_size in range(2, min(4, len(lowered_tokens)) + 1):
        for index in range(0, len(lowered_tokens) - ngram_size + 1):
            candidates.append(" ".join(lowered_tokens[index : index + ngram_size]))
    return candidates


def _dedupe_weak_tags(values: list[WeakEvidenceTag]) -> list[WeakEvidenceTag]:
    deduped: list[WeakEvidenceTag] = []
    seen: set[WeakEvidenceTag] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _normalize_date(value: PartialDate | None) -> str | None:
    if value is None:
        return None
    return value.normalized_value or value.raw_value


def _dedupe_signature(value: str) -> str:
    normalized = _normalize_text(value).casefold()
    digest = sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"dedupe.{digest}"


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()
