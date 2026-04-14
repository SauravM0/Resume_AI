"""JSON-backed evaluation case loading."""

from __future__ import annotations

from pathlib import Path
import json

from backend.app.evaluation.case_models import EvaluationCaseDefinition
from backend.app.evaluation.contracts import EvaluationCaseLoader
from backend.app.evaluation.enums import EvaluationPackType
from backend.app.evaluation.paths import DEFAULT_EVALUATION_FIXTURE_ROOT


class JsonEvaluationCaseLoader(EvaluationCaseLoader):
    """Load evaluation cases from repository JSON fixtures."""

    def load_case(self, path: Path) -> EvaluationCaseDefinition:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "metadata" in payload:
            return EvaluationCaseDefinition.model_validate(payload)
        raise ValueError(f"expected a single evaluation case document: {path}")

    def load_pack(
        self,
        pack_type: EvaluationPackType,
        *,
        fixture_root: Path | None = None,
    ) -> list[EvaluationCaseDefinition]:
        root = (fixture_root or DEFAULT_EVALUATION_FIXTURE_ROOT) / pack_type.value
        cases: list[EvaluationCaseDefinition] = []
        for path in sorted(root.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if "cases" in payload:
                cases.extend(EvaluationCaseDefinition.model_validate(case) for case in payload["cases"])
                continue
            cases.append(EvaluationCaseDefinition.model_validate(payload))
        return cases
