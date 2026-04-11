from __future__ import annotations

from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.services.verification.provenance_service import ProvenanceMatch
from backend.app.services.verification.semantic_validator import (
    MalformedSemanticResponseError,
    OverclaimDimension,
    SemanticValidationInput,
    SemanticValidatorService,
    SemanticVerdict,
)
from backend.app.services.verification.types import (
    EvidenceStrength,
    IssueCategory,
    IssueSeverity,
    ProvenanceRelationType,
)
from resume_optimizer.models import ItemType
from resume_optimizer.phase3_models import SupportLevel


class _FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _FakeResponses:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        output = self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]
        return _FakeResponse(output)


class _FakeClient:
    def __init__(self, outputs: list[str]) -> None:
        self.responses = _FakeResponses(outputs)


def _match() -> ProvenanceMatch:
    return ProvenanceMatch(
        generated_item_key="gen.bullet.semantic",
        generated_item_type="experience_bullet",
        generated_text="Built Python APIs for internal platform workflows.",
        source_entity_type=ItemType.EXPERIENCE,
        source_entity_id="exp.platform",
        source_bullet_id="bullet.platform.1",
        relation_type=ProvenanceRelationType.DIRECT_REWRITE,
        evidence_strength=EvidenceStrength.STRONG,
        matched_tokens=["built", "python", "apis"],
        source_span_json={
            "text": "Built Python APIs for internal platform workflows.",
            "matched_tokens": ["built", "python", "apis"],
        },
        support_level=SupportLevel.DIRECT,
    )


def _validation_input(text: str = "Built Python APIs for internal platform workflows.") -> SemanticValidationInput:
    return SemanticValidationInput(
        item_id="gen.bullet.semantic",
        item_type="experience_bullet",
        generated_text=text,
        provenance_matches=[_match()],
    )


def test_schema_parsing_accepts_strict_pass_response() -> None:
    response = SemanticValidatorService(prompt_template="prompt").parse_response(
        '{"verdict":"pass","confidence":0.93,"issue_category":null,'
        '"explanation":"The generated statement is faithful.",'
        '"overclaim_dimensions":[]}'
    )

    assert response.verdict is SemanticVerdict.PASS
    assert response.confidence == 0.93


def test_schema_parsing_rejects_extra_fields() -> None:
    with pytest.raises(MalformedSemanticResponseError):
        SemanticValidatorService(prompt_template="prompt").parse_response(
            '{"verdict":"pass","confidence":0.93,"issue_category":null,'
            '"explanation":"Faithful.","overclaim_dimensions":[],"rewrite":"Use this."}'
        )


def test_malformed_response_retries_and_returns_pass_result() -> None:
    client = _FakeClient(
        [
            "not-json",
            '{"verdict":"pass","confidence":0.88,"issue_category":null,'
            '"explanation":"Supported paraphrase.","overclaim_dimensions":[]}',
        ]
    )
    service = SemanticValidatorService(
        client=client,
        model="test-model",
        prompt_template="judge only",
    )

    result = service.validate_item(_validation_input())

    assert result.response.verdict is SemanticVerdict.PASS
    assert result.issues == []
    assert len(client.responses.calls) == 2
    assert client.responses.calls[0]["temperature"] == 0


def test_fail_response_maps_to_structured_issue() -> None:
    client = _FakeClient(
        [
            '{"verdict":"fail","confidence":0.91,'
            '"issue_category":"unsupported_scope",'
            '"explanation":"Generated text overstates platform-wide ownership.",'
            '"overclaim_dimensions":["ownership_inflation"]}'
        ]
    )
    service = SemanticValidatorService(
        client=client,
        model="test-model",
        prompt_template="judge only",
    )

    result = service.validate_item(
        _validation_input("Owned the entire platform strategy for all engineering teams.")
    )

    assert result.response.verdict is SemanticVerdict.FAIL
    assert result.response.overclaim_dimensions == [OverclaimDimension.OWNERSHIP_INFLATION]
    assert len(result.issues) == 1
    assert result.issues[0].category is IssueCategory.UNSUPPORTED_SCOPE
    assert result.issues[0].severity is IssueSeverity.HIGH
    assert result.issues[0].source_bullet_ids == ["bullet.platform.1"]


def test_weak_support_response_maps_to_warning() -> None:
    client = _FakeClient(
        [
            '{"verdict":"weak_support","confidence":0.64,'
            '"issue_category":"provenance_weak",'
            '"explanation":"The evidence is related but indirect.",'
            '"overclaim_dimensions":["summary_overreach"]}'
        ]
    )
    service = SemanticValidatorService(
        client=client,
        model="test-model",
        prompt_template="judge only",
    )

    result = service.validate_item(_validation_input("Backend engineer with broad platform experience."))

    assert result.response.verdict is SemanticVerdict.WEAK_SUPPORT
    assert result.issues[0].severity is IssueSeverity.MEDIUM
    assert result.issues[0].category is IssueCategory.PROVENANCE_WEAK


def test_prompt_packages_generated_text_source_evidence_and_schema() -> None:
    prompt = SemanticValidatorService(prompt_template="base prompt").build_prompt(
        _validation_input()
    )

    assert "base prompt" in prompt
    assert "Built Python APIs for internal platform workflows." in prompt
    assert "bullet.platform.1" in prompt
    assert "output_schema" in prompt
    assert "must_not_rewrite" in prompt
