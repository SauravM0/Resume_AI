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
    devops_bullet_case,
    frontend_bullet_case,
)
from backend.app.tests.fixtures.summary_generation_cases import (
    backend_senior_ic_case,
    frontend_lead_case,
    management_role_case,
)
from resume_optimizer.generation.bullet_rewrite_service import (
    BulletRewriteService,
    _build_support_bundle,
)
from resume_optimizer.generation.contracts import PolicyReasonCode, PolicySignalSeverity
from resume_optimizer.generation.role_style_policy import (
    neutral_role_style_policy,
    resolve_role_style_policy,
)
from resume_optimizer.generation.summary_service import SummaryGenerationService
from resume_optimizer.phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode


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


def test_summary_prompt_includes_role_specific_style_guidance() -> None:
    service = SummaryGenerationService(prompt_template="summary prompt")

    backend_input = backend_senior_ic_case()
    frontend_input = frontend_lead_case()
    management_input = management_role_case()

    backend_prompt = service.build_prompt(backend_input, service._build_signal_bundle(backend_input))
    frontend_prompt = service.build_prompt(frontend_input, service._build_signal_bundle(frontend_input))
    management_prompt = service.build_prompt(management_input, service._build_signal_bundle(management_input))

    assert '"policy_id": "backend"' in backend_prompt
    assert "reliability" in backend_prompt
    assert '"policy_id": "frontend"' in frontend_prompt
    assert "design systems" in frontend_prompt
    assert '"policy_id": "engineering_management"' in management_prompt
    assert "stakeholder alignment" in management_prompt


def test_bullet_prompt_includes_different_role_style_guidance() -> None:
    service = BulletRewriteService(prompt_template="rewrite prompt")

    backend_input = backend_bullet_case()
    frontend_input = frontend_bullet_case()
    devops_input = devops_bullet_case()

    backend_prompt = service.build_prompt(
        backend_input,
        backend_input.source_bullets[0],
        _build_support_bundle(backend_input.source_bullets[0], backend_input.evidence_unit_ids),
    )
    frontend_prompt = service.build_prompt(
        frontend_input,
        frontend_input.source_bullets[0],
        _build_support_bundle(frontend_input.source_bullets[0], frontend_input.evidence_unit_ids),
    )
    devops_prompt = service.build_prompt(
        devops_input,
        devops_input.source_bullets[0],
        _build_support_bundle(devops_input.source_bullets[0], devops_input.evidence_unit_ids),
    )

    assert '"policy_id": "backend"' in backend_prompt
    assert "apis" in backend_prompt
    assert '"policy_id": "frontend"' in frontend_prompt
    assert "accessibility" in frontend_prompt
    assert '"policy_id": "devops_platform"' in devops_prompt
    assert "observability" in devops_prompt


def test_neutral_fallback_policy_works_for_other_role_family() -> None:
    policy = resolve_role_style_policy(
        role_family=FunctionalRoleFamily.OTHER,
        organizational_role_mode=OrganizationalRoleMode.UNKNOWN,
    )

    assert policy.policy_id == neutral_role_style_policy().policy_id
    assert "concrete role language" in policy.preferred_phrasing_patterns[0]


def test_role_style_policy_does_not_override_faithfulness_guardrails() -> None:
    service = SummaryGenerationService(
        client=_FakeClient(
            [
                '{"summary_text":"Frontend specialist with 12 years of experience leading global Kubernetes migrations.","evidence_ids_used":["ev.frontend.1"],"themes_used":["design systems"]}'
            ]
        ),
        model="test-model",
        prompt_template="summary prompt",
    )

    result = service.generate(frontend_lead_case())

    assert "12 years" not in result.summary_text.casefold()
    assert "kubernetes" not in result.summary_text.casefold()
    assert any(
        signal.reason_code == PolicyReasonCode.UNSUPPORTED_YEARS_EXPERIENCE
        and signal.policy_severity == PolicySignalSeverity.HARD_BLOCK
        for signal in result.quality_signals.hard_failures
    )
