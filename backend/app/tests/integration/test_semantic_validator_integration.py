from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.services.verification.provenance_service import ProvenanceMatch
from backend.app.services.verification.semantic_validator import (
    SemanticValidationInput,
    SemanticValidatorService,
    SemanticVerdict,
)
from backend.app.services.verification.types import (
    EvidenceStrength,
    IssueCategory,
    ProvenanceRelationType,
)
from resume_optimizer.models import ItemType
from resume_optimizer.phase3_models import SupportLevel


class _HeuristicFakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class _HeuristicResponses:
    def create(self, **kwargs):
        prompt = str(kwargs["input"])
        if "Owned the entire platform strategy" in prompt:
            return _HeuristicFakeResponse(
                '{"verdict":"fail","confidence":0.9,'
                '"issue_category":"unsupported_scope",'
                '"explanation":"The generated statement overstates ownership and strategy beyond the source evidence.",'
                '"overclaim_dimensions":["ownership_inflation","summary_overreach"]}'
            )
        return _HeuristicFakeResponse(
            '{"verdict":"pass","confidence":0.92,"issue_category":null,'
            '"explanation":"The generated statement is a supported paraphrase of the source evidence.",'
            '"overclaim_dimensions":[]}'
        )


class _HeuristicClient:
    responses = _HeuristicResponses()


def _input(text: str) -> SemanticValidationInput:
    return SemanticValidationInput(
        item_id="gen.bullet.integration",
        item_type="experience_bullet",
        generated_text=text,
        provenance_matches=[
            ProvenanceMatch(
                generated_item_key="gen.bullet.integration",
                generated_item_type="experience_bullet",
                generated_text=text,
                source_entity_type=ItemType.EXPERIENCE,
                source_entity_id="exp.platform",
                source_bullet_id="bullet.platform.1",
                relation_type=ProvenanceRelationType.DIRECT_REWRITE,
                evidence_strength=EvidenceStrength.STRONG,
                source_span_json={
                    "text": "Built Python APIs for internal platform workflows.",
                },
                support_level=SupportLevel.DIRECT,
            )
        ],
    )


def test_supported_paraphrase_pass_case() -> None:
    service = SemanticValidatorService(
        client=_HeuristicClient(),
        model="test-model",
        prompt_template="judge only",
    )

    result = service.validate_item(
        _input("Built Python APIs supporting internal platform workflows.")
    )

    assert result.response.verdict is SemanticVerdict.PASS
    assert result.issues == []


def test_unsupported_scope_inflation_case() -> None:
    service = SemanticValidatorService(
        client=_HeuristicClient(),
        model="test-model",
        prompt_template="judge only",
    )

    result = service.validate_item(
        _input("Owned the entire platform strategy for all engineering teams.")
    )

    assert result.response.verdict is SemanticVerdict.FAIL
    assert result.issues[0].category is IssueCategory.UNSUPPORTED_SCOPE
