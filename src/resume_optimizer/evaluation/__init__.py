"""Phase 7 Evaluation Dataset System.

This package provides typed schemas and loaders for evaluation regression packs.
"""

from .case_models import (
    EdgeCaseType,
    Expectation,
    ExpectationMatchMode,
    ExpectationType,
    EvaluationCase,
    EvaluationManifest,
    EvaluationPack,
    JobDescriptionInput,
    Phase1ParseExpectations,
    ProfileInputReference,
    RoleFamily,
    ScoringWeights,
    SelectionExpectations,
    SeniorityLevel,
)
from .jd_parse_runner import (
    JDParseCaseResult,
    JDParseSummary,
    FieldScore,
    SkillScore,
    run_jd_parse_evaluation,
    render_jd_parse_summary,
    render_jd_parse_summary_json,
)
from .selection_runner import (
    SelectionCaseResult,
    SelectionSummary,
    PathologicalDetection,
    render_selection_case_report,
    run_selection_evaluation,
    render_selection_summary,
    render_selection_summary_json,
)
from .loader import (
    load_all_packs,
    load_evaluation_manifest,
    load_evaluation_pack,
    validate_case,
    validate_pack,
)

__all__ = [
    "EdgeCaseType",
    "Expectation",
    "ExpectationMatchMode",
    "ExpectationType",
    "EvaluationCase",
    "EvaluationManifest",
    "EvaluationPack",
    "JobDescriptionInput",
    "Phase1ParseExpectations",
    "ProfileInputReference",
    "RoleFamily",
    "ScoringWeights",
    "SelectionExpectations",
    "SeniorityLevel",
    "JDParseCaseResult",
    "JDParseSummary",
    "FieldScore",
    "SkillScore",
    "SelectionCaseResult",
    "SelectionSummary",
    "PathologicalDetection",
    "render_selection_case_report",
    "run_jd_parse_evaluation",
    "run_selection_evaluation",
    "render_jd_parse_summary",
    "render_selection_summary",
    "render_jd_parse_summary_json",
    "render_selection_summary_json",
    "load_all_packs",
    "load_evaluation_manifest",
    "load_evaluation_pack",
    "validate_case",
    "validate_pack",
]
