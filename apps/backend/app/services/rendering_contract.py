"""Public Phase 5 deterministic rendering contract.

This module intentionally contains no HTTP or database logic. It exposes the
renderer-facing Pydantic models plus pure validation helpers that later Phase 5
tasks can call before LaTeX template rendering and PDF compilation.
"""

from __future__ import annotations

from backend.app.models.render_models import (
    ArtifactKind,
    CompileResult,
    ConfidenceMetadata,
    LatexCompiler,
    LatexTemplateMetadata,
    LayoutConstraints,
    LoadedLatexTemplate,
    RenderArtifactMetadata,
    RenderBullet,
    RenderCertification,
    RenderDiagnostics,
    RenderEducation,
    RenderExperience,
    RenderFailure,
    RenderFailureSeverity,
    RenderFailureStage,
    RenderJobInput,
    RenderJobOutput,
    RenderOptions,
    RenderOutputStatus,
    RenderPersonalInfo,
    RenderProject,
    RenderSection,
    RenderSectionStats,
    RenderSectionType,
    RenderSkillGroup,
    RenderSourceProvenance,
    RenderSummary,
    RenderedLatexArtifact,
    TargetPagePolicy,
    TemplatePlaceholder,
)
from backend.app.services.verification.types import VerificationStatus

__all__ = [
    "ArtifactKind",
    "CompileResult",
    "ConfidenceMetadata",
    "LatexCompiler",
    "LatexTemplateMetadata",
    "LayoutConstraints",
    "LoadedLatexTemplate",
    "RenderArtifactMetadata",
    "RenderBullet",
    "RenderCertification",
    "RenderDiagnostics",
    "RenderEducation",
    "RenderExperience",
    "RenderFailure",
    "RenderFailureSeverity",
    "RenderFailureStage",
    "RenderJobInput",
    "RenderJobOutput",
    "RenderOptions",
    "RenderOutputStatus",
    "RenderPersonalInfo",
    "RenderProject",
    "RenderSection",
    "RenderSectionStats",
    "RenderSectionType",
    "RenderSkillGroup",
    "RenderSourceProvenance",
    "RenderSummary",
    "RenderedLatexArtifact",
    "TargetPagePolicy",
    "TemplatePlaceholder",
    "validate_display_ready_content",
    "validate_required_rendering_prerequisites",
    "validate_section_consistency",
]


def validate_section_consistency(render_input: RenderJobInput) -> list[RenderFailure]:
    """Return section-level contract failures without mutating render input."""

    failures: list[RenderFailure] = []
    section_types = {section.section_type for section in render_input.sections}
    visible_sections = [section for section in render_input.sections if section.visible]

    if len({section.display_order for section in render_input.sections}) != len(
        render_input.sections
    ):
        failures.append(
            _failure(
                code="duplicate-section-order",
                message="Sections must have unique display_order values.",
                stage=RenderFailureStage.CONTRACT_VALIDATION,
            )
        )

    if len({section.id for section in render_input.sections}) != len(render_input.sections):
        failures.append(
            _failure(
                code="duplicate-section-id",
                message="Sections must have unique ids.",
                stage=RenderFailureStage.CONTRACT_VALIDATION,
            )
        )

    if RenderSectionType.PERSONAL_INFO not in {
        section.section_type for section in visible_sections
    }:
        failures.append(
            _failure(
                code="missing-visible-personal-section",
                message="The personal_info section must be present and visible.",
                stage=RenderFailureStage.CONTRACT_VALIDATION,
                section_type=RenderSectionType.PERSONAL_INFO,
            )
        )

    for section_type, visible in render_input.section_visibility.items():
        if visible and section_type not in section_types:
            failures.append(
                _failure(
                    code=f"visible-section-missing-{section_type.value}",
                    message=(
                        f"section_visibility marks {section_type.value} visible, "
                        "but no section exists."
                    ),
                    stage=RenderFailureStage.CONTRACT_VALIDATION,
                    section_type=section_type,
                )
            )

    for section in render_input.sections:
        if len(set(section.selected_bullet_ids)) != len(section.selected_bullet_ids):
            failures.append(
                _failure(
                    code=f"duplicate-section-bullets-{section.section_type.value}",
                    message=f"{section.section_type.value} contains duplicate selected_bullet_ids.",
                    stage=RenderFailureStage.CONTRACT_VALIDATION,
                    section_id=section.id,
                    section_type=section.section_type,
                    selected_bullet_ids=section.selected_bullet_ids,
                )
            )

    return failures


def validate_required_rendering_prerequisites(render_input: RenderJobInput) -> list[RenderFailure]:
    """Return failures that should block any template rendering attempt."""

    failures: list[RenderFailure] = []

    if not render_input.template_id.strip():
        failures.append(
            _failure(
                code="missing-template-id",
                message="template_id is required before deterministic rendering.",
                stage=RenderFailureStage.CONTRACT_VALIDATION,
            )
        )

    if render_input.verified_status in {
        VerificationStatus.FAILED,
        VerificationStatus.BLOCKED,
        VerificationStatus.NEEDS_RETRY,
    }:
        failures.append(
            _failure(
                code="render-input-not-verified",
                message="Render input must be passed or passed_with_warnings before rendering.",
                stage=RenderFailureStage.CONTRACT_VALIDATION,
            )
        )

    if not render_input.personal_info.full_name.strip():
        failures.append(
            _failure(
                code="missing-full-name",
                message="personal_info.full_name is required.",
                stage=RenderFailureStage.CONTENT_VALIDATION,
                section_type=RenderSectionType.PERSONAL_INFO,
            )
        )

    if not render_input.personal_info.email.strip():
        failures.append(
            _failure(
                code="missing-email",
                message="personal_info.email is required.",
                stage=RenderFailureStage.CONTENT_VALIDATION,
                section_type=RenderSectionType.PERSONAL_INFO,
            )
        )

    return failures


def validate_display_ready_content(render_input: RenderJobInput) -> list[RenderFailure]:
    """Return content failures that would make deterministic rendering unsafe."""

    failures: list[RenderFailure] = []

    for experience in render_input.experiences:
        if not experience.bullets:
            failures.append(
                _failure(
                    code=f"experience-without-bullets-{experience.id}",
                    message=f"Experience {experience.id} has no display-ready bullets.",
                    stage=RenderFailureStage.CONTENT_VALIDATION,
                    section_type=RenderSectionType.EXPERIENCE,
                    item_id=experience.id,
                    source_ids=[experience.source_item_id],
                )
            )
        failures.extend(
            _validate_bullets_display_ready(
                bullets=experience.bullets,
                section_type=RenderSectionType.EXPERIENCE,
                item_id=experience.id,
            )
        )

    for project in render_input.projects:
        if not project.bullets:
            failures.append(
                _failure(
                    code=f"project-without-bullets-{project.id}",
                    message=f"Project {project.id} has no display-ready bullets.",
                    stage=RenderFailureStage.CONTENT_VALIDATION,
                    section_type=RenderSectionType.PROJECTS,
                    item_id=project.id,
                    source_ids=[project.source_item_id],
                )
            )
        failures.extend(
            _validate_bullets_display_ready(
                bullets=project.bullets,
                section_type=RenderSectionType.PROJECTS,
                item_id=project.id,
            )
        )

    for skill_group in render_input.skills:
        if not skill_group.skills:
            failures.append(
                _failure(
                    code=f"empty-skill-group-{skill_group.id}",
                    message=f"Skill group {skill_group.id} has no skills.",
                    stage=RenderFailureStage.CONTENT_VALIDATION,
                    section_type=RenderSectionType.SKILLS,
                    item_id=skill_group.id,
                    source_ids=skill_group.source_ids,
                )
            )

    visible_content_counts = {
        RenderSectionType.PERSONAL_INFO: 1,
        RenderSectionType.SUMMARY: 1 if render_input.summary else 0,
        RenderSectionType.EXPERIENCE: len(render_input.experiences),
        RenderSectionType.PROJECTS: len(render_input.projects),
        RenderSectionType.SKILLS: len(render_input.skills),
        RenderSectionType.EDUCATION: len(render_input.education),
        RenderSectionType.CERTIFICATIONS: len(render_input.certifications),
    }
    for section in render_input.sections:
        if section.visible and visible_content_counts[section.section_type] == 0:
            failures.append(
                _failure(
                    code=f"visible-empty-section-{section.section_type.value}",
                    message=(
                        f"Visible section {section.section_type.value} has no "
                        "display-ready content."
                    ),
                    stage=RenderFailureStage.CONTENT_VALIDATION,
                    section_id=section.id,
                    section_type=section.section_type,
                )
            )

    return failures


def _validate_bullets_display_ready(
    *,
    bullets: list[RenderBullet],
    section_type: RenderSectionType,
    item_id: str,
) -> list[RenderFailure]:
    """Validate bullet text, order, uniqueness, and provenance."""

    failures: list[RenderFailure] = []
    bullet_ids = [bullet.id for bullet in bullets]
    if len(set(bullet_ids)) != len(bullet_ids):
        failures.append(
            _failure(
                code=f"duplicate-bullet-id-{item_id}",
                    message=(
                        f"{section_type.value} item {item_id} contains "
                        "duplicate bullet ids."
                    ),
                stage=RenderFailureStage.CONTENT_VALIDATION,
                section_type=section_type,
                item_id=item_id,
                selected_bullet_ids=bullet_ids,
            )
        )

    display_orders = [bullet.display_order for bullet in bullets]
    if len(set(display_orders)) != len(display_orders):
        failures.append(
            _failure(
                code=f"duplicate-bullet-order-{item_id}",
                message=(
                    f"{section_type.value} item {item_id} contains duplicate "
                    "bullet display_order values."
                ),
                stage=RenderFailureStage.CONTENT_VALIDATION,
                section_type=section_type,
                item_id=item_id,
            )
        )

    for bullet in bullets:
        if not bullet.provenance.source_item_ids:
            failures.append(
                _failure(
                    code=f"missing-bullet-source-{bullet.id}",
                    message=f"Bullet {bullet.id} has no source_item_ids provenance.",
                    stage=RenderFailureStage.CONTENT_VALIDATION,
                    section_type=section_type,
                    item_id=bullet.id,
                    selected_bullet_ids=[bullet.id],
                )
            )

    return failures


def _failure(
    *,
    code: str,
    message: str,
    stage: RenderFailureStage,
    severity: RenderFailureSeverity = RenderFailureSeverity.ERROR,
    section_id: str | None = None,
    section_type: RenderSectionType | None = None,
    item_id: str | None = None,
    source_ids: list[str] | None = None,
    selected_bullet_ids: list[str] | None = None,
    retryable: bool = False,
) -> RenderFailure:
    """Build a render failure with stable defaults."""

    return RenderFailure(
        code=code,
        message=message,
        severity=severity,
        stage=stage,
        section_id=section_id,
        section_type=section_type,
        item_id=item_id,
        source_ids=source_ids or [],
        selected_bullet_ids=selected_bullet_ids or [],
        retryable=retryable,
    )
