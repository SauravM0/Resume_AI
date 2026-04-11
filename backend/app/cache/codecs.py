"""Serialization helpers for cached deterministic pipeline artifacts."""

from __future__ import annotations

def serialize_model(value) -> dict[str, object]:
    return value.model_dump(mode="json", exclude_none=True)


def deserialize_master_profile(payload: dict[str, object]):
    from resume_optimizer.models import MasterProfile

    return MasterProfile.model_validate(payload)


def deserialize_load_source_profile_output(payload: dict[str, object]) -> LoadSourceProfileOutput:
    from backend.app.orchestration.pipeline_models import LoadSourceProfileOutput

    return LoadSourceProfileOutput.model_validate(payload)


def deserialize_normalize_source_data_output(payload: dict[str, object]) -> NormalizeSourceDataOutput:
    from backend.app.orchestration.pipeline_models import NormalizeSourceDataOutput

    return NormalizeSourceDataOutput.model_validate(payload)


def deserialize_parse_job_description_output(payload: dict[str, object]) -> ParseJobDescriptionOutput:
    from backend.app.orchestration.pipeline_models import ParseJobDescriptionOutput

    return ParseJobDescriptionOutput.model_validate(payload)


def deserialize_job_ranking_features(payload: dict[str, object]) -> JobRankingFeatures:
    from resume_optimizer.job_feature_adapter import JobRankingFeatures

    return JobRankingFeatures.model_validate(payload)


def deserialize_loaded_template(payload: dict[str, object]) -> LoadedLatexTemplate:
    from backend.app.models.render_models import LoadedLatexTemplate

    return LoadedLatexTemplate.model_validate(payload)


def serialize_phase2_candidate_artifacts(value: Phase2CandidateArtifacts) -> dict[str, object]:
    return {
        "source_profile": value.source_profile.model_dump(mode="json", exclude_none=True),
        "evidence_graph": value.evidence_graph.model_dump(mode="json", exclude_none=True),
        "coverage_map": value.coverage_map.model_dump(mode="json", exclude_none=True),
        "ranking_compatible_evidence": [
            unit.model_dump(mode="json", exclude_none=True) for unit in value.ranking_compatible_evidence
        ],
        "extraction_summary": value.extraction_summary.model_dump(mode="json", exclude_none=True),
    }


def deserialize_phase2_candidate_artifacts(payload: dict[str, object]) -> Phase2CandidateArtifacts:
    from resume_optimizer.evidence_models import (
        CandidateEvidenceCoverageMap,
        CandidateEvidenceGraph,
        CanonicalEvidenceUnit,
    )
    from resume_optimizer.models import MasterProfile
    from resume_optimizer.phase2_artifacts import Phase2CandidateArtifacts
    from resume_optimizer.services.evidence_extraction_service import (
        CandidateEvidenceExtractionSummary,
    )

    return Phase2CandidateArtifacts(
        source_profile=MasterProfile.model_validate(payload["source_profile"]),
        evidence_graph=CandidateEvidenceGraph.model_validate(payload["evidence_graph"]),
        coverage_map=CandidateEvidenceCoverageMap.model_validate(payload["coverage_map"]),
        ranking_compatible_evidence=[
            CanonicalEvidenceUnit.model_validate(item)
            for item in payload.get("ranking_compatible_evidence", [])
        ],
        extraction_summary=CandidateEvidenceExtractionSummary.model_validate(payload["extraction_summary"]),
    )
