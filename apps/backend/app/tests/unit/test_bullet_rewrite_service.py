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
    leadership_bullet_case,
    metric_bullet_case,
    non_metric_bullet_case,
    vague_bullet_case,
)
from resume_optimizer.generation.bullet_rewrite_service import BulletRewriteService
from resume_optimizer.phase3_models import BulletRewriteStrategy


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


def test_metric_bullet_preserves_metric_and_tools() -> None:
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

    assert "35%" in result.rewritten_text
    assert "python" in result.rewritten_text.casefold()
    assert "aws" in result.rewritten_text.casefold()
    assert result.rewrite_strategy is BulletRewriteStrategy.CONDENSED


def test_non_metric_bullet_stays_conservative() -> None:
    service = BulletRewriteService(
        client=_FakeClient(
            [
                '{"rewritten_text":"Maintained backend services for internal tooling in Python.","evidence_ids_used":["ev.nonmetric.1"],"rewrite_strategy":"light_rewrite"}'
            ]
        ),
        model="test-model",
        prompt_template="rewrite prompt",
    )

    result = service.rewrite(non_metric_bullet_case())[0]

    assert "maintained" in result.rewritten_text.casefold()
    assert "python" in result.rewritten_text.casefold()
    assert not result.rewrite_quality_signals.hard_failures


def test_vague_bullet_can_stay_close_to_source_without_inflation() -> None:
    service = BulletRewriteService(
        client=_FakeClient(
            [
                '{"rewritten_text":"Helped with backend work.","evidence_ids_used":["ev.vague.1"],"rewrite_strategy":"light_rewrite"}'
            ]
        ),
        model="test-model",
        prompt_template="rewrite prompt",
    )

    result = service.rewrite(vague_bullet_case())[0]

    assert "helped" in result.rewritten_text.casefold()
    assert "led" not in result.rewritten_text.casefold()


def test_role_specific_phrasing_improves_for_frontend_and_devops() -> None:
    frontend_service = BulletRewriteService(
        client=_FakeClient(
            [
                '{"rewritten_text":"Led design system work in React and TypeScript for the web app.","evidence_ids_used":["ev.frontend.1"],"rewrite_strategy":"light_rewrite"}'
            ]
        ),
        model="test-model",
        prompt_template="rewrite prompt",
    )
    devops_service = BulletRewriteService(
        client=_FakeClient(
            [
                '{"rewritten_text":"Automated AWS infrastructure deployments with Terraform.","evidence_ids_used":["ev.devops.1"],"rewrite_strategy":"condensed"}'
            ]
        ),
        model="test-model",
        prompt_template="rewrite prompt",
    )

    frontend_result = frontend_service.rewrite(frontend_bullet_case())[0]
    devops_result = devops_service.rewrite(devops_bullet_case())[0]

    assert "design system" in frontend_result.rewritten_text.casefold()
    assert "react" in frontend_result.rewritten_text.casefold()
    assert "terraform" in devops_result.rewritten_text.casefold()
    assert "infrastructure" in devops_result.rewritten_text.casefold()


def test_leadership_bullet_preserves_supported_ownership_level() -> None:
    service = BulletRewriteService(
        client=_FakeClient(
            [
                '{"rewritten_text":"Managed backend engineers while improving deployment reliability.","evidence_ids_used":["ev.leadership.1"],"rewrite_strategy":"light_rewrite"}'
            ]
        ),
        model="test-model",
        prompt_template="rewrite prompt",
    )

    result = service.rewrite(leadership_bullet_case())[0]

    assert "managed" in result.rewritten_text.casefold()
    assert "owned" not in result.rewritten_text.casefold()


def test_unsupported_inflation_falls_back_to_source_text() -> None:
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
    assert result.warnings
    assert result.rewrite_strategy is BulletRewriteStrategy.LIGHT_REWRITE
