"""Deterministic candidate-level evidence coverage aggregation for Phase 2."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from ..evidence_models import (
    CandidateEvidenceCoverageMap,
    CandidateEvidenceGraph,
    CoverageBand,
    CoverageDimension,
    CoverageGap,
    CoverageHighlight,
    EvidenceQualityBand,
    EvidenceSourceType,
    EvidenceUnit,
    RoleSpecialty,
)

_ROLE_SPECIALTY_LABELS = {
    RoleSpecialty.ARCHITECTURE: "architecture",
    RoleSpecialty.BACKEND: "backend",
    RoleSpecialty.FRONTEND: "frontend",
    RoleSpecialty.FULLSTACK: "fullstack",
    RoleSpecialty.DATA: "data",
    RoleSpecialty.DEVOPS: "devops",
    RoleSpecialty.ML: "ml",
    RoleSpecialty.MOBILE: "mobile",
    RoleSpecialty.PRODUCT: "product",
    RoleSpecialty.DESIGN: "design",
}
_CLOUD_PLATFORM_TERMS = {
    "aws",
    "gcp",
    "google-cloud-platform",
    "azure",
    "kubernetes",
    "docker",
    "terraform",
    "helm",
    "platform",
    "infrastructure",
    "ci/cd",
}
_ANALYTICS_TERMS = {
    "analytics",
    "experimentation",
    "data",
    "postgresql",
    "postgres",
    "sql",
    "bigquery",
    "snowflake",
    "airflow",
}
_TECHNICAL_CLUSTER_RULES = {
    "backend": {"backend", "python", "java", "golang", "go", "node.js", "api", "service"},
    "frontend": {"frontend", "react", "typescript", "javascript", "next.js", "css", "html"},
    "data": {"data", "sql", "postgresql", "postgres", "spark", "airflow", "warehouse", "analytics"},
    "cloud_platform": _CLOUD_PLATFORM_TERMS,
    "devops": {"devops", "kubernetes", "docker", "terraform", "ci/cd", "infrastructure"},
    "ml": {"ml", "machine-learning", "tensorflow", "pytorch", "llm", "ai"},
    "mobile": {"mobile", "ios", "android", "react-native"},
}


@dataclass(frozen=True)
class _FacetContribution:
    unit: EvidenceUnit
    weight: float
    signals: tuple[str, ...]


class CandidateEvidenceCoverageMapService:
    """Aggregate candidate-level strengths and weak zones from the evidence graph."""

    def build(self, graph: CandidateEvidenceGraph) -> CandidateEvidenceCoverageMap:
        primary_units = [unit for unit in graph.evidence_units if unit.duplicate_of is None]
        weak_units = [unit for unit in primary_units if unit.quality.omit_risk]
        declared_skills = [unit for unit in graph.evidence_units if unit.source_type == EvidenceSourceType.SKILL_DECLARATION]

        role_family_strengths = self._role_family_strengths(primary_units)
        domain_strengths = self._domain_strengths(primary_units)
        core_technical_clusters = self._technical_clusters(primary_units)

        leadership_depth = self._facet(
            "leadership_depth",
            [
                _FacetContribution(
                    unit=unit,
                    weight=self._quality(unit) * max(unit.enrichment.leadership_score or 0.0, unit.enrichment.mentoring_score or 0.0),
                    signals=tuple(signal.value for signal in unit.signals.leadership_signals),
                )
                for unit in primary_units
                if max(unit.enrichment.leadership_score or 0.0, unit.enrichment.mentoring_score or 0.0) >= 0.35
            ],
        )
        ownership_depth = self._facet(
            "ownership_depth",
            [
                _FacetContribution(
                    unit=unit,
                    weight=self._quality(unit) * (unit.enrichment.ownership_score or 0.0),
                    signals=(unit.signals.ownership_level.value,),
                )
                for unit in primary_units
                if (unit.enrichment.ownership_score or 0.0) >= 0.35
            ],
        )
        architecture_strength = self._facet(
            "architecture_system_design",
            [
                _FacetContribution(
                    unit=unit,
                    weight=self._quality(unit) * (unit.enrichment.architecture_system_design_score or 0.0),
                    signals=("architecture_system_design",),
                )
                for unit in primary_units
                if (unit.enrichment.architecture_system_design_score or 0.0) >= 0.4
            ],
        )
        delivery_execution = self._facet(
            "delivery_execution",
            [
                _FacetContribution(
                    unit=unit,
                    weight=self._quality(unit) * (unit.enrichment.delivery_execution_score or 0.0),
                    signals=(unit.signals.delivery_scope.value,),
                )
                for unit in primary_units
                if (unit.enrichment.delivery_execution_score or 0.0) >= 0.35
            ],
        )
        cloud_platform_strength = self._facet(
            "cloud_platform_strength",
            [
                _FacetContribution(
                    unit=unit,
                    weight=self._quality(unit)
                    * max(
                        unit.enrichment.internal_platform_score or 0.0,
                        0.7 if _contains_any(unit, _CLOUD_PLATFORM_TERMS) else 0.0,
                    ),
                    signals=tuple(sorted(set(unit.normalized_tools) & _CLOUD_PLATFORM_TERMS)),
                )
                for unit in primary_units
                if (unit.enrichment.internal_platform_score or 0.0) >= 0.45 or _contains_any(unit, _CLOUD_PLATFORM_TERMS)
            ],
        )
        product_stakeholder_strength = self._facet(
            "product_stakeholder_strength",
            [
                _FacetContribution(
                    unit=unit,
                    weight=self._quality(unit)
                    * max(
                        unit.enrichment.stakeholder_management_score or 0.0,
                        unit.enrichment.customer_facing_score or 0.0,
                    ),
                    signals=tuple(
                        signal
                        for signal in [
                            "stakeholder_management" if (unit.enrichment.stakeholder_management_score or 0.0) > 0 else "",
                            "customer_facing" if (unit.enrichment.customer_facing_score or 0.0) > 0 else "",
                        ]
                        if signal
                    ),
                )
                for unit in primary_units
                if max(unit.enrichment.stakeholder_management_score or 0.0, unit.enrichment.customer_facing_score or 0.0) >= 0.35
            ],
        )
        experimentation_analytics_strength = self._facet(
            "experimentation_analytics_strength",
            [
                _FacetContribution(
                    unit=unit,
                    weight=self._quality(unit)
                    * max(
                        unit.enrichment.experimentation_score or 0.0,
                        0.55 if _contains_any(unit, _ANALYTICS_TERMS) else 0.0,
                    ),
                    signals=tuple(sorted((set(unit.normalized_tools) | set(unit.normalized_domains)) & _ANALYTICS_TERMS)),
                )
                for unit in primary_units
                if (unit.enrichment.experimentation_score or 0.0) >= 0.35 or _contains_any(unit, _ANALYTICS_TERMS)
            ],
        )
        certifications_strength = self._facet(
            "certifications_strength",
            [
                _FacetContribution(
                    unit=unit,
                    weight=self._quality(unit) * 0.9,
                    signals=("certification",),
                )
                for unit in primary_units
                if unit.source_type == EvidenceSourceType.CERTIFICATION
            ],
        )
        awards_strength = self._facet(
            "awards_distinction_strength",
            [
                _FacetContribution(
                    unit=unit,
                    weight=self._quality(unit) * 0.95,
                    signals=("award",),
                )
                for unit in primary_units
                if unit.source_type == EvidenceSourceType.AWARD
            ],
        )

        weak_zones = self._weak_zones(
            primary_units=primary_units,
            declared_skills=declared_skills,
            dimensions=[
                leadership_depth,
                ownership_depth,
                architecture_strength,
                delivery_execution,
                cloud_platform_strength,
                product_stakeholder_strength,
                experimentation_analytics_strength,
                certifications_strength,
                awards_strength,
            ],
        )
        strengths = self._high_level_strengths(
            role_family_strengths=role_family_strengths,
            domain_strengths=domain_strengths,
            core_technical_clusters=core_technical_clusters,
            dimensions=[
                leadership_depth,
                ownership_depth,
                architecture_strength,
                delivery_execution,
                cloud_platform_strength,
                product_stakeholder_strength,
                experimentation_analytics_strength,
                certifications_strength,
                awards_strength,
            ],
        )

        return CandidateEvidenceCoverageMap(
            candidate_profile_id=graph.candidate_profile_id,
            total_evidence_units=len(graph.evidence_units),
            primary_evidence_units=len(primary_units),
            suppressed_repeat_units=len([unit for unit in graph.evidence_units if unit.duplicate_of is not None]),
            weak_evidence_units=len(weak_units),
            declared_skill_units=len(declared_skills),
            role_family_strengths=role_family_strengths,
            leadership_depth=leadership_depth,
            ownership_depth=ownership_depth,
            architecture_system_design_strength=architecture_strength,
            delivery_execution_strength=delivery_execution,
            domain_strengths=domain_strengths,
            core_technical_clusters=core_technical_clusters,
            cloud_platform_strength=cloud_platform_strength,
            product_stakeholder_strength=product_stakeholder_strength,
            experimentation_analytics_strength=experimentation_analytics_strength,
            certifications_strength=certifications_strength,
            awards_distinction_strength=awards_strength,
            sparsity_weak_zones=weak_zones,
            high_level_strengths=strengths,
            weak_match_flags=weak_zones[:5],
        )

    def _role_family_strengths(self, primary_units: list[EvidenceUnit]) -> list[CoverageDimension]:
        contributions: dict[str, list[_FacetContribution]] = defaultdict(list)
        for unit in primary_units:
            for specialty in unit.enrichment.role_specialties:
                label = _ROLE_SPECIALTY_LABELS[specialty]
                specialty_score = max(
                    unit.enrichment.architecture_system_design_score or 0.0 if specialty == RoleSpecialty.ARCHITECTURE else 0.0,
                    unit.enrichment.delivery_execution_score or 0.0,
                    unit.enrichment.internal_platform_score or 0.0 if specialty in {RoleSpecialty.DEVOPS, RoleSpecialty.BACKEND, RoleSpecialty.ARCHITECTURE} else 0.0,
                    0.55,
                )
                contributions[label].append(
                    _FacetContribution(
                        unit=unit,
                        weight=self._quality(unit) * specialty_score,
                        signals=(label,),
                    )
                )
        return self._sorted_dimensions(contributions)

    def _domain_strengths(self, primary_units: list[EvidenceUnit]) -> list[CoverageDimension]:
        contributions: dict[str, list[_FacetContribution]] = defaultdict(list)
        for unit in primary_units:
            for domain in unit.normalized_domains:
                contributions[domain].append(
                    _FacetContribution(
                        unit=unit,
                        weight=self._quality(unit)
                        * max(unit.enrichment.domain_specificity_score or 0.0, 0.45),
                        signals=(domain,),
                    )
                )
        return self._sorted_dimensions(contributions, limit=6)

    def _technical_clusters(self, primary_units: list[EvidenceUnit]) -> list[CoverageDimension]:
        contributions: dict[str, list[_FacetContribution]] = defaultdict(list)
        for unit in primary_units:
            tokens = set(unit.normalized_tools) | set(unit.normalized_skills) | set(unit.normalized_domains)
            for cluster, rule_terms in _TECHNICAL_CLUSTER_RULES.items():
                overlap = sorted(tokens & rule_terms)
                if not overlap:
                    continue
                contributions[cluster].append(
                    _FacetContribution(
                        unit=unit,
                        weight=self._quality(unit) * min(0.95, 0.45 + 0.12 * len(overlap)),
                        signals=tuple(overlap[:4]),
                    )
                )
        return self._sorted_dimensions(contributions, limit=6)

    def _sorted_dimensions(
        self,
        contributions: dict[str, list[_FacetContribution]],
        *,
        limit: int = 5,
    ) -> list[CoverageDimension]:
        dimensions = [self._facet(area, items) for area, items in contributions.items()]
        filtered = [dimension for dimension in dimensions if dimension.evidence_count > 0]
        return sorted(filtered, key=lambda item: (-item.score, -item.strong_evidence_count, item.area))[:limit]

    def _facet(self, area: str, contributions: list[_FacetContribution]) -> CoverageDimension:
        ranked = sorted(
            contributions,
            key=lambda item: (-item.weight, -(item.unit.quality.overall_quality_score or 0.0), item.unit.evidence_id),
        )
        evidence_ids = [item.unit.evidence_id for item in ranked[:5]]
        quality_weighted = round(sum(item.weight for item in ranked), 4)
        score = self._facet_score(ranked)
        rationale_counts = Counter(signal for item in ranked[:5] for signal in item.signals if signal)
        return CoverageDimension(
            area=area,
            score=score,
            band=_coverage_band(score, evidence_count=len(ranked)),
            evidence_count=len(ranked),
            strong_evidence_count=sum(
                1
                for item in ranked
                if item.unit.quality.quality_band in {EvidenceQualityBand.STRONG, EvidenceQualityBand.MEDIUM}
            ),
            quality_weighted_evidence=min(1.0, quality_weighted),
            evidence_ids=evidence_ids,
            rationale_signals=[signal for signal, _ in rationale_counts.most_common(4)],
        )

    def _facet_score(self, contributions: list[_FacetContribution]) -> float:
        if not contributions:
            return 0.0
        top_weights = [item.weight for item in contributions[:3]]
        avg_top = sum(top_weights) / len(top_weights)
        count_bonus = min(0.25, 0.06 * len(contributions))
        strong_bonus = min(
            0.15,
            0.05
            * sum(
                1
                for item in contributions[:4]
                if item.unit.quality.quality_band in {EvidenceQualityBand.STRONG, EvidenceQualityBand.MEDIUM}
            ),
        )
        return round(min(1.0, avg_top + count_bonus + strong_bonus), 4)

    def _quality(self, unit: EvidenceUnit) -> float:
        return float(unit.quality.overall_quality_score or unit.quality.specificity_score or 0.35)

    def _weak_zones(
        self,
        *,
        primary_units: list[EvidenceUnit],
        declared_skills: list[EvidenceUnit],
        dimensions: list[CoverageDimension],
    ) -> list[CoverageGap]:
        gaps: list[CoverageGap] = []
        for dimension in dimensions:
            if dimension.band in {CoverageBand.EMERGING, CoverageBand.SPARSE}:
                reason = "No meaningful supporting evidence yet." if dimension.evidence_count == 0 else "Coverage exists but remains shallow or weakly supported."
                gaps.append(
                    CoverageGap(
                        area=dimension.area,
                        band=dimension.band,
                        reason=reason,
                        related_evidence_ids=dimension.evidence_ids[:3],
                    )
                )

        strong_skill_terms = {
            skill
            for unit in primary_units
            if unit.source_type != EvidenceSourceType.SKILL_DECLARATION and not unit.quality.omit_risk
            for skill in unit.normalized_skills
        }
        declared_only = sorted(
            {
                skill
                for unit in declared_skills
                for skill in unit.normalized_skills
                if skill not in strong_skill_terms
            }
        )
        if declared_only:
            gaps.append(
                CoverageGap(
                    area="declared_skill_support_gap",
                    band=CoverageBand.EMERGING if len(declared_only) <= 2 else CoverageBand.SPARSE,
                    reason=f"Declared skills outnumber evidence-backed skills for {', '.join(declared_only[:4])}.",
                    related_evidence_ids=[unit.evidence_id for unit in declared_skills[:4]],
                )
            )

        if len(primary_units) <= 5 or len([unit for unit in primary_units if not unit.quality.omit_risk]) <= 3:
            gaps.append(
                CoverageGap(
                    area="overall_evidence_sparsity",
                    band=CoverageBand.SPARSE,
                    reason="The candidate profile has very few primary evidence units to support broad strategy coverage.",
                    related_evidence_ids=[unit.evidence_id for unit in primary_units],
                )
            )
        return sorted(gaps, key=lambda item: (item.band.value, item.area))

    def _high_level_strengths(
        self,
        *,
        role_family_strengths: list[CoverageDimension],
        domain_strengths: list[CoverageDimension],
        core_technical_clusters: list[CoverageDimension],
        dimensions: list[CoverageDimension],
    ) -> list[CoverageHighlight]:
        highlights: list[CoverageHighlight] = []
        for dimension in [*role_family_strengths[:3], *domain_strengths[:2], *core_technical_clusters[:2], *dimensions]:
            if dimension.band not in {CoverageBand.STRONG, CoverageBand.MODERATE}:
                continue
            descriptor = "strong" if dimension.band == CoverageBand.STRONG else "credible"
            highlights.append(
                CoverageHighlight(
                    area=dimension.area,
                    score=dimension.score,
                    band=dimension.band,
                    summary=f"{descriptor} {dimension.area.replace('_', ' ')} coverage backed by {dimension.evidence_count} evidence units.",
                    evidence_ids=dimension.evidence_ids[:3],
                )
            )
        unique = {highlight.area: highlight for highlight in highlights}
        return sorted(unique.values(), key=lambda item: (-item.score, item.area))[:8]


def _contains_any(unit: EvidenceUnit, terms: set[str]) -> bool:
    return bool((set(unit.normalized_tools) | set(unit.normalized_domains) | set(unit.normalized_skills)) & terms)


def _coverage_band(score: float, *, evidence_count: int) -> CoverageBand:
    if score >= 0.75 and evidence_count >= 2:
        return CoverageBand.STRONG
    if score >= 0.55 and evidence_count >= 1:
        return CoverageBand.MODERATE
    if score >= 0.3 and evidence_count >= 1:
        return CoverageBand.EMERGING
    return CoverageBand.SPARSE


DEFAULT_CANDIDATE_EVIDENCE_COVERAGE_MAP_SERVICE = CandidateEvidenceCoverageMapService()
