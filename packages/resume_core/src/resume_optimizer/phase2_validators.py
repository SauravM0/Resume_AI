"""Phase 2 integrity validators for evidence graphs, coverage maps, and artifacts."""

from __future__ import annotations

from collections import Counter, defaultdict

from pydantic import Field

from .evidence_builder import build_candidate_evidence_graph
from .evidence_models import (
    CandidateEvidenceCoverageMap,
    CandidateEvidenceGraph,
    CoverageDimension,
    CoverageGap,
    EvidenceRelationshipType,
    EvidenceSourceType,
    EvidenceUnit,
)
from .models import MasterProfile, NonEmptyStr, StableId, StrictModel


class Phase2ValidationIssue(StrictModel):
    code: NonEmptyStr
    message: NonEmptyStr
    severity: NonEmptyStr = "error"
    evidence_id: StableId | None = None
    related_id: StableId | None = None


class Phase2ValidationReport(StrictModel):
    issues: list[Phase2ValidationIssue] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues


def validate_phase2_graph(
    graph: CandidateEvidenceGraph,
    *,
    source_profile: MasterProfile | None = None,
) -> Phase2ValidationReport:
    issues: list[Phase2ValidationIssue] = []
    evidence_by_id = {unit.evidence_id: unit for unit in graph.evidence_units}

    issues.extend(_validate_graph_identity(graph, evidence_by_id))
    issues.extend(_validate_parent_child_consistency(graph, evidence_by_id, source_profile))
    issues.extend(_validate_normalization_integrity(graph.evidence_units))
    issues.extend(_validate_dedupe_metadata(graph, evidence_by_id))
    return Phase2ValidationReport(issues=issues)


def validate_phase2_stable_ids(source_profile: MasterProfile) -> Phase2ValidationReport:
    first = build_candidate_evidence_graph(source_profile)
    second = build_candidate_evidence_graph(source_profile)

    issues: list[Phase2ValidationIssue] = []
    first_ids = [unit.evidence_id for unit in first.evidence_units]
    second_ids = [unit.evidence_id for unit in second.evidence_units]
    if first_ids != second_ids:
        issues.append(
            Phase2ValidationIssue(
                code="stable_ids_changed",
                message="Evidence IDs changed across repeated graph builds for the same source profile.",
            )
        )

    for left, right in zip(first.evidence_units, second.evidence_units, strict=True):
        if left.parent_link != right.parent_link:
            issues.append(
                Phase2ValidationIssue(
                    code="parent_link_changed",
                    message="Parent-child linkage changed across repeated graph builds.",
                    evidence_id=left.evidence_id,
                )
            )
        if left.dedupe_fingerprint != right.dedupe_fingerprint:
            issues.append(
                Phase2ValidationIssue(
                    code="dedupe_fingerprint_changed",
                    message="Dedupe fingerprint changed across repeated graph builds.",
                    evidence_id=left.evidence_id,
                )
            )
        if left.duplicate_of != right.duplicate_of:
            issues.append(
                Phase2ValidationIssue(
                    code="duplicate_marker_changed",
                    message="Duplicate marker changed across repeated graph builds.",
                    evidence_id=left.evidence_id,
                )
            )

    return Phase2ValidationReport(issues=issues)


def validate_candidate_coverage_map(
    graph: CandidateEvidenceGraph,
    coverage_map: CandidateEvidenceCoverageMap,
) -> Phase2ValidationReport:
    issues: list[Phase2ValidationIssue] = []
    evidence_ids = {unit.evidence_id for unit in graph.evidence_units}
    primary_ids = {unit.evidence_id for unit in graph.evidence_units if unit.duplicate_of is None}
    duplicate_ids = {unit.evidence_id for unit in graph.evidence_units if unit.duplicate_of is not None}

    if coverage_map.candidate_profile_id != graph.candidate_profile_id:
        issues.append(
            Phase2ValidationIssue(
                code="coverage_profile_id_mismatch",
                message="Coverage map candidate_profile_id must match evidence graph candidate_profile_id.",
            )
        )
    if coverage_map.total_evidence_units != len(graph.evidence_units):
        issues.append(
            Phase2ValidationIssue(
                code="coverage_total_count_mismatch",
                message="Coverage map total_evidence_units does not match the evidence graph.",
            )
        )
    if coverage_map.primary_evidence_units != len(primary_ids):
        issues.append(
            Phase2ValidationIssue(
                code="coverage_primary_count_mismatch",
                message="Coverage map primary_evidence_units does not match the evidence graph.",
            )
        )
    if coverage_map.suppressed_repeat_units != len(duplicate_ids):
        issues.append(
            Phase2ValidationIssue(
                code="coverage_repeat_count_mismatch",
                message="Coverage map suppressed_repeat_units does not match duplicate evidence count.",
            )
        )
    declared_skill_count = sum(1 for unit in graph.evidence_units if unit.source_type == EvidenceSourceType.SKILL_DECLARATION)
    if coverage_map.declared_skill_units != declared_skill_count:
        issues.append(
            Phase2ValidationIssue(
                code="coverage_declared_skill_count_mismatch",
                message="Coverage map declared_skill_units does not match the graph.",
            )
        )

    for dimension in _all_dimensions(coverage_map):
        issues.extend(_validate_dimension_references(dimension, evidence_ids, primary_ids))
    for gap in [*coverage_map.sparsity_weak_zones, *coverage_map.weak_match_flags]:
        missing = [evidence_id for evidence_id in gap.related_evidence_ids if evidence_id not in evidence_ids]
        if missing:
            issues.append(
                Phase2ValidationIssue(
                    code="coverage_gap_reference_missing",
                    message=f"Coverage gap references missing evidence ids: {', '.join(missing)}.",
                )
            )
    weak_zone_keys = {(gap.area, gap.reason) for gap in coverage_map.sparsity_weak_zones}
    for weak_flag in coverage_map.weak_match_flags:
        if (weak_flag.area, weak_flag.reason) not in weak_zone_keys:
            issues.append(
                Phase2ValidationIssue(
                    code="weak_match_flag_not_in_weak_zones",
                    message="weak_match_flags must be derived from sparsity_weak_zones.",
                )
            )

    return Phase2ValidationReport(issues=issues)


def _validate_graph_identity(
    graph: CandidateEvidenceGraph,
    evidence_by_id: dict[str, EvidenceUnit],
) -> list[Phase2ValidationIssue]:
    issues: list[Phase2ValidationIssue] = []
    if len(evidence_by_id) != len(graph.evidence_units):
        duplicates = [item_id for item_id, count in Counter(unit.evidence_id for unit in graph.evidence_units).items() if count > 1]
        issues.append(
            Phase2ValidationIssue(
                code="duplicate_evidence_ids",
                message=f"Evidence graph contains duplicate evidence ids: {', '.join(sorted(duplicates))}.",
            )
        )
    for link in graph.overlap_links:
        if link.primary_evidence_id not in evidence_by_id:
            issues.append(
                Phase2ValidationIssue(
                    code="overlap_primary_missing",
                    message="Overlap link references a missing primary evidence unit.",
                    related_id=link.primary_evidence_id,
                )
            )
        if link.related_evidence_id not in evidence_by_id:
            issues.append(
                Phase2ValidationIssue(
                    code="overlap_related_missing",
                    message="Overlap link references a missing related evidence unit.",
                    related_id=link.related_evidence_id,
                )
            )
    return issues


def _validate_parent_child_consistency(
    graph: CandidateEvidenceGraph,
    evidence_by_id: dict[str, EvidenceUnit],
    source_profile: MasterProfile | None,
) -> list[Phase2ValidationIssue]:
    issues: list[Phase2ValidationIssue] = []
    known_parent_ids: set[str] = set()
    known_child_ids: set[str] = set()
    if source_profile is not None:
        known_parent_ids.add(source_profile.personal_profile.id)
        for entry in source_profile.experience + source_profile.projects + source_profile.education + source_profile.certifications + source_profile.awards + source_profile.skills:
            known_parent_ids.add(entry.id)
            bullets = getattr(entry, "bullets", [])
            known_child_ids.update(bullet.id for bullet in bullets)

    for unit in graph.evidence_units:
        if unit.parent_link.source_child_id is not None and unit.parent_link.source_child_type is None:
            issues.append(
                Phase2ValidationIssue(
                    code="child_link_missing_type",
                    message="Evidence unit has a source_child_id without source_child_type.",
                    evidence_id=unit.evidence_id,
                )
            )
        if source_profile is not None:
            if unit.parent_link.source_parent_id not in known_parent_ids:
                issues.append(
                    Phase2ValidationIssue(
                        code="unknown_parent_id",
                        message="Evidence unit parent_link.source_parent_id was not found in the source profile.",
                        evidence_id=unit.evidence_id,
                        related_id=unit.parent_link.source_parent_id,
                    )
                )
            child_id = unit.parent_link.source_child_id
            if child_id is not None and child_id.startswith("evidence.") is False and child_id not in known_child_ids:
                issues.append(
                    Phase2ValidationIssue(
                        code="unknown_child_id",
                        message="Evidence unit source_child_id was not found in the source profile.",
                        evidence_id=unit.evidence_id,
                        related_id=child_id,
                    )
                )
        if unit.source_type in {
            EvidenceSourceType.EXPERIENCE_BULLET,
            EvidenceSourceType.PROJECT_BULLET,
            EvidenceSourceType.EDUCATION_ACHIEVEMENT,
        } and unit.parent_link.source_child_id is None:
            issues.append(
                Phase2ValidationIssue(
                    code="granular_evidence_missing_child_link",
                    message="Granular bullet/honor evidence must preserve a child link.",
                    evidence_id=unit.evidence_id,
                )
            )
        if unit.duplicate_of is not None and unit.duplicate_of not in evidence_by_id:
            issues.append(
                Phase2ValidationIssue(
                    code="duplicate_of_missing",
                    message="duplicate_of points to a missing evidence id.",
                    evidence_id=unit.evidence_id,
                    related_id=unit.duplicate_of,
                )
            )
    return issues


def _validate_normalization_integrity(units: list[EvidenceUnit]) -> list[Phase2ValidationIssue]:
    issues: list[Phase2ValidationIssue] = []
    for unit in units:
        normalized_text = " ".join(unit.canonical_text.split())
        if unit.canonical_text != normalized_text:
            issues.append(
                Phase2ValidationIssue(
                    code="canonical_text_not_normalized",
                    message="canonical_text must be stripped and whitespace-normalized.",
                    evidence_id=unit.evidence_id,
                )
            )
        for field_name, values in {
            "normalized_skills": unit.normalized_skills,
            "normalized_tools": unit.normalized_tools,
            "normalized_domains": unit.normalized_domains,
        }.items():
            lowered = [value.casefold() for value in values]
            if lowered != list(dict.fromkeys(lowered)):
                issues.append(
                    Phase2ValidationIssue(
                        code="normalized_values_not_deduped",
                        message=f"{field_name} must be lower-cased and de-duplicated.",
                        evidence_id=unit.evidence_id,
                    )
                )
            if any(value != value.strip() for value in values):
                issues.append(
                    Phase2ValidationIssue(
                        code="normalized_value_not_trimmed",
                        message=f"{field_name} contains untrimmed canonical values.",
                        evidence_id=unit.evidence_id,
                    )
                )
    return issues


def _validate_dedupe_metadata(
    graph: CandidateEvidenceGraph,
    evidence_by_id: dict[str, EvidenceUnit],
) -> list[Phase2ValidationIssue]:
    issues: list[Phase2ValidationIssue] = []
    relationship_index: dict[tuple[str, str], set[EvidenceRelationshipType]] = defaultdict(set)
    for link in graph.overlap_links:
        pair = tuple(sorted((link.primary_evidence_id, link.related_evidence_id)))
        relationship_index[pair].add(link.relationship_type)

    for unit in graph.evidence_units:
        if unit.duplicate_of is None:
            continue
        pair = tuple(sorted((unit.evidence_id, unit.duplicate_of)))
        relationship_types = relationship_index.get(pair, set())
        if not relationship_types & {
            EvidenceRelationshipType.EXACT_DUPLICATE,
            EvidenceRelationshipType.NEAR_DUPLICATE,
        }:
            issues.append(
                Phase2ValidationIssue(
                    code="duplicate_without_overlap_link",
                    message="duplicate_of requires an exact or near-duplicate overlap link.",
                    evidence_id=unit.evidence_id,
                    related_id=unit.duplicate_of,
                )
            )
        if unit.duplicate_of == unit.evidence_id:
            issues.append(
                Phase2ValidationIssue(
                    code="self_duplicate_reference",
                    message="duplicate_of must not reference the evidence unit itself.",
                    evidence_id=unit.evidence_id,
                )
            )
    return issues


def _validate_dimension_references(
    dimension: CoverageDimension,
    evidence_ids: set[str],
    primary_ids: set[str],
) -> list[Phase2ValidationIssue]:
    issues: list[Phase2ValidationIssue] = []
    missing = [evidence_id for evidence_id in dimension.evidence_ids if evidence_id not in evidence_ids]
    if missing:
        issues.append(
            Phase2ValidationIssue(
                code="coverage_dimension_reference_missing",
                message=f"Coverage dimension references missing evidence ids: {', '.join(missing)}.",
            )
        )
    duplicate_refs = [item_id for item_id, count in Counter(dimension.evidence_ids).items() if count > 1]
    if duplicate_refs:
        issues.append(
            Phase2ValidationIssue(
                code="coverage_dimension_duplicate_references",
                message=f"Coverage dimension contains duplicate evidence references: {', '.join(duplicate_refs)}.",
            )
        )
    non_primary = [evidence_id for evidence_id in dimension.evidence_ids if evidence_id not in primary_ids]
    if non_primary:
        issues.append(
            Phase2ValidationIssue(
                code="coverage_dimension_non_primary_reference",
                message="Coverage dimensions must reference primary evidence units only.",
            )
        )
    return issues


def _all_dimensions(coverage_map: CandidateEvidenceCoverageMap) -> list[CoverageDimension]:
    return [
        *coverage_map.role_family_strengths,
        coverage_map.leadership_depth,
        coverage_map.ownership_depth,
        coverage_map.architecture_system_design_strength,
        coverage_map.delivery_execution_strength,
        *coverage_map.domain_strengths,
        *coverage_map.core_technical_clusters,
        coverage_map.cloud_platform_strength,
        coverage_map.product_stakeholder_strength,
        coverage_map.experimentation_analytics_strength,
        coverage_map.certifications_strength,
        coverage_map.awards_distinction_strength,
    ]
