from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.tests.fixtures.bullet_rewrite_cases import (
    backend_bullet_case,
    metric_bullet_case,
    vague_bullet_case,
)
from backend.app.tests.fixtures.summary_generation_cases import backend_senior_ic_case
from resume_optimizer.generation.bullet_rewrite_service import BulletRewriteService
from resume_optimizer.generation.contracts import PolicyReasonCode, PolicySignalSeverity
from resume_optimizer.generation.rewrite_policy import (
    RewritePolicyContext,
    RewritePolicyTarget,
    evaluate_rewrite_policy,
)
from resume_optimizer.generation.summary_service import SummaryGenerationService


class _FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _FakeResponses:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._outputs[min(len(self.calls) - 1, len(self._outputs) - 1)])


class _FakeClient:
    def __init__(self, outputs: list[str]) -> None:
        self.responses = _FakeResponses(outputs)


def test_metric_inflation_attempt_is_flagged() -> None:
    rewrite_input = metric_bullet_case()
    source_bullet = rewrite_input.source_bullets[0]

    evaluation = evaluate_rewrite_policy(
        RewritePolicyContext(
            target=RewritePolicyTarget.BULLET,
            section_id=rewrite_input.section_id,
            source_item_id=rewrite_input.source_item_id,
            source_bullet_ids=[source_bullet.bullet_id],
            source_text=source_bullet.text,
            candidate_text="Built Python APIs that reduced latency by 50% on AWS.",
            allowed_tools=list(source_bullet.tools),
            leadership_supported=False,
            organizational_role_mode=rewrite_input.organizational_role_mode,
        )
    )

    assert any(
        violation.reason_code == PolicyReasonCode.UNSUPPORTED_NUMBER
        and violation.policy_severity == PolicySignalSeverity.HARD_BLOCK
        for violation in evaluation.violations
    )


def test_tool_inflation_attempt_is_flagged() -> None:
    rewrite_input = metric_bullet_case()
    source_bullet = rewrite_input.source_bullets[0]

    evaluation = evaluate_rewrite_policy(
        RewritePolicyContext(
            target=RewritePolicyTarget.BULLET,
            section_id=rewrite_input.section_id,
            source_item_id=rewrite_input.source_item_id,
            source_bullet_ids=[source_bullet.bullet_id],
            source_text=source_bullet.text,
            candidate_text="Built Python APIs on AWS and Kubernetes, reducing latency by 35%.",
            allowed_tools=list(source_bullet.tools),
            leadership_supported=False,
            organizational_role_mode=rewrite_input.organizational_role_mode,
        )
    )

    assert any(
        violation.reason_code == PolicyReasonCode.UNSUPPORTED_TOOL
        and violation.policy_severity == PolicySignalSeverity.HARD_BLOCK
        for violation in evaluation.violations
    )


def test_leadership_inflation_attempt_is_flagged() -> None:
    rewrite_input = vague_bullet_case()
    source_bullet = rewrite_input.source_bullets[0]

    evaluation = evaluate_rewrite_policy(
        RewritePolicyContext(
            target=RewritePolicyTarget.BULLET,
            section_id=rewrite_input.section_id,
            source_item_id=rewrite_input.source_item_id,
            source_bullet_ids=[source_bullet.bullet_id],
            source_text=source_bullet.text,
            candidate_text="Led backend platform work across the organization.",
            leadership_supported=False,
            organizational_role_mode=rewrite_input.organizational_role_mode,
        )
    )

    assert any(
        violation.reason_code == PolicyReasonCode.LEADERSHIP_INFLATION
        and violation.policy_severity == PolicySignalSeverity.FALLBACK_TO_SOURCE
        for violation in evaluation.violations
    )


def test_summary_overclaim_attempt_triggers_fallback_and_policy_signals() -> None:
    service = SummaryGenerationService(
        client=_FakeClient(
            [
                '{"summary_text":"Fintech specialist with 10 years of experience leading Kubernetes platform teams.","evidence_ids_used":["ev.backend.1"],"themes_used":["reliability"]}'
            ]
        ),
        model="test-model",
        prompt_template="summary prompt",
    )

    result = service.generate(backend_senior_ic_case())

    assert result.summary_text != "Fintech specialist with 10 years of experience leading Kubernetes platform teams."
    assert any(
        signal.reason_code == PolicyReasonCode.UNSUPPORTED_YEARS_EXPERIENCE
        and signal.policy_severity == PolicySignalSeverity.HARD_BLOCK
        for signal in result.quality_signals.hard_failures
    )
    assert any(
        signal.reason_code == PolicyReasonCode.FAKE_SPECIALIZATION
        and signal.policy_severity == PolicySignalSeverity.REQUIRES_REGENERATION
        for signal in result.quality_signals.hard_failures
    )


def test_bullet_service_fallback_preserves_policy_reason_codes() -> None:
    service = BulletRewriteService(
        client=_FakeClient(
            [
                '{"rewritten_text":"Owned platform architecture in Python and AWS, reducing latency by 50%.","evidence_ids_used":["ev.metric.1"],"rewrite_strategy":"condensed"}'
            ]
        ),
        model="test-model",
        prompt_template="rewrite prompt",
    )

    result = service.rewrite(backend_bullet_case())[0]

    assert result.rewritten_text == "Built Python APIs that reduced latency by 35% on AWS."
    assert any(
        signal.reason_code == PolicyReasonCode.UNSUPPORTED_NUMBER
        and signal.policy_severity == PolicySignalSeverity.HARD_BLOCK
        for signal in result.rewrite_quality_signals.hard_failures
    )
    assert any(
        signal.reason_code == PolicyReasonCode.LEADERSHIP_INFLATION
        and signal.policy_severity == PolicySignalSeverity.FALLBACK_TO_SOURCE
        for signal in result.rewrite_quality_signals.hard_failures
    )


def test_valid_rewrite_passes_policy_and_keeps_candidate_text() -> None:
    service = BulletRewriteService(
        client=_FakeClient(
            [
                '{"rewritten_text":"Built Python APIs on AWS, reducing latency by 35%.","evidence_ids_used":["ev.metric.1"],"rewrite_strategy":"condensed"}'
            ]
        ),
        model="test-model",
        prompt_template="rewrite prompt",
    )

    result = service.rewrite(metric_bullet_case())[0]

    assert result.rewritten_text == "Built Python APIs on AWS, reducing latency by 35%."
    assert not any(signal.reason_code for signal in result.rewrite_quality_signals.hard_failures)
