"""AI-backed Phase 3 service for strict JSON resume content generation."""

from __future__ import annotations

import json
from json import JSONDecodeError
import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from .config import DEFAULT_SETTINGS, Settings
from .openai_client import build_openai_client, create_json_response_text
from .phase3_headline_summary import (
    build_headline_summary_prompt_lines,
    validate_headline_and_summary,
)
from .phase3_models import (
    GenerationPreferences,
    Phase3GenerationPayload,
    Phase3GenerationResult,
)
from .phase3_output_validation import (
    Phase3ValidatedOutput,
    validate_and_finalize_phase3_output,
)
from .phase3_rewrite_policy import evaluate_bullet_rewrite
from .prompt_loader import (
    format_phase3_generation_user_prompt,
    load_phase3_generation_system_prompt,
)

if TYPE_CHECKING:
    from google.genai.client import Client as GeminiClient


logger = logging.getLogger(__name__)


class Phase3GenerationError(RuntimeError):
    """Raised when Phase 3 generation cannot produce a valid structured result."""


class MalformedPhase3GenerationJSONError(Phase3GenerationError):
    """Raised when the model response is not valid top-level JSON."""


class InvalidPhase3GenerationSchemaError(Phase3GenerationError):
    """Raised when the model response is JSON but fails Phase 3 schema validation."""


class Phase3ContentGenerationService:
    """Generate strict Phase 3 structured content from the assembled payload."""

    def __init__(
        self,
        *,
        client: GeminiClient | None = None,
        model: str | None = None,
        settings: Settings = DEFAULT_SETTINGS,
    ) -> None:
        self._client = client
        self._model = model
        self._settings = settings

    def generate(
        self,
        payload: Phase3GenerationPayload,
        *,
        generation_preferences: GenerationPreferences | None = None,
    ) -> Phase3GenerationResult:
        """Call the model and return the finalized Phase 3 result only."""

        return self.generate_with_report(
            payload,
            generation_preferences=generation_preferences,
        ).result

    def generate_with_report(
        self,
        payload: Phase3GenerationPayload,
        *,
        generation_preferences: GenerationPreferences | None = None,
    ) -> Phase3ValidatedOutput:
        """Call the model with compact payload input and validate strict JSON output."""

        system_prompt = load_phase3_generation_system_prompt()
        headline_summary_rules = "\n".join(build_headline_summary_prompt_lines(payload))
        user_prompt = (
            f"{format_phase3_generation_user_prompt(payload)}\n\n"
            f"{headline_summary_rules}"
        )
        input_messages = [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ]

        resolved_client = self._client or build_openai_client()
        resolved_model = self._model or self._settings.phase3_generation_model

        if self._settings.phase3_safe_logging_enabled:
            self._log_request_summary(payload, resolved_model)

        raw_text = self._run_generation_call(
            client=resolved_client,
            model=resolved_model,
            input_messages=input_messages,
        )
        try:
            validated_output = self._parse_validate_and_finalize(raw_text, payload)
        except MalformedPhase3GenerationJSONError:
            retry_messages = [
                *input_messages,
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Your previous response was malformed. Return one valid JSON object "
                                "that matches the output contract exactly, with no commentary."
                            ),
                        }
                    ],
                },
            ]
            retry_text = self._run_generation_call(
                client=resolved_client,
                model=resolved_model,
                input_messages=retry_messages,
            )
            try:
                validated_output = self._parse_validate_and_finalize(retry_text, payload)
            except MalformedPhase3GenerationJSONError as exc:
                raise Phase3GenerationError(
                    "Phase 3 generation returned malformed JSON twice."
                ) from exc
        result = validated_output.result
        self._validate_result_against_payload(result, payload)

        if generation_preferences is not None:
            result = result.model_copy(
                update={
                    "metadata": result.metadata.model_copy(
                        update={
                            "preferences_applied": _preferences_applied(generation_preferences)
                        }
                    )
                }
            )
            validated_output = validated_output.model_copy(update={"result": result})

        if validated_output.report.severe_failure:
            issue_messages = "; ".join(issue.message for issue in validated_output.report.issues)
            raise Phase3GenerationError(
                "Phase 3 validation encountered unrecoverable issues: "
                f"{issue_messages}"
            )

        if self._settings.phase3_safe_logging_enabled:
            self._log_response_summary(result, resolved_model)

        return validated_output

    def _run_generation_call(
        self,
        *,
        client: GeminiClient,
        model: str,
        input_messages: list[dict[str, Any]],
    ) -> str:
        try:
            return create_json_response_text(
                client=client,
                model=model,
                input_payload=input_messages,
            )
        except RuntimeError as exc:
            raise Phase3GenerationError("Phase 3 generation returned an empty response.") from exc

    def _parse_validate_and_finalize(
        self,
        raw_text: str,
        payload: Phase3GenerationPayload,
    ) -> Phase3ValidatedOutput:
        raw_payload = _parse_json_object(raw_text)
        try:
            return validate_and_finalize_phase3_output(raw_payload, payload)
        except ValidationError as exc:
            raise InvalidPhase3GenerationSchemaError(
                "Phase 3 generation returned JSON that could not be finalized into the expected schema."
            ) from exc

    def _validate_result_against_payload(
        self,
        result: Phase3GenerationResult,
        payload: Phase3GenerationPayload,
    ) -> None:
        """Reject outputs that drift outside the allowed assembled payload references."""

        validation_metadata = payload.validation_metadata
        if result.metadata.source_profile_id != validation_metadata.profile_id:
            raise Phase3GenerationError(
                "Phase 3 generation returned metadata.source_profile_id that did not match the payload."
            )
        if result.metadata.phase2_status != validation_metadata.phase2_status:
            raise Phase3GenerationError(
                "Phase 3 generation returned metadata.phase2_status that did not match the payload."
            )

        allowed_item_ids = {
            *validation_metadata.allowed_experience_ids,
            *validation_metadata.allowed_project_ids,
            *validation_metadata.allowed_certification_ids,
            *validation_metadata.allowed_skill_ids,
        }
        allowed_bullet_ids = set(validation_metadata.allowed_bullet_ids)

        for experience in result.selected_experiences:
            if experience.source_item_id not in validation_metadata.allowed_experience_ids:
                raise Phase3GenerationError(
                    f"Phase 3 generation referenced unapproved experience id: {experience.source_item_id}"
                )
            for bullet in experience.generated_bullets:
                if bullet.source_item_id != experience.source_item_id:
                    raise Phase3GenerationError(
                        "Phase 3 generation returned an experience bullet with mismatched source_item_id."
                    )
                invalid_bullets = [
                    bullet_id for bullet_id in bullet.source_bullet_ids if bullet_id not in allowed_bullet_ids
                ]
                if invalid_bullets:
                    raise Phase3GenerationError(
                        "Phase 3 generation referenced unapproved experience bullet ids: "
                        + ", ".join(invalid_bullets)
                    )
                self._validate_bullet_rewrite_against_payload(bullet, payload)

        for project in result.selected_projects:
            if project.source_item_id not in validation_metadata.allowed_project_ids:
                raise Phase3GenerationError(
                    f"Phase 3 generation referenced unapproved project id: {project.source_item_id}"
                )
            for bullet in project.generated_bullets:
                if bullet.source_item_id != project.source_item_id:
                    raise Phase3GenerationError(
                        "Phase 3 generation returned a project bullet with mismatched source_item_id."
                    )
                invalid_bullets = [
                    bullet_id for bullet_id in bullet.source_bullet_ids if bullet_id not in allowed_bullet_ids
                ]
                if invalid_bullets:
                    raise Phase3GenerationError(
                        "Phase 3 generation referenced unapproved project bullet ids: "
                        + ", ".join(invalid_bullets)
                    )
                self._validate_bullet_rewrite_against_payload(bullet, payload)

        for skill in result.skills_to_highlight:
            invalid_ids = [
                item_id
                for item_id in skill.source_item_ids
                if item_id not in validation_metadata.allowed_skill_ids
            ]
            if invalid_ids:
                raise Phase3GenerationError(
                    "Phase 3 generation referenced unapproved skill ids: "
                    + ", ".join(invalid_ids)
                )

        for text_item in [result.headline, result.summary, *result.section_emphasis]:
            if text_item is None:
                continue
            invalid_item_ids = [
                item_id for item_id in text_item.source_item_ids if item_id not in allowed_item_ids
            ]
            if invalid_item_ids:
                raise Phase3GenerationError(
                    "Phase 3 generation referenced unapproved source_item_ids: "
                    + ", ".join(invalid_item_ids)
                )
            invalid_bullet_ids = [
                bullet_id for bullet_id in text_item.source_bullet_ids if bullet_id not in allowed_bullet_ids
            ]
            if invalid_bullet_ids:
                raise Phase3GenerationError(
                    "Phase 3 generation referenced unapproved source_bullet_ids: "
                    + ", ".join(invalid_bullet_ids)
                )

        for omitted_item in result.omitted_items:
            if omitted_item.source_item_id not in allowed_item_ids:
                raise Phase3GenerationError(
                    f"Phase 3 generation referenced unapproved omitted item id: {omitted_item.source_item_id}"
                )
            invalid_bullet_ids = [
                bullet_id for bullet_id in omitted_item.source_bullet_ids if bullet_id not in allowed_bullet_ids
            ]
            if invalid_bullet_ids:
                raise Phase3GenerationError(
                    "Phase 3 generation referenced unapproved omitted bullet ids: "
                    + ", ".join(invalid_bullet_ids)
                )

        for warning in result.warnings:
            invalid_item_ids = [
                item_id for item_id in warning.source_item_ids if item_id not in allowed_item_ids
            ]
            if invalid_item_ids:
                raise Phase3GenerationError(
                    "Phase 3 generation referenced unapproved warning source_item_ids: "
                    + ", ".join(invalid_item_ids)
                )
            invalid_bullet_ids = [
                bullet_id for bullet_id in warning.source_bullet_ids if bullet_id not in allowed_bullet_ids
            ]
            if invalid_bullet_ids:
                raise Phase3GenerationError(
                    "Phase 3 generation referenced unapproved warning source_bullet_ids: "
                    + ", ".join(invalid_bullet_ids)
                )

        for assessment in validate_headline_and_summary(payload, result):
            if assessment.hard_fail:
                raise Phase3GenerationError(
                    "Phase 3 generation produced unsupported headline/summary copy: "
                    + "; ".join(issue.message for issue in assessment.issues)
                )

    def _validate_bullet_rewrite_against_payload(
        self,
        generated_bullet,
        payload: Phase3GenerationPayload,
    ) -> None:
        """Run lightweight deterministic rewrite safety checks against source bullets."""

        source_bullets_by_id = {
            bullet.id: bullet
            for section in [*payload.selected_experiences, *payload.selected_projects]
            for bullet in section.bullets
        }
        source_bullets = [
            source_bullets_by_id[bullet_id]
            for bullet_id in generated_bullet.source_bullet_ids
            if bullet_id in source_bullets_by_id
        ]
        assessment = evaluate_bullet_rewrite(
            source_bullets,
            generated_bullet.rewritten_text,
        )
        if assessment.hard_fail:
            raise Phase3GenerationError(
                "Phase 3 generation produced a rewritten bullet that violated rewrite guardrails: "
                + "; ".join(violation.message for violation in assessment.violations)
            )

    def _log_request_summary(self, payload: Phase3GenerationPayload, model: str) -> None:
        """Emit safe request telemetry without logging resume content."""

        logger.info(
            "phase3 generation requested",
            extra={
                "model": model,
                "profile_id": payload.validation_metadata.profile_id,
                "selected_experience_count": len(payload.selected_experiences),
                "selected_project_count": len(payload.selected_projects),
                "matched_skill_count": len(payload.matched_skills),
                "selected_certification_count": len(payload.selected_certifications),
                "summary_hint_count": len(payload.summary_hints),
            },
        )

    def _log_response_summary(self, result: Phase3GenerationResult, model: str) -> None:
        """Emit safe response telemetry without logging generated content."""

        logger.info(
            "phase3 generation completed",
            extra={
                "model": model,
                "profile_id": result.metadata.source_profile_id,
                "selected_experience_count": result.metadata.selected_experience_count,
                "selected_project_count": result.metadata.selected_project_count,
                "highlighted_skill_count": result.metadata.highlighted_skill_count,
                "warning_count": result.metadata.warning_count,
                "omitted_item_count": result.metadata.omitted_item_count,
            },
        )


def generate_phase3_content(
    payload: Phase3GenerationPayload,
    *,
    client: GeminiClient | None = None,
    model: str | None = None,
    settings: Settings = DEFAULT_SETTINGS,
    generation_preferences: GenerationPreferences | None = None,
) -> Phase3GenerationResult:
    """Convenience wrapper around the Phase 3 generation service."""

    service = Phase3ContentGenerationService(
        client=client,
        model=model,
        settings=settings,
    )
    return service.generate(payload, generation_preferences=generation_preferences)


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_text)
    except JSONDecodeError as exc:
        raise MalformedPhase3GenerationJSONError(
            "Phase 3 generation returned malformed JSON at "
            f"line {exc.lineno}, column {exc.colno}."
        ) from exc

    if not isinstance(payload, dict):
        raise MalformedPhase3GenerationJSONError(
            "Phase 3 generation must return a top-level JSON object."
        )
    return payload


def _preferences_applied(
    generation_preferences: GenerationPreferences,
) -> list[str]:
    applied: list[str] = []
    for field_name, value in generation_preferences.model_dump(exclude_none=True).items():
        if isinstance(value, bool):
            if value:
                applied.append(field_name)
            continue
        applied.append(field_name)
    return applied
