from __future__ import annotations

from resume_optimizer.evidence_models import (
    CanonicalEvidenceUnit,
    EvidenceParentLink,
    EvidenceProvenance,
    EvidenceSection,
    EvidenceSourceType,
)
from resume_optimizer.job_feature_adapter import JobRankingFeatures, WeightedFeatureBucket
from resume_optimizer.job_models import NormalizedJobAnalysis
from resume_optimizer.models import (
    BulletEntry,
    EvidenceStrength,
    ExperienceEntry,
    ItemType,
    MasterProfile,
    PartialDate,
    PersonalProfile,
    RoleType,
    SeniorityLevel,
    VerifiedStatus,
)
from resume_optimizer.ranking_service import build_phase2_ranking_artifacts
from resume_optimizer.scoring_config import (
    HybridScoringConfig,
    HybridScoringWeights,
    SemanticFallbackBehavior,
    SemanticScoringConfig,
)
from resume_optimizer.scoring_engine import HybridScoringEngine
from resume_optimizer.semantic_scoring import (
    DeterministicConceptSemanticScorer,
    SemanticScoringResult,
)


class _ExplodingSemanticScorer:
    def score(
        self,
        evidence_unit: CanonicalEvidenceUnit,
        job_features: JobRankingFeatures,
    ) -> SemanticScoringResult:
        raise RuntimeError("provider unavailable")


def test_exact_match_still_outranks_semantic_only_match() -> None:
    job_features = _job_features(must_have=["performance", "reliability"], nice_to_have=["backend"])
    engine = HybridScoringEngine(semantic_scorer=DeterministicConceptSemanticScorer())

    exact = engine.score_evidence_unit(
        _evidence_unit(
            evidence_id="evidence.exact",
            text="Improved performance and reliability of backend APIs.",
            normalized_skills=["performance", "reliability"],
        ),
        job_features,
    )
    paraphrase = engine.score_evidence_unit(
        _evidence_unit(
            evidence_id="evidence.paraphrase",
            text="Reduced latency and increased uptime across backend services.",
        ),
        job_features,
    )

    assert exact.total_score > paraphrase.total_score
    assert paraphrase.semantic_score.score > 0.0


def test_semantic_scoring_recovers_paraphrased_relevance() -> None:
    job_features = _job_features(must_have=["performance", "reliability"], nice_to_have=["backend"])
    paraphrase = _evidence_unit(
        evidence_id="evidence.paraphrase",
        text="Reduced latency and increased uptime across backend services.",
    )
    enabled_engine = HybridScoringEngine(semantic_scorer=DeterministicConceptSemanticScorer())
    disabled_engine = HybridScoringEngine(
        config=HybridScoringConfig(
            weights=_hybrid_weights(semantic_weight=10.0),
            semantic=SemanticScoringConfig(enabled=False),
        ),
        semantic_scorer=DeterministicConceptSemanticScorer(),
    )

    enabled = enabled_engine.score_evidence_unit(paraphrase, job_features)
    disabled = disabled_engine.score_evidence_unit(paraphrase, job_features)

    assert enabled.semantic_score.score > 0.0
    assert disabled.semantic_score.score == 0.0
    assert enabled.total_score > disabled.total_score


def test_semantic_scoring_falls_back_gracefully_when_provider_is_unavailable() -> None:
    engine = HybridScoringEngine(
        config=HybridScoringConfig(
            weights=_hybrid_weights(semantic_weight=10.0),
            semantic=SemanticScoringConfig(
                enabled=True,
                provider="deterministic_concept",
                fallback_behavior=SemanticFallbackBehavior.FALLBACK_TO_ZERO,
            ),
        ),
        semantic_scorer=_ExplodingSemanticScorer(),
    )

    result = engine.score_evidence_unit(
        _evidence_unit(
            evidence_id="evidence.fallback",
            text="Reduced latency and increased uptime across backend services.",
        ),
        _job_features(must_have=["performance", "reliability"]),
    )

    assert result.semantic_score.score == 0.0
    assert result.semantic_score.confidence_note is not None
    assert "fallback applied" in result.semantic_score.confidence_note


def test_phase2_ranking_service_uses_semantic_scoring_in_default_path() -> None:
    profile = MasterProfile(
        id="fixture.semantic.profile",
        personal_profile=PersonalProfile(
            id="fixture.semantic.person",
            full_name="Semantic Candidate",
            role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
            seniority_level=SeniorityLevel.SENIOR,
            verified_status=VerifiedStatus.SELF_REPORTED,
            evidence_strength=EvidenceStrength.MODERATE,
        ),
        experience=[
            ExperienceEntry(
                id="fixture.semantic.exp",
                organization="Semantic Co",
                title="Backend Engineer",
                role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
                seniority_level=SeniorityLevel.SENIOR,
                start_date=PartialDate(raw_value="2024-01"),
                current=True,
                bullets=[
                    BulletEntry(
                        id="fixture.semantic.exp.b1",
                        text="Reduced latency and improved uptime across backend services.",
                        verified_status=VerifiedStatus.CORROBORATED,
                        evidence_strength=EvidenceStrength.STRONG,
                    )
                ],
                verified_status=VerifiedStatus.CORROBORATED,
                evidence_strength=EvidenceStrength.STRONG,
            )
        ],
    )
    job_analysis = NormalizedJobAnalysis(
        role_type=RoleType.INDIVIDUAL_CONTRIBUTOR,
        seniority_level=SeniorityLevel.SENIOR,
        must_have_requirements=["Improve API performance and service reliability"],
        nice_to_have_requirements=["Backend platform experience"],
    )

    artifacts = build_phase2_ranking_artifacts(job_analysis, profile)

    paraphrase_score = next(
        score
        for score in artifacts.selection_result.evidence_scores
        if score.source_item_id == "fixture.semantic.exp"
    )
    semantic_component = paraphrase_score.component_scores["semantic_similarity"]

    assert semantic_component.value > 0.0
    assert "semantic" in semantic_component.rationale


def _job_features(*, must_have: list[str], nice_to_have: list[str] | None = None) -> JobRankingFeatures:
    return JobRankingFeatures(
        canonical_must_have_skills=WeightedFeatureBucket(values=must_have, weight=20.0, confidence=1.0),
        canonical_nice_to_have_skills=WeightedFeatureBucket(
            values=nice_to_have or [],
            weight=10.0,
            confidence=1.0,
        ),
        canonical_all_skills=[*must_have, *(nice_to_have or [])],
        role_family="engineering",
        role_type="backend",
        seniority_target="senior",
        responsibility_themes=["reliability", "performance", "backend"],
        action_verb_signals=["improve", "optimize"],
        keyword_priority_buckets={
            "must_have": must_have,
            "nice_to_have": nice_to_have or [],
        },
        role_priority_weight=9.0,
        seniority_priority_weight=10.0,
        domain_priority_weight=15.0,
        parser_confidence=1.0,
    )


def _hybrid_weights(*, semantic_weight: float) -> HybridScoringWeights:
    return HybridScoringWeights(
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
        semantic_similarity=semantic_weight,
    )


def _evidence_unit(
    *,
    evidence_id: str,
    text: str,
    normalized_skills: list[str] | None = None,
) -> CanonicalEvidenceUnit:
    parent_link = EvidenceParentLink(
        source_section=EvidenceSection.EXPERIENCE,
        source_parent_id=f"{evidence_id}.parent",
        source_parent_type=ItemType.EXPERIENCE,
    )
    provenance = EvidenceProvenance(
        source_section=EvidenceSection.EXPERIENCE,
        source_item_type=ItemType.EXPERIENCE,
        source_parent_id=f"{evidence_id}.parent",
        source_parent_title="Backend Engineer",
        extraction_method="test",
        source_excerpt=text,
    )
    return CanonicalEvidenceUnit(
        evidence_id=evidence_id,
        source_type=EvidenceSourceType.EXPERIENCE_SUMMARY,
        parent_link=parent_link,
        canonical_text=text,
        raw_text=text,
        normalized_skills=normalized_skills or [],
        evidence_strength=EvidenceStrength.STRONG,
        verified_status=VerifiedStatus.CORROBORATED,
        dedupe_fingerprint=evidence_id,
        provenance=provenance,
    )
