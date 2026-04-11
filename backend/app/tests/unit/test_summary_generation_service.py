from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from types import SimpleNamespace

from backend.app.tests.fixtures.summary_generation_cases import (
    backend_senior_ic_case,
    data_role_case,
    frontend_lead_case,
    management_role_case,
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


def test_summary_is_role_specific_for_backend_senior_ic() -> None:
    service = SummaryGenerationService(
        client=_FakeClient(
            [
                '{"summary_text":"Backend engineer with experience building Python APIs and improving reliability on AWS.","evidence_ids_used":["ev.backend.1"],"themes_used":["backend APIs","reliability"]}'
            ]
        ),
        model="test-model",
        prompt_template="summary prompt",
    )

    result = service.generate(backend_senior_ic_case())

    assert "backend engineer" in result.summary_text.casefold()
    assert "python" in result.summary_text.casefold()
    assert result.evidence_ids_used == ["ev.backend.1"]
    assert result.themes_used == ["backend APIs", "reliability"]


def test_summary_is_role_specific_for_frontend_lead() -> None:
    service = SummaryGenerationService(
        client=_FakeClient(
            [
                '{"summary_text":"Frontend engineer lead with experience in React and TypeScript, focused on design systems and frontend architecture.","evidence_ids_used":["ev.frontend.1"],"themes_used":["design systems","frontend architecture"]}'
            ]
        ),
        model="test-model",
        prompt_template="summary prompt",
    )

    result = service.generate(frontend_lead_case())

    assert "frontend" in result.summary_text.casefold()
    assert "lead" in result.summary_text.casefold()
    assert "design systems" in result.summary_text.casefold()


def test_summary_is_grounded_and_short_for_data_role() -> None:
    service = SummaryGenerationService(
        client=_FakeClient(
            [
                '{"summary_text":"Data engineer with experience in Python and Snowflake, focused on data pipelines and etl.","evidence_ids_used":["ev.data.1"],"themes_used":["data pipelines","etl"]}'
            ]
        ),
        model="test-model",
        prompt_template="summary prompt",
    )

    result = service.generate(data_role_case())

    assert "data engineer" in result.summary_text.casefold()
    assert "snowflake" in result.summary_text.casefold()
    assert len(result.summary_text.split()) <= 20
    assert not result.quality_signals.hard_failures


def test_management_summary_respects_organizational_mode() -> None:
    service = SummaryGenerationService(
        client=_FakeClient(
            [
                '{"summary_text":"Engineering manager with experience in Python and AWS, focused on platform reliability and supported leadership work.","evidence_ids_used":["ev.mgmt.1"],"themes_used":["platform reliability"]}'
            ]
        ),
        model="test-model",
        prompt_template="summary prompt",
    )

    result = service.generate(management_role_case())

    assert "engineering manager" in result.summary_text.casefold()
    assert "leadership" in result.summary_text.casefold()


def test_generic_or_unsupported_summary_falls_back_to_safe_summary() -> None:
    service = SummaryGenerationService(
        client=_FakeClient(
            [
                '{"summary_text":"Results-driven dynamic professional with a proven track record leading global teams for 10 years.","evidence_ids_used":["ev.backend.1"],"themes_used":["reliability"]}'
            ]
        ),
        model="test-model",
        prompt_template="summary prompt",
    )

    result = service.generate(backend_senior_ic_case())

    assert "results-driven" not in result.summary_text.casefold()
    assert "dynamic professional" not in result.summary_text.casefold()
    assert "10 years" not in result.summary_text.casefold()
    assert result.warnings
    assert "backend engineer" in result.summary_text.casefold()
