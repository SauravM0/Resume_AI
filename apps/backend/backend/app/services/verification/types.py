"""Shared enum types for the Phase 6 verification domain."""

from __future__ import annotations

from enum import StrEnum


class VerificationStatus(StrEnum):
    """Lifecycle status for an item or aggregate verification report."""

    PENDING = "pending"
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    FAILED = "failed"
    NEEDS_RETRY = "needs_retry"
    BLOCKED = "blocked"


class IssueSeverity(StrEnum):
    """Operational severity for verification issues."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VerificationDecisionOutcome(StrEnum):
    """Centralized Phase 6 action outcome derived from verification issues."""

    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    REPAIR_AND_PASS = "repair_and_pass"
    REGENERATE_TARGET = "regenerate_target"
    FAIL_CLOSED = "fail_closed"


class RepairExecutionStatus(StrEnum):
    """Execution status for a concrete fallback repair attempt."""

    NOT_NEEDED = "not_needed"
    APPLIED = "applied"
    FAILED = "failed"


class IssueCategory(StrEnum):
    """Stable taxonomy for unsupported or unverifiable generated content."""

    UNSUPPORTED_METRIC = "unsupported_metric"
    UNSUPPORTED_TOOL = "unsupported_tool"
    UNSUPPORTED_SCOPE = "unsupported_scope"
    UNSUPPORTED_LEADERSHIP = "unsupported_leadership"
    UNSUPPORTED_KEYWORD = "unsupported_keyword"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    UNSUPPORTED_CERTIFICATION = "unsupported_certification"
    UNSUPPORTED_AWARD = "unsupported_award"
    UNSUPPORTED_DOMAIN = "unsupported_domain"
    UNSUPPORTED_YEARS_EXPERIENCE = "unsupported_years_experience"
    SENIORITY_MISMATCH = "seniority_mismatch"
    ROLE_FAMILY_MISMATCH = "role_family_mismatch"
    BREADTH_INFLATION = "breadth_inflation"
    PROVENANCE_MISSING = "provenance_missing"
    PROVENANCE_WEAK = "provenance_weak"
    CONTENT_DRIFT = "content_drift"
    STRUCTURE_INVALID = "structure_invalid"
    SEMANTIC_VERIFICATION_UNAVAILABLE = "semantic_verification_unavailable"


class EvidenceStrength(StrEnum):
    """Verifier-facing evidence strength after provenance and semantic checks."""

    EXACT = "exact"
    NONE = "none"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERIFIED = "verified"


class ProvenanceRelationType(StrEnum):
    """How generated content is related to source-truth evidence."""

    DIRECT_REWRITE = "direct_rewrite"
    DIRECT_COPY = "direct_copy"
    MERGED_FROM_MULTIPLE = "merged_from_multiple"
    INFERRED_FROM_MULTIPLE_SUPPORTED_SOURCES = "inferred_from_multiple_supported_sources"


class FallbackAction(StrEnum):
    """Allowed downstream remediation actions when verification is not clean."""

    ACCEPT = "accept"
    PASS_AS_IS = "pass_as_is"
    FALLBACK_TO_ORIGINAL_SOURCE_BULLET = "fallback_to_original_source_bullet"
    RETRY_GENERATION = "retry_generation"
    USE_SOURCE_TEXT = "use_source_text"
    REMOVE_CLAIM = "remove_claim"
    DROP_ITEM = "drop_item"
    MARK_NEEDS_REVIEW = "mark_needs_review"
    REGENERATE_SPECIFIC_ITEM = "regenerate_specific_item"
    USE_SAFE_SUMMARY_FALLBACK = "use_safe_summary_fallback"
    REQUIRE_HUMAN_REVIEW = "require_human_review"
    BLOCK_RENDERING = "block_rendering"


class SemanticVerificationStatus(StrEnum):
    """Aggregate audit state for semantic verification execution."""

    DISABLED = "disabled"
    COMPLETED = "completed"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class SemanticVerifierUnavailableBehavior(StrEnum):
    """Configured action when the semantic verifier cannot run."""

    BLOCK = "block"
    MARK_NEEDS_REVIEW = "mark_needs_review"
