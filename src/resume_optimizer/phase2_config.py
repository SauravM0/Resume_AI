"""Explicit configuration models for Phase 2 ranking and selection behavior."""

from __future__ import annotations

from pydantic import Field, model_validator

from .models import ScoreValue, StrictModel


class Phase2Weights(StrictModel):
    """Deterministic scoring weights used by the Phase 2 ranking engine."""

    keyword: float = Field(default=40.0, ge=0.0, le=100.0)
    relevant_for: float = Field(default=15.0, ge=0.0, le=100.0)
    domain: float = Field(default=15.0, ge=0.0, le=100.0)
    seniority: float = Field(default=10.0, ge=0.0, le=100.0)
    impact: float = Field(default=10.0, ge=0.0, le=100.0)
    recency: float = Field(default=10.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_total_weight(self) -> "Phase2Weights":
        """Ensure the default scoring budget stays bounded to 100 points."""

        total = (
            self.keyword
            + self.relevant_for
            + self.domain
            + self.seniority
            + self.impact
            + self.recency
        )
        if total > 100.0:
            raise ValueError("phase2 weights must sum to 100 or less")
        return self


class Phase2SelectionLimits(StrictModel):
    """Selection-count limits for ranked evidence returned by Phase 2."""

    max_experiences: int = Field(default=3, ge=1, le=20)
    max_projects: int = Field(default=3, ge=0, le=20)
    max_certifications: int = Field(default=2, ge=0, le=20)
    max_highlighted_skills: int = Field(default=5, ge=0, le=20)
    max_highlighted_skills_per_category: int = Field(default=3, ge=1, le=20)
    max_bullet_share_per_experience: float = Field(default=0.6, ge=0.34, le=1.0)
    minimum_experience_spread: int = Field(default=2, ge=1, le=10)
    max_bullets_per_item: int = Field(default=5, ge=1, le=20)
    min_bullets_if_available: int = Field(default=3, ge=1, le=20)
    max_summary_themes: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_bullet_bounds(self) -> "Phase2SelectionLimits":
        """Ensure minimum bullet expectations never exceed the hard maximum."""

        if self.min_bullets_if_available > self.max_bullets_per_item:
            raise ValueError(
                "min_bullets_if_available must be less than or equal to max_bullets_per_item"
            )
        return self


class Phase2Thresholds(StrictModel):
    """Thresholds that control inclusion, diagnostics, and explanation behavior."""

    min_relevance_score: ScoreValue = 0.0
    recent_evidence_score_threshold: float = Field(default=7.5, ge=0.0, le=100.0)
    strong_impact_score_threshold: float = Field(default=5.0, ge=0.0, le=100.0)
    explanation_keyword_limit: int = Field(default=3, ge=1, le=10)
    explanation_domain_limit: int = Field(default=2, ge=1, le=10)
    explanation_relevant_for_limit: int = Field(default=2, ge=1, le=10)
    dominant_experience_score_gap: float = Field(default=0.18, ge=0.0, le=1.0)
    similar_experience_score_gap: float = Field(default=0.08, ge=0.0, le=1.0)


class Phase2Config(StrictModel):
    """Top-level Phase 2 configuration container for scoring and selection."""

    weights: Phase2Weights = Field(default_factory=Phase2Weights)
    selection_limits: Phase2SelectionLimits = Field(default_factory=Phase2SelectionLimits)
    thresholds: Phase2Thresholds = Field(default_factory=Phase2Thresholds)


DEFAULT_PHASE2_CONFIG = Phase2Config()
