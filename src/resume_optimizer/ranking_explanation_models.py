"""Shared explanation models used by ranking and resume selection layers."""

from __future__ import annotations

from pydantic import Field, computed_field

from .models import NonEmptyStr, StrictModel


class RankingExplanation(StrictModel):
    """Structured explanation of why an evidence unit was scored or selected."""

    summary: NonEmptyStr
    matched_keywords: list[NonEmptyStr] = Field(default_factory=list)
    matched_required_skills: list[NonEmptyStr] = Field(default_factory=list)
    matched_preferred_skills: list[NonEmptyStr] = Field(default_factory=list)
    matched_domains: list[NonEmptyStr] = Field(default_factory=list)
    matched_relevant_for: list[NonEmptyStr] = Field(default_factory=list)
    matched_job_requirements: list[NonEmptyStr] = Field(default_factory=list)
    matched_prioritized_skills: list[NonEmptyStr] = Field(default_factory=list)
    mismatch_signals: list[NonEmptyStr] = Field(default_factory=list)
    warning_signals: list[NonEmptyStr] = Field(default_factory=list)
    explanation_fragments: list[NonEmptyStr] = Field(default_factory=list)
    confidence_notes: list[NonEmptyStr] = Field(default_factory=list)
    signal_labels: list[NonEmptyStr] = Field(default_factory=list)

    @computed_field(return_type=str)
    @property
    def reasoning(self) -> str:
        """Provide a legacy string explanation for older ranking consumers."""

        return self.summary
