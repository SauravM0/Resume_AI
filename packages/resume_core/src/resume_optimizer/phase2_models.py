"""Strict contracts for Phase 2 evidence ranking, selection, and diagnostics."""

from __future__ import annotations

from enum import StrEnum

from pydantic import (
    AliasChoices,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from .job_models import NormalizedJobAnalysis
from .models import ItemType, MasterProfile, NonEmptyStr, ScoreValue, StableId, StrictModel
from .ranking_explanation_models import RankingExplanation
from .resume_selection_models import EvidenceScore, ResumeSelectionDecision
from .scoring_engine import ScoreComponent

_RANKABLE_ITEM_TYPES = (
    ItemType.EXPERIENCE,
    ItemType.PROJECT,
    ItemType.CERTIFICATION,
    ItemType.SKILL,
)
_BULLET_SELECTABLE_ITEM_TYPES = (
    ItemType.EXPERIENCE,
    ItemType.PROJECT,
)


class Phase2Status(StrEnum):
    """High-level Phase 2 execution status for success and failure payloads."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class JobAnalysisInput(NormalizedJobAnalysis):
    """Normalized Phase 1 output consumed by the Phase 2 ranking engine."""


class CandidateProfileInput(MasterProfile):
    """Normalized source-of-truth candidate profile consumed by Phase 2."""


class EvidenceUnit(StrictModel):
    """Single rankable evidence unit extracted from the candidate profile."""

    id: StableId
    item_type: ItemType
    title: NonEmptyStr
    source_item_id: StableId | None = None
    source_bullet_ids: list[StableId] = Field(default_factory=list)
    domain_tags: list[NonEmptyStr] = Field(default_factory=list)
    relevant_for: list[NonEmptyStr] = Field(default_factory=list)
    keywords: list[NonEmptyStr] = Field(default_factory=list)
    bullets: list[NonEmptyStr] = Field(default_factory=list)
    impact: ScoreValue | None = None
    level: NonEmptyStr | None = None
    start: NonEmptyStr | None = None
    end: NonEmptyStr | None = None

    @field_validator("item_type")
    @classmethod
    def validate_item_type(cls, value: ItemType) -> ItemType:
        """Restrict evidence units to types the ranking layer can reason about."""

        if value not in _RANKABLE_ITEM_TYPES:
            allowed = ", ".join(item.value for item in _RANKABLE_ITEM_TYPES)
            raise ValueError(f"candidate evidence item_type must be one of: {allowed}")
        return value

    @model_validator(mode="after")
    def validate_bullet_shape(self) -> "EvidenceUnit":
        """Ensure bullet identifiers align with bullet text payloads when present."""

        if self.source_bullet_ids and len(self.source_bullet_ids) != len(self.bullets):
            raise ValueError("source_bullet_ids must align one-to-one with bullets")
        if self.item_type not in _BULLET_SELECTABLE_ITEM_TYPES and self.source_bullet_ids:
            raise ValueError(
                "source_bullet_ids are only valid for experience and project evidence units"
            )
        return self


class ScoredEvidenceUnit(EvidenceUnit):
    """Evidence unit enriched with a bounded relevance score and explanation."""

    relevance_score: ScoreValue
    ranking_explanation: RankingExplanation = Field(
        validation_alias=AliasChoices("ranking_explanation", "explanation")
    )
    provenance: dict[str, object] = Field(default_factory=dict)
    component_scores: dict[str, ScoreComponent] = Field(default_factory=dict)
    selected_bullet_ids: list[StableId] = Field(
        default_factory=list,
        validation_alias=AliasChoices("selected_bullet_ids", "include_bullet_ids"),
    )
    include_bullet_indexes: list[int] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def coerce_legacy_explanation_fields(cls, data: object) -> object:
        """Accept legacy RankedItem payloads that use matching_keywords and reasoning."""

        if not isinstance(data, dict):
            return data

        if "ranking_explanation" not in data and "explanation" not in data:
            reasoning = data.get("reasoning")
            matching_keywords = data.get("matching_keywords", [])
            data = {
                **data,
                "title": data.get("title") or data.get("id") or "ranked-item",
                "ranking_explanation": {
                    "summary": reasoning or "Selected on available deterministic score signals.",
                    "matched_keywords": matching_keywords,
                    "matched_required_skills": matching_keywords,
                    "matched_preferred_skills": [],
                    "matched_job_requirements": [],
                    "matched_prioritized_skills": matching_keywords,
                    "matched_domains": data.get("matched_domains", []),
                    "matched_relevant_for": data.get("matched_relevant_for", []),
                    "mismatch_signals": data.get("mismatch_signals", []),
                    "warning_signals": data.get("warning_signals", []),
                    "explanation_fragments": data.get("explanation_fragments", []),
                    "confidence_notes": data.get("confidence_notes", []),
                    "signal_labels": data.get("signal_labels", []),
                },
            }
        if "matching_keywords" in data or "reasoning" in data:
            data = {
                key: value
                for key, value in data.items()
                if key not in {"matching_keywords", "reasoning"}
            }
        return data

    @field_validator("include_bullet_indexes")
    @classmethod
    def validate_include_bullet_indexes(cls, value: list[int]) -> list[int]:
        """Preserve backward-compatible bullet-index payloads with strict bounds."""

        if any(index < 0 for index in value):
            raise ValueError("include_bullet_indexes must contain only non-negative integers")
        return value

    @model_validator(mode="after")
    def validate_selected_bullets(self) -> "ScoredEvidenceUnit":
        """Ensure selected bullet ids only reference bullets exposed by the evidence unit."""

        available_bullets = set(self.source_bullet_ids)
        if self.selected_bullet_ids and not available_bullets:
            raise ValueError("selected_bullet_ids require source_bullet_ids on the evidence unit")

        invalid_ids = [bullet_id for bullet_id in self.selected_bullet_ids if bullet_id not in available_bullets]
        if invalid_ids:
            invalid_list = ", ".join(invalid_ids)
            raise ValueError(
                f"selected_bullet_ids must reference valid source bullet ids: {invalid_list}"
            )
        return self

    @computed_field(return_type=list[str])
    @property
    def matching_keywords(self) -> list[str]:
        """Provide the legacy keyword-match list expected by older Phase 2 consumers."""

        return self.ranking_explanation.matched_keywords

    @computed_field(return_type=str)
    @property
    def reasoning(self) -> str:
        """Provide the legacy free-text reasoning string expected by older consumers."""

        return self.ranking_explanation.summary


class SelectedExperience(StrictModel):
    """Selected experience item and the source bullet ids chosen for later drafting."""

    id: StableId
    source_item_id: StableId
    relevance_score: ScoreValue
    evidence_unit_ids: list[StableId] = Field(default_factory=list)
    selected_bullet_ids: list[StableId] = Field(min_length=1)
    ranking_explanation: RankingExplanation
    provenance: dict[str, object] = Field(default_factory=dict)


class SelectedProject(StrictModel):
    """Selected project item and the source bullet ids chosen for later drafting."""

    id: StableId
    source_item_id: StableId
    relevance_score: ScoreValue
    evidence_unit_ids: list[StableId] = Field(default_factory=list)
    selected_bullet_ids: list[StableId] = Field(min_length=1)
    ranking_explanation: RankingExplanation
    provenance: dict[str, object] = Field(default_factory=dict)


class SelectedSkill(StrictModel):
    """Selected skill signal that should be surfaced during later content generation."""

    id: StableId
    source_item_id: StableId
    relevance_score: ScoreValue
    skill_name: NonEmptyStr
    ranking_explanation: RankingExplanation
    provenance: dict[str, object] = Field(default_factory=dict)


class Phase2Diagnostics(StrictModel):
    """Operational diagnostics for Phase 2 success, partial success, or failure states."""

    status: Phase2Status = Phase2Status.SUCCESS
    warnings: list[NonEmptyStr] = Field(default_factory=list)
    errors: list[NonEmptyStr] = Field(default_factory=list)
    candidate_evidence_count: int = Field(default=0, ge=0)
    scored_evidence_count: int = Field(default=0, ge=0)
    selected_experience_count: int = Field(default=0, ge=0)
    selected_project_count: int = Field(default=0, ge=0)
    selected_skill_count: int = Field(default=0, ge=0)
    top_matched_requirements: list[NonEmptyStr] = Field(default_factory=list)
    weak_coverage_areas: list[NonEmptyStr] = Field(default_factory=list)
    near_miss_item_ids: list[StableId] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_vs_errors(self) -> "Phase2Diagnostics":
        """Prevent contradictory diagnostics such as failed status with no errors."""

        if self.status == Phase2Status.FAILED and not self.errors:
            raise ValueError("failed diagnostics must include at least one error")
        return self


class Phase2SelectionResult(StrictModel):
    """Canonical Phase 2 output carrying selected evidence, scored units, and diagnostics."""

    job_analysis: JobAnalysisInput
    candidate_profile_id: StableId
    evidence_scores: list[EvidenceScore] = Field(default_factory=list)
    scored_evidence: list[ScoredEvidenceUnit] = Field(default_factory=list)
    resume_selection_decision: ResumeSelectionDecision | None = None
    selected_experiences: list[SelectedExperience] = Field(default_factory=list)
    selected_projects: list[SelectedProject] = Field(default_factory=list)
    selected_skills: list[SelectedSkill] = Field(default_factory=list)
    diagnostics: Phase2Diagnostics = Field(default_factory=Phase2Diagnostics)

    @model_validator(mode="after")
    def validate_selection_references(self) -> "Phase2SelectionResult":
        """Ensure selected entries resolve to valid scored evidence and source bullets."""

        evidence_by_id = {item.id: item for item in self.scored_evidence}
        evidence_ids_by_source: dict[str, list[str]] = {}
        bullet_ids_by_source: dict[str, set[str]] = {}
        for evidence in self.scored_evidence:
            if evidence.source_item_id is None:
                continue
            evidence_ids_by_source.setdefault(evidence.source_item_id, []).append(evidence.id)
            bullet_ids_by_source.setdefault(evidence.source_item_id, set()).update(
                evidence.source_bullet_ids
            )

        for selected in [*self.selected_experiences, *self.selected_projects]:
            supporting_evidence_ids = list(selected.evidence_unit_ids)
            if selected.source_item_id in evidence_by_id and not supporting_evidence_ids:
                supporting_evidence_ids.append(selected.source_item_id)
            if selected.source_item_id not in evidence_by_id:
                supporting_evidence_ids.extend(evidence_ids_by_source.get(selected.source_item_id, []))
            supporting_evidence_ids = list(dict.fromkeys(supporting_evidence_ids))
            if not supporting_evidence_ids:
                raise ValueError(
                    "selected item source_item_id not found in scored_evidence/source entries: "
                    f"{selected.source_item_id}"
                )
            valid_bullet_ids: set[str] = set()
            for evidence_id in supporting_evidence_ids:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None:
                    raise ValueError(
                        f"selected item evidence_unit_id not found in scored_evidence: {evidence_id}"
                    )
                valid_bullet_ids.update(evidence.source_bullet_ids)
            if not valid_bullet_ids:
                valid_bullet_ids.update(bullet_ids_by_source.get(selected.source_item_id, set()))
            invalid_ids = [
                bullet_id
                for bullet_id in selected.selected_bullet_ids
                if bullet_id not in valid_bullet_ids
            ]
            if invalid_ids:
                invalid_list = ", ".join(invalid_ids)
                raise ValueError(
                    "selected bullets must reference valid source IDs: "
                    f"{selected.source_item_id} -> {invalid_list}"
                )

        object.__setattr__(
            self,
            "diagnostics",
            self.diagnostics.model_copy(
                update={
                    "scored_evidence_count": len(self.scored_evidence),
                    "selected_experience_count": len(self.selected_experiences),
                    "selected_project_count": len(self.selected_projects),
                    "selected_skill_count": len(self.selected_skills),
                }
            ),
        )
        return self


class Phase2SelectionResultRecord(StrictModel):
    """Database-oriented DTO for persisting a Phase 2 result snapshot in PostgreSQL."""

    profile_id: StableId
    job_analysis: JobAnalysisInput
    result: Phase2SelectionResult
