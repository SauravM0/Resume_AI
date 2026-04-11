# Mapping is isolated from template loading so content-to-fragment conversion can
# be tested independently from asset lookup and registry integrity checks.
# Deterministic rendering matters because Phase 4 already verified the content;
# this layer must preserve that content and ordering rather than reinterpret it.
# This is safer than letting AI emit a full final LaTeX document because every
# field is placed into known section fragments through a sanitizer-compatible
# text boundary.
"""Deterministic mapping from verified render models to LaTeX fragments."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from backend.app.models.render_models import (
    RenderBullet,
    RenderCertification,
    RenderEducation,
    RenderExperience,
    RenderJobInput,
    RenderPersonalInfo,
    RenderProject,
    RenderSectionType,
    RenderSkillGroup,
    RenderSummary,
    TemplatePlaceholder,
)

TextAdapter = Callable[[str], str]
TDisplayItem = TypeVar("TDisplayItem", bound="HasDisplayOrder")

__all__ = [
    "SectionRenderResult",
    "TextAdapter",
    "escape_latex_text",
    "format_date_range",
    "render_certifications_section",
    "render_education_section",
    "render_experience_section",
    "render_personal_info",
    "render_placeholder_fragments",
    "render_projects_section",
    "render_section_fragments",
    "render_skills_section",
    "render_summary_section",
]


class HasDisplayOrder(Protocol):
    """Structural type for render models with deterministic display ordering."""

    display_order: int


@dataclass(frozen=True, slots=True)
class SectionRenderResult:
    """Rendered fragment plus lightweight diagnostics for one resume section."""

    section_type: RenderSectionType
    placeholder: TemplatePlaceholder
    content: str
    rendered: bool
    item_count: int = 0
    bullet_count: int = 0


def render_personal_info(
    personal_info: RenderPersonalInfo,
    *,
    text_adapter: TextAdapter | None = None,
) -> str:
    """Render the resume header personal info fragment."""

    adapter = text_adapter or escape_latex_text
    lines = [
        r"\begin{center}",
        r"{\Large \textbf{" + adapter(personal_info.full_name) + r"}}",
    ]

    if personal_info.headline:
        lines.append(adapter(personal_info.headline))

    contact_parts = [
        personal_info.email,
        personal_info.phone,
        personal_info.location,
        *personal_info.links,
    ]
    contact_line = _join_inline_parts(contact_parts, adapter=adapter, separator=" | ")
    if contact_line:
        lines.append(contact_line)

    lines.append(r"\end{center}")
    return _join_block(lines)


def render_summary_section(
    summary: RenderSummary | None,
    *,
    text_adapter: TextAdapter | None = None,
) -> str:
    """Render the professional summary section, or an empty fragment."""

    if summary is None:
        return ""

    adapter = text_adapter or escape_latex_text
    return _join_block([_section_header("Summary"), adapter(summary.text)])


def render_experience_section(
    experiences: Sequence[RenderExperience],
    *,
    text_adapter: TextAdapter | None = None,
) -> str:
    """Render all experience blocks in deterministic display order."""

    ordered_experiences = _ordered_by_display_order(experiences)
    if not ordered_experiences:
        return ""

    adapter = text_adapter or escape_latex_text
    lines = [_section_header("Experience")]
    for experience in ordered_experiences:
        lines.extend(
            _render_role_block(
                primary=experience.title,
                secondary=experience.organization,
                date_range=format_date_range(
                    experience.start_date,
                    experience.end_date,
                    current=experience.current,
                ),
                location=experience.location,
                bullets=experience.bullets,
                adapter=adapter,
            )
        )

    return _join_block(lines)


def render_projects_section(
    projects: Sequence[RenderProject],
    *,
    text_adapter: TextAdapter | None = None,
) -> str:
    """Render all project blocks in deterministic display order."""

    ordered_projects = _ordered_by_display_order(projects)
    if not ordered_projects:
        return ""

    adapter = text_adapter or escape_latex_text
    lines = [_section_header("Projects")]
    for project in ordered_projects:
        date_range = format_date_range(project.start_date, project.end_date)
        lines.extend(
            _render_role_block(
                primary=project.name,
                secondary=project.role,
                date_range=date_range,
                location=None,
                bullets=project.bullets,
                adapter=adapter,
            )
        )
        tools_line = _format_labeled_values("Tools", project.tools, adapter=adapter)
        if tools_line:
            lines.append(tools_line)

    return _join_block(lines)


def render_skills_section(
    skill_groups: Sequence[RenderSkillGroup],
    *,
    text_adapter: TextAdapter | None = None,
) -> str:
    """Render compact skill groups, omitting empty categories."""

    ordered_skill_groups = [
        group for group in _ordered_by_display_order(skill_groups) if group.skills
    ]
    if not ordered_skill_groups:
        return ""

    adapter = text_adapter or escape_latex_text
    lines = [_section_header("Skills")]
    for group in ordered_skill_groups:
        lines.append(_format_labeled_values(group.label, group.skills, adapter=adapter))

    return _join_block(lines)


def render_education_section(
    education_items: Sequence[RenderEducation],
    *,
    text_adapter: TextAdapter | None = None,
) -> str:
    """Render education items in ATS-safe plain section formatting."""

    ordered_items = _ordered_by_display_order(education_items)
    if not ordered_items:
        return ""

    adapter = text_adapter or escape_latex_text
    lines = [_section_header("Education")]
    for item in ordered_items:
        credential = _join_raw_parts(
            [item.degree, item.field_of_study],
            separator=", ",
        )
        date_range = format_date_range(item.start_date, item.end_date)
        lines.append(_format_heading_line(credential, date_range, adapter=adapter))
        lines.append(
            _format_secondary_line(
                item.institution,
                item.location,
                adapter=adapter,
            )
        )
        for detail in item.details:
            lines.append(adapter(detail))

    return _join_block(lines)


def render_certifications_section(
    certifications: Sequence[RenderCertification],
    *,
    text_adapter: TextAdapter | None = None,
) -> str:
    """Render certification items in ATS-safe plain section formatting."""

    ordered_items = _ordered_by_display_order(certifications)
    if not ordered_items:
        return ""

    adapter = text_adapter or escape_latex_text
    lines = [_section_header("Certifications")]
    for certification in ordered_items:
        date_text = _format_certification_dates(
            certification.issued_date,
            certification.expiration_date,
        )
        lines.append(_format_heading_line(certification.name, date_text, adapter=adapter))
        details = [certification.issuer]
        if certification.credential_id:
            details.append("Credential ID: " + certification.credential_id)
        lines.append(_join_inline_parts(details, adapter=adapter, separator=" | "))

    return _join_block(lines)


def render_section_fragments(
    render_input: RenderJobInput,
    *,
    text_adapter: TextAdapter | None = None,
) -> list[SectionRenderResult]:
    """Render all visible sections according to the input section ordering."""

    adapter = text_adapter or escape_latex_text
    rendered_by_type = {
        RenderSectionType.PERSONAL_INFO: (
            TemplatePlaceholder.PERSONAL_INFO,
            render_personal_info(render_input.personal_info, text_adapter=adapter),
            1,
            0,
        ),
        RenderSectionType.SUMMARY: (
            TemplatePlaceholder.SUMMARY_SECTION,
            render_summary_section(render_input.summary, text_adapter=adapter),
            1 if render_input.summary else 0,
            0,
        ),
        RenderSectionType.EXPERIENCE: (
            TemplatePlaceholder.EXPERIENCE_SECTION,
            render_experience_section(render_input.experiences, text_adapter=adapter),
            len(render_input.experiences),
            _count_bullets(render_input.experiences),
        ),
        RenderSectionType.PROJECTS: (
            TemplatePlaceholder.PROJECTS_SECTION,
            render_projects_section(render_input.projects, text_adapter=adapter),
            len(render_input.projects),
            _count_bullets(render_input.projects),
        ),
        RenderSectionType.SKILLS: (
            TemplatePlaceholder.SKILLS_SECTION,
            render_skills_section(render_input.skills, text_adapter=adapter),
            len(render_input.skills),
            0,
        ),
        RenderSectionType.EDUCATION: (
            TemplatePlaceholder.EDUCATION_SECTION,
            render_education_section(render_input.education, text_adapter=adapter),
            len(render_input.education),
            0,
        ),
        RenderSectionType.CERTIFICATIONS: (
            TemplatePlaceholder.CERTIFICATIONS_SECTION,
            render_certifications_section(
                render_input.certifications,
                text_adapter=adapter,
            ),
            len(render_input.certifications),
            0,
        ),
    }

    results: list[SectionRenderResult] = []
    for section in _ordered_by_display_order(render_input.sections):
        if not _is_section_visible(render_input, section.section_type, section.visible):
            continue

        placeholder, content, item_count, bullet_count = rendered_by_type[
            section.section_type
        ]
        results.append(
            SectionRenderResult(
                section_type=section.section_type,
                placeholder=placeholder,
                content=content,
                rendered=bool(content.strip()),
                item_count=item_count,
                bullet_count=bullet_count,
            )
        )

    return results


def render_placeholder_fragments(
    render_input: RenderJobInput,
    *,
    text_adapter: TextAdapter | None = None,
) -> dict[TemplatePlaceholder, str]:
    """Render a placeholder-to-fragment map for later template insertion."""

    fragments = {
        placeholder: ""
        for placeholder in TemplatePlaceholder
    }
    for result in render_section_fragments(render_input, text_adapter=text_adapter):
        fragments[result.placeholder] = result.content
    return fragments


def format_date_range(
    start_date: str | None,
    end_date: str | None,
    *,
    current: bool = False,
) -> str:
    """Format an ATS-safe date range without guessing missing dates."""

    if start_date and current:
        return f"{start_date} -- Present"
    if start_date and end_date:
        return f"{start_date} -- {end_date}"
    if start_date:
        return start_date
    if end_date:
        return end_date
    if current:
        return "Present"
    return ""


def escape_latex_text(value: str) -> str:
    """Conservatively escape common LaTeX text characters.

    This is intentionally small and replaceable. A later dedicated sanitizer
    can be passed as ``text_adapter`` without changing mapper behavior.
    """

    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in value)


def _render_role_block(
    *,
    primary: str,
    secondary: str | None,
    date_range: str,
    location: str | None,
    bullets: Sequence[RenderBullet],
    adapter: TextAdapter,
) -> list[str]:
    """Render a titled item block with optional bullets."""

    lines = [
        _format_heading_line(primary, date_range, adapter=adapter),
    ]
    secondary_line = _format_secondary_line(secondary, location, adapter=adapter)
    if secondary_line:
        lines.append(secondary_line)

    bullet_lines = _render_bullet_list(bullets, adapter=adapter)
    if bullet_lines:
        lines.extend(bullet_lines)

    return lines


def _render_bullet_list(
    bullets: Sequence[RenderBullet],
    *,
    adapter: TextAdapter,
) -> list[str]:
    """Render bullets in deterministic display order."""

    ordered_bullets = _ordered_by_display_order(bullets)
    if not ordered_bullets:
        return []

    lines = [r"\begin{itemize}"]
    for bullet in ordered_bullets:
        lines.append(r"\item " + adapter(bullet.text))
    lines.append(r"\end{itemize}")
    return lines


def _format_heading_line(
    left: str,
    right: str | None,
    *,
    adapter: TextAdapter,
) -> str:
    """Format a left/right heading line for section items."""

    safe_left = adapter(left)
    if not right:
        return r"\textbf{" + safe_left + r"}"
    return r"\textbf{" + safe_left + r"} \hfill " + adapter(right)


def _format_secondary_line(
    left: str | None,
    right: str | None,
    *,
    adapter: TextAdapter,
) -> str:
    """Format a simple secondary item line."""

    return _join_inline_parts([left, right], adapter=adapter, separator=" | ")


def _format_labeled_values(
    label: str,
    values: Sequence[str],
    *,
    adapter: TextAdapter,
) -> str:
    """Format compact label/value content such as skills or tools."""

    visible_values = [value for value in values if value]
    if not visible_values:
        return ""
    return r"\textbf{" + adapter(label) + r"}: " + ", ".join(
        adapter(value) for value in visible_values
    )


def _format_certification_dates(
    issued_date: str | None,
    expiration_date: str | None,
) -> str:
    """Format certification date metadata without adding unsupported dates."""

    if issued_date and expiration_date:
        return f"Issued {issued_date} -- Expires {expiration_date}"
    if issued_date:
        return f"Issued {issued_date}"
    if expiration_date:
        return f"Expires {expiration_date}"
    return ""


def _join_inline_parts(
    parts: Iterable[str | None],
    *,
    adapter: TextAdapter,
    separator: str,
) -> str:
    """Join non-empty text parts after applying the text adapter."""

    return separator.join(adapter(part) for part in parts if part)


def _join_raw_parts(
    parts: Iterable[str | None],
    *,
    separator: str,
) -> str:
    """Join non-empty text parts before a single later adapter call."""

    return separator.join(part for part in parts if part)


def _join_block(lines: Iterable[str]) -> str:
    """Join non-empty LaTeX lines with one trailing newline for insertion."""

    visible_lines = [line for line in lines if line]
    if not visible_lines:
        return ""
    return "\n".join(visible_lines) + "\n"


def _section_header(title: str) -> str:
    """Return a consistent unnumbered section header."""

    return r"\section*{" + title + r"}"


def _ordered_by_display_order(items: Sequence[TDisplayItem]) -> list[TDisplayItem]:
    """Return a stable copy ordered by display_order without mutating inputs.

    Pydantic validators reject duplicate display_order values in the Phase 5
    contract. The id tie-breaker is defensive only, preserving deterministic
    output if this helper is reused with looser test doubles.
    """

    return sorted(
        items,
        key=lambda item: (
            getattr(item, "display_order", 0),
            getattr(item, "id", ""),
        ),
    )


def _count_bullets(items: Sequence[object]) -> int:
    """Count bullet collections on experience-like or project-like items."""

    return sum(len(getattr(item, "bullets", [])) for item in items)


def _is_section_visible(
    render_input: RenderJobInput,
    section_type: RenderSectionType,
    default_visible: bool,
) -> bool:
    """Resolve visibility from section metadata and explicit visibility flags."""

    return render_input.section_visibility.get(section_type, default_visible)
