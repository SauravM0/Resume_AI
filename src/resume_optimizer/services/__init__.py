"""Service layer exports for backend orchestration."""

from .evidence_extraction_service import (
    CandidateEvidenceExtractionResult,
    CandidateEvidenceExtractionService,
    CandidateEvidenceExtractionSummary,
    DEFAULT_CANDIDATE_EVIDENCE_EXTRACTION_SERVICE,
    DefaultCandidateEvidenceExtractor,
)
from .evidence_enrichment_service import (
    DEFAULT_EVIDENCE_ENRICHMENT_SERVICE,
    EvidenceEnrichmentService,
)
from .evidence_quality_service import (
    DEFAULT_EVIDENCE_QUALITY_SERVICE,
    EvidenceQualityService,
)
from .evidence_overlap_service import (
    DEFAULT_EVIDENCE_OVERLAP_RESOLUTION_SERVICE,
    EvidenceOverlapResolution,
    EvidenceOverlapResolutionService,
)
from .evidence_coverage_map_service import (
    CandidateEvidenceCoverageMapService,
    DEFAULT_CANDIDATE_EVIDENCE_COVERAGE_MAP_SERVICE,
)
from .phase2_service import (
    DEFAULT_PHASE2_SERVICE,
    NoOpPhase2PersistenceRepository,
    Phase2PersistenceRepository,
    Phase2Service,
    Phase2ServiceResult,
)
from .phase3_service import (
    DEFAULT_PHASE3_SERVICE,
    Phase3Service,
    Phase3ServiceResult,
)

__all__ = [
    "CandidateEvidenceExtractionResult",
    "CandidateEvidenceExtractionService",
    "CandidateEvidenceExtractionSummary",
    "CandidateEvidenceCoverageMapService",
    "EvidenceEnrichmentService",
    "EvidenceOverlapResolution",
    "EvidenceOverlapResolutionService",
    "EvidenceQualityService",
    "DEFAULT_PHASE2_SERVICE",
    "DEFAULT_PHASE3_SERVICE",
    "DEFAULT_CANDIDATE_EVIDENCE_COVERAGE_MAP_SERVICE",
    "DEFAULT_CANDIDATE_EVIDENCE_EXTRACTION_SERVICE",
    "DEFAULT_EVIDENCE_ENRICHMENT_SERVICE",
    "DEFAULT_EVIDENCE_OVERLAP_RESOLUTION_SERVICE",
    "DEFAULT_EVIDENCE_QUALITY_SERVICE",
    "DefaultCandidateEvidenceExtractor",
    "NoOpPhase2PersistenceRepository",
    "Phase2PersistenceRepository",
    "Phase2Service",
    "Phase2ServiceResult",
    "Phase3Service",
    "Phase3ServiceResult",
]
