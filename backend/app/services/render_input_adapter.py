"""Adapter from verified Phase 4 output to deterministic Phase 5 render input."""

from __future__ import annotations

from backend.app.models.render_models import (
    ConfidenceMetadata,
    LayoutConstraints,
    RenderBullet,
    RenderCertification,
    RenderEducation,
    RenderExperience,
    RenderJobInput,
    RenderPersonalInfo,
    RenderProject,
    RenderSection,
    RenderSectionType,
    RenderSkillGroup,
    RenderSourceProvenance,
    RenderSummary,
    TargetPagePolicy,
)
from backend.app.schemas.verification import Phase4RenderingOutput
from resume_optimizer.models import MasterProfile, PartialDate


class RenderInputAdapterError(ValueError):
    """Raised when verified content cannot be converted into render input."""


def build_render_input_from_verified_output(
    *,
    source_profile: MasterProfile,
    rendering_output: Phase4RenderingOutput,
    template_id: str,
    render_job_id: str,
) -> RenderJobInput:
    """Build a deterministic render input from verified Phase 4 content."""

    if not rendering_output.renderable:
        raise RenderInputAdapterError("verified output is not renderable")
    if rendering_output.source_profile_id != source_profile.id:
        raise RenderInputAdapterError("rendering_output source_profile_id must match source_profile.id")

    verified_result = rendering_output.verified_result
    personal_info = _build_personal_info(source_profile, verified_result)
    summary = (
        RenderSummary(
            text=verified_result.summary.text,
            provenance=RenderSourceProvenance(
                source_item_ids=verified_result.summary.source_item_ids,
                source_bullet_ids=verified_result.summary.source_bullet_ids,
                generated_item_id="summary",
            ),
            confidence=ConfidenceMetadata(
                verified_status=rendering_output.verification_report.status,
                confidence_score=verified_result.summary.confidence_score,
            ),
        )
        if verified_result.summary is not None
        else None
    )
    experiences = [
        RenderExperience(
            id=f"render.{experience.source_item_id}",
            source_item_id=experience.source_item_id,
            organization=experience.organization,
            title=experience.title,
            start_date=_date_text(experience.start_date),
            end_date=_date_text(experience.end_date),
            current=experience.current,
            bullets=[
                _render_bullet(
                    bullet,
                    index=index,
                    verified_status=rendering_output.verification_report.status,
                )
                for index, bullet in enumerate(experience.generated_bullets)
            ],
            display_order=index,
            confidence=ConfidenceMetadata(
                verified_status=rendering_output.verification_report.status,
                confidence_score=experience.confidence_score,
            ),
        )
        for index, experience in enumerate(verified_result.selected_experiences)
    ]
    projects = [
        RenderProject(
            id=f"render.{project.source_item_id}",
            source_item_id=project.source_item_id,
            name=project.name,
            role=project.role,
            start_date=_date_text(project.start_date),
            end_date=_date_text(project.end_date),
            bullets=[
                _render_bullet(
                    bullet,
                    index=index,
                    verified_status=rendering_output.verification_report.status,
                )
                for index, bullet in enumerate(project.generated_bullets)
            ],
            display_order=index,
            confidence=ConfidenceMetadata(
                verified_status=rendering_output.verification_report.status,
                confidence_score=project.confidence_score,
            ),
        )
        for index, project in enumerate(verified_result.selected_projects)
    ]
    skills = _build_skill_groups(rendering_output)
    education = _build_education(source_profile, rendering_output)
    certifications = _build_certifications(source_profile, rendering_output)
    sections = _build_sections(
        summary=summary,
        experiences=experiences,
        projects=projects,
        skills=skills,
        education=education,
        certifications=certifications,
        verified_status=rendering_output.verification_report.status,
    )

    return RenderJobInput(
        render_job_id=render_job_id,
        source_profile_id=source_profile.id,
        template_id=template_id,
        target_page_policy=TargetPagePolicy.PREFER_ONE_PAGE,
        personal_info=personal_info,
        summary=summary,
        experiences=experiences,
        projects=projects,
        skills=skills,
        education=education,
        certifications=certifications,
        sections=sections,
        section_visibility={
            section.section_type: section.visible
            for section in sections
        },
        layout_constraints=LayoutConstraints(max_pages=1),
        verified_status=rendering_output.verification_report.status,
        confidence=ConfidenceMetadata(verified_status=rendering_output.verification_report.status),
    )


def _build_personal_info(source_profile: MasterProfile, rendering_output) -> RenderPersonalInfo:
    profile = source_profile.personal_profile
    if not profile.email:
        raise RenderInputAdapterError("source profile email is required for rendering")
    links = [
        str(value)
        for value in (profile.linkedin_url, profile.github_url, profile.website_url)
        if value is not None
    ]
    headline = (
        rendering_output.headline.text
        if getattr(rendering_output, "headline", None) is not None
        else profile.headline
    )
    return RenderPersonalInfo(
        full_name=profile.full_name,
        email=profile.email,
        phone=profile.phone,
        location=profile.location,
        headline=headline,
        links=links,
        provenance=RenderSourceProvenance(source_item_ids=[profile.id]),
    )


def _render_bullet(bullet, *, index: int, verified_status) -> RenderBullet:
    return RenderBullet(
        id=bullet.id,
        text=bullet.rewritten_text,
        selected_bullet_ids=bullet.source_bullet_ids,
        provenance=RenderSourceProvenance(
            source_item_ids=[bullet.source_item_id],
            source_bullet_ids=bullet.source_bullet_ids,
            generated_item_id=bullet.id,
        ),
        display_order=index,
        confidence=ConfidenceMetadata(
            verified_status=verified_status,
            confidence_score=bullet.confidence_score,
        ),
    )


def _build_skill_groups(rendering_output: Phase4RenderingOutput) -> list[RenderSkillGroup]:
    skills = sorted(
        {skill.skill_name for skill in rendering_output.verified_result.skills_to_highlight},
        key=str.casefold,
    )
    if not skills:
        return []
    source_ids: list[str] = []
    for skill in rendering_output.verified_result.skills_to_highlight:
        source_ids.extend(skill.source_item_ids)
    return [
        RenderSkillGroup(
            id="render.skills.highlighted",
            label="Skills",
            skills=skills,
            source_ids=sorted(set(source_ids), key=str.casefold),
            display_order=0,
            confidence=ConfidenceMetadata(verified_status=rendering_output.verification_report.status),
        )
    ]


def _build_education(
    source_profile: MasterProfile,
    rendering_output: Phase4RenderingOutput,
) -> list[RenderEducation]:
    return [
        RenderEducation(
            id=f"render.{entry.id}",
            source_item_id=entry.id,
            institution=entry.institution,
            degree=entry.degree,
            field_of_study=entry.field_of_study,
            location=entry.location,
            start_date=_date_text(entry.start_date),
            end_date=_date_text(entry.end_date),
            details=entry.honors,
            display_order=index,
            confidence=ConfidenceMetadata(verified_status=rendering_output.verification_report.status),
        )
        for index, entry in enumerate(source_profile.education)
    ]


def _build_certifications(
    source_profile: MasterProfile,
    rendering_output: Phase4RenderingOutput,
) -> list[RenderCertification]:
    return [
        RenderCertification(
            id=f"render.{entry.id}",
            source_item_id=entry.id,
            name=entry.name,
            issuer=entry.issuer,
            issued_date=_date_text(entry.issue_date),
            expiration_date=_date_text(entry.expiration_date),
            credential_id=entry.credential_id,
            display_order=index,
            confidence=ConfidenceMetadata(verified_status=rendering_output.verification_report.status),
        )
        for index, entry in enumerate(source_profile.certifications)
    ]


def _build_sections(
    *,
    summary,
    experiences,
    projects,
    skills,
    education,
    certifications,
    verified_status,
) -> list[RenderSection]:
    section_specs = [
        ("section.personal", RenderSectionType.PERSONAL_INFO, "Personal Info", True),
        ("section.summary", RenderSectionType.SUMMARY, "Summary", summary is not None),
        ("section.experience", RenderSectionType.EXPERIENCE, "Experience", bool(experiences)),
        ("section.projects", RenderSectionType.PROJECTS, "Projects", bool(projects)),
        ("section.skills", RenderSectionType.SKILLS, "Skills", bool(skills)),
        ("section.education", RenderSectionType.EDUCATION, "Education", bool(education)),
        ("section.certifications", RenderSectionType.CERTIFICATIONS, "Certifications", bool(certifications)),
    ]
    return [
        RenderSection(
            id=section_id,
            section_type=section_type,
            title=title,
            visible=visible,
            display_order=index,
            verified_status=verified_status,
            confidence=ConfidenceMetadata(verified_status=verified_status),
            layout_constraints=LayoutConstraints(
                priority=90 if section_type == RenderSectionType.EXPERIENCE else 50
            ),
        )
        for index, (section_id, section_type, title, visible) in enumerate(section_specs)
    ]


def _date_text(value: PartialDate | None) -> str | None:
    if value is None:
        return None
    return value.normalized_value or value.raw_value
