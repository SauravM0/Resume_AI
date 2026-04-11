"""Fallback policy matrix for Phase 6 orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.orchestration.enums import OrchestrationFailureType, StageName
from backend.app.orchestration.policies.policy_types import FallbackStrategy


@dataclass(frozen=True, slots=True)
class FallbackPolicyRule:
    """Fallback decision rule keyed by stage, failure type, and attempt window."""

    stage_name: StageName
    failure_type: OrchestrationFailureType
    strategy: FallbackStrategy
    min_attempt: int
    max_attempt: int
    safe_to_apply_automatically: bool
    escalation_note: str

    def matches(
        self,
        *,
        stage_name: StageName,
        failure_type: OrchestrationFailureType,
        current_attempt: int,
    ) -> bool:
        """Return whether this rule applies to the policy key."""

        return (
            self.stage_name == stage_name
            and self.failure_type == failure_type
            and self.min_attempt <= current_attempt <= self.max_attempt
        )


FALLBACK_POLICY_RULES: tuple[FallbackPolicyRule, ...] = (
    FallbackPolicyRule(
        stage_name=StageName.RANK_SELECT_EVIDENCE,
        failure_type=OrchestrationFailureType.RANKING_SELECTION,
        strategy=FallbackStrategy.DETERMINISTIC_BEST_MATCH_SUBSET,
        min_attempt=1,
        max_attempt=1,
        safe_to_apply_automatically=False,
        escalation_note=(
            "Empty or invalid rank result may use a deterministic best-match subset only "
            "when an explicit fallback implementation can prove the subset is source-backed."
        ),
    ),
    FallbackPolicyRule(
        stage_name=StageName.VERIFY_GENERATED_CONTENT,
        failure_type=OrchestrationFailureType.VERIFICATION_BLOCKED,
        strategy=FallbackStrategy.SOURCE_BULLET_OR_SAFER_REWRITE,
        min_attempt=1,
        max_attempt=1,
        safe_to_apply_automatically=False,
        escalation_note=(
            "Verification-blocked content may fall back to source bullet text or a safer "
            "rewrite only through a verifier-approved fallback hook."
        ),
    ),
    FallbackPolicyRule(
        stage_name=StageName.RENDER_DETERMINISTIC_LATEX,
        failure_type=OrchestrationFailureType.LATEX_RENDER,
        strategy=FallbackStrategy.LATEX_RENDER_CORRECTION,
        min_attempt=1,
        max_attempt=1,
        safe_to_apply_automatically=False,
        escalation_note=(
            "LaTeX render failures may use a deterministic render correction hook only; "
            "the policy engine must not fabricate document content."
        ),
    ),
    FallbackPolicyRule(
        stage_name=StageName.COMPILE_PDF,
        failure_type=OrchestrationFailureType.PDF_COMPILE,
        strategy=FallbackStrategy.LATEX_RENDER_CORRECTION,
        min_attempt=2,
        max_attempt=2,
        safe_to_apply_automatically=False,
        escalation_note=(
            "After one compile retry, a local render correction fallback is allowed only "
            "if a correction hook exists and preserves verified content."
        ),
    ),
)


def get_fallback_rule(
    *,
    stage_name: StageName,
    failure_type: OrchestrationFailureType,
    current_attempt: int,
) -> FallbackPolicyRule | None:
    """Return the first fallback rule matching a policy key."""

    for rule in FALLBACK_POLICY_RULES:
        if rule.matches(
            stage_name=stage_name,
            failure_type=failure_type,
            current_attempt=current_attempt,
        ):
            return rule
    return None
