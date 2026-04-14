"""Deterministic semantic-scoring providers for Phase 2 hybrid ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from pydantic import Field

from .evidence_models import CanonicalEvidenceUnit
from .job_feature_adapter import JobRankingFeatures
from .models import StrictModel
from .scoring_config import SemanticFallbackBehavior, SemanticScoringConfig

_TOKEN_PATTERN = re.compile(r"[a-z0-9+#./-]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "be",
    "build",
    "built",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
_CONCEPT_ALIASES = {
    "api": {"api", "apis", "service", "services", "endpoint", "endpoints"},
    "backend": {"backend", "server", "servers", "service", "services"},
    "deploy": {"deploy", "deployment", "deployments", "release", "releases", "ship", "shipping"},
    "etl": {"etl", "pipeline", "pipelines", "ingestion", "batch"},
    "infrastructure": {"infrastructure", "platform", "cloud", "aws", "terraform", "kubernetes"},
    "latency": {"latency", "performance", "throughput", "optimization", "optimized"},
    "monitoring": {"monitoring", "observability", "telemetry", "alerting", "alerts"},
    "reliability": {"reliability", "resilience", "availability", "uptime", "fault", "tolerant"},
    "testing": {"testing", "tests", "qa", "quality", "validation"},
}


class SemanticScoringResult(StrictModel):
    """Structured semantic score payload consumed by the hybrid scorer."""

    score: float = Field(default=0.0, ge=0.0, le=1.0)
    matched_concepts: list[str] = Field(default_factory=list)
    confidence_note: str | None = None


class SemanticScorer(Protocol):
    """Pluggable semantic scorer interface for one evidence unit against one job."""

    def score(
        self,
        evidence_unit: CanonicalEvidenceUnit,
        job_features: JobRankingFeatures,
    ) -> SemanticScoringResult:
        """Return a bounded semantic score and matched concepts."""


class NullSemanticScorer:
    """Explicit no-op scorer used only for disabled or fallback paths."""

    def score(
        self,
        evidence_unit: CanonicalEvidenceUnit,
        job_features: JobRankingFeatures,
    ) -> SemanticScoringResult:
        return SemanticScoringResult(
            score=0.0,
            matched_concepts=[],
            confidence_note="semantic scorer disabled",
        )


@dataclass(slots=True)
class DeterministicConceptSemanticScorer:
    """Concept-aware deterministic scorer for paraphrase recovery without external models."""

    concept_aliases: dict[str, set[str]] | None = None

    def score(
        self,
        evidence_unit: CanonicalEvidenceUnit,
        job_features: JobRankingFeatures,
    ) -> SemanticScoringResult:
        aliases = self.concept_aliases or _CONCEPT_ALIASES
        evidence_tokens = _expand_tokens(_tokenize(_semantic_text_for_evidence(evidence_unit)), aliases)
        job_tokens = _expand_tokens(_tokenize(_semantic_text_for_job(job_features)), aliases)
        if not evidence_tokens or not job_tokens:
            return SemanticScoringResult(score=0.0, matched_concepts=[], confidence_note="semantic tokens unavailable")

        overlap = sorted(evidence_tokens.intersection(job_tokens))
        if not overlap:
            return SemanticScoringResult(score=0.0, matched_concepts=[], confidence_note="no semantic concept overlap")

        coverage = len(overlap) / max(1, len(job_tokens))
        density = len(overlap) / max(1, min(len(evidence_tokens), len(job_tokens)))
        score = round(min(1.0, coverage * 0.65 + density * 0.35), 4)
        return SemanticScoringResult(
            score=score,
            matched_concepts=overlap[:8],
            confidence_note=f"deterministic semantic concept overlap on {len(overlap)} concepts",
        )


def _semantic_text_for_evidence(evidence_unit: CanonicalEvidenceUnit) -> str:
    parts = [
        evidence_unit.canonical_text,
        evidence_unit.raw_text,
        *evidence_unit.normalized_skills,
        *evidence_unit.normalized_tools,
        *evidence_unit.normalized_domains,
        evidence_unit.provenance.source_parent_title or "",
        *evidence_unit.signals.signal_tokens,
        *evidence_unit.signals.business_outcome_hints,
    ]
    return " ".join(part for part in parts if part)


def _semantic_text_for_job(job_features: JobRankingFeatures) -> str:
    parts = [
        *job_features.canonical_must_have_skills.values,
        *job_features.canonical_nice_to_have_skills.values,
        *job_features.domain_targets,
        *job_features.responsibility_themes,
        *job_features.action_verb_signals,
        *job_features.keyword_priority_buckets.get("must_have", []),
        *job_features.keyword_priority_buckets.get("nice_to_have", []),
    ]
    if job_features.role_type:
        parts.append(job_features.role_type)
    if job_features.role_family:
        parts.append(job_features.role_family)
    return " ".join(part for part in parts if part)


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw in _TOKEN_PATTERN.findall(text.casefold()):
        token = raw.strip(".-/")
        if len(token) < 3 or token in _STOP_WORDS:
            continue
        tokens.add(_normalize_token(token))
    return tokens


def _expand_tokens(tokens: set[str], aliases: dict[str, set[str]]) -> set[str]:
    expanded = set(tokens)
    for token in list(tokens):
        for concept, concept_aliases in aliases.items():
            if token in concept_aliases:
                expanded.add(concept)
                expanded.update(concept_aliases)
    return expanded


def _normalize_token(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("ing") and len(token) > 5:
        return token[:-3]
    if token.endswith("ed") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
        return token[:-1]
    return token


def build_semantic_scorer(config: SemanticScoringConfig) -> SemanticScorer:
    """Return the configured semantic scorer with deterministic fallback behavior."""

    if not config.enabled or config.provider == "null":
        return NullSemanticScorer()
    if config.provider == "deterministic_concept":
        return DeterministicConceptSemanticScorer()
    if config.fallback_behavior == SemanticFallbackBehavior.RAISE:
        raise ValueError(f"unsupported semantic scorer provider: {config.provider}")
    return NullSemanticScorer()
