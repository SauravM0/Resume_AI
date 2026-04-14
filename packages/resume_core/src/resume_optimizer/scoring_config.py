"""Config-driven scoring weights and thresholds for the Phase 2 hybrid scorer."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from .models import StrictModel


class HybridScoringWeights(StrictModel):
    """Explainable weight allocation across Phase 2 scoring dimensions."""

    must_have_skill_overlap: float = Field(default=20.0, ge=0.0, le=100.0)
    nice_to_have_skill_overlap: float = Field(default=10.0, ge=0.0, le=100.0)
    role_family_relevance: float = Field(default=8.0, ge=0.0, le=100.0)
    seniority_relevance: float = Field(default=10.0, ge=0.0, le=100.0)
    domain_relevance: float = Field(default=15.0, ge=0.0, le=100.0)
    impact_strength: float = Field(default=10.0, ge=0.0, le=100.0)
    recency: float = Field(default=10.0, ge=0.0, le=100.0)
    evidence_strength: float = Field(default=7.0, ge=0.0, le=100.0)
    quantified_outcome_bonus: float = Field(default=5.0, ge=0.0, le=100.0)
    title_responsibility_relevance: float = Field(default=5.0, ge=0.0, le=100.0)
    semantic_similarity: float = Field(default=0.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_total(self) -> "HybridScoringWeights":
        total = sum(self.model_dump().values())
        if total > 100.0:
            raise ValueError("hybrid scoring weights must sum to 100 or less")
        return self


class HybridScoringThresholds(StrictModel):
    """Thresholds, penalties, and lookup breakpoints for hybrid scoring."""

    recency_recent_months: int = Field(default=12, ge=1, le=240)
    recency_moderate_months: int = Field(default=36, ge=1, le=240)
    recency_stale_months: int = Field(default=60, ge=1, le=480)
    strong_impact_signal_threshold: int = Field(default=2, ge=0, le=20)
    duplicate_penalty: float = Field(default=8.0, ge=0.0, le=100.0)
    near_duplicate_penalty: float = Field(default=4.0, ge=0.0, le=100.0)
    low_information_penalty: float = Field(default=5.0, ge=0.0, le=100.0)
    vague_penalty: float = Field(default=4.0, ge=0.0, le=100.0)
    unsupported_skill_penalty: float = Field(default=3.0, ge=0.0, le=100.0)
    stale_irrelevant_penalty: float = Field(default=10.0, ge=0.0, le=100.0)
    weak_alignment_penalty: float = Field(default=6.0, ge=0.0, le=100.0)


class SemanticFallbackBehavior(StrEnum):
    """Failure handling policy for semantic scoring."""

    DISABLED = "disabled"
    FALLBACK_TO_ZERO = "fallback_to_zero"
    RAISE = "raise"


class SemanticScoringConfig(StrictModel):
    """Operational controls for the semantic scoring provider."""

    enabled: bool = True
    provider: str = Field(default="deterministic_concept")
    fallback_behavior: SemanticFallbackBehavior = SemanticFallbackBehavior.FALLBACK_TO_ZERO


class HybridScoringConfig(StrictModel):
    """Top-level config for the hybrid scorer and semantic provider."""

    weights: HybridScoringWeights = Field(default_factory=HybridScoringWeights)
    thresholds: HybridScoringThresholds = Field(default_factory=HybridScoringThresholds)
    semantic: SemanticScoringConfig = Field(default_factory=SemanticScoringConfig)


DEFAULT_HYBRID_SCORING_CONFIG = HybridScoringConfig(
    weights=HybridScoringWeights(
        must_have_skill_overlap=20.0,
        nice_to_have_skill_overlap=10.0,
        role_family_relevance=8.0,
        seniority_relevance=10.0,
        domain_relevance=12.0,
        impact_strength=10.0,
        recency=8.0,
        evidence_strength=6.0,
        quantified_outcome_bonus=3.0,
        title_responsibility_relevance=3.0,
        semantic_similarity=10.0,
    )
)
