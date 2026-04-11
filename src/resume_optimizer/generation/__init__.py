"""Bounded generation contracts and mappers."""

from .contracts import (
    BulletRewriteInput,
    BulletRewriteOutput,
    FullGenerationContext,
    GenerationQualitySignals,
    PageConstraints,
    SectionAssemblyInput,
    SectionAssemblyOutput,
    SkillPresentationInput,
    SkillPresentationOutput,
    StoryStrategy,
    StylePolicy,
    SummaryGenerationInput,
    SummaryGenerationOutput,
)
from .mappers import (
    build_bullet_rewrite_inputs,
    build_full_generation_context,
    build_section_assembly_input,
    build_skill_presentation_input,
    build_summary_generation_input,
)
from .bullet_rewrite_service import BulletRewriteError, BulletRewriteService
from .rewrite_policy import (
    RewritePolicyContext,
    RewritePolicyEvaluation,
    RewritePolicyTarget,
    evaluate_rewrite_policy,
)
from .quality_validator import (
    merge_quality_signals,
    validate_bullet_outputs_quality,
    validate_generation_quality,
    validate_section_assembly_quality,
    validate_skill_presentation_quality,
    validate_summary_quality,
)
from .role_style_policy import RoleStylePolicy, neutral_role_style_policy, resolve_role_style_policy
from .skill_presentation_service import present_skills
from .section_assembly_service import SectionAssemblyService
from .section_budget import BulletBudgetTracker, resolve_total_bullet_budget
from .summary_service import SummaryGenerationError, SummaryGenerationService

__all__ = [
    "BulletRewriteInput",
    "BulletRewriteOutput",
    "BulletRewriteError",
    "BulletRewriteService",
    "evaluate_rewrite_policy",
    "FullGenerationContext",
    "GenerationQualitySignals",
    "PageConstraints",
    "RoleStylePolicy",
    "RewritePolicyContext",
    "RewritePolicyEvaluation",
    "RewritePolicyTarget",
    "SectionAssemblyInput",
    "SectionAssemblyOutput",
    "SkillPresentationInput",
    "SkillPresentationOutput",
    "present_skills",
    "neutral_role_style_policy",
    "resolve_role_style_policy",
    "merge_quality_signals",
    "StoryStrategy",
    "StylePolicy",
    "SummaryGenerationInput",
    "SummaryGenerationOutput",
    "SummaryGenerationError",
    "SummaryGenerationService",
    "validate_bullet_outputs_quality",
    "validate_generation_quality",
    "validate_section_assembly_quality",
    "validate_skill_presentation_quality",
    "validate_summary_quality",
    "build_bullet_rewrite_inputs",
    "build_full_generation_context",
    "build_section_assembly_input",
    "build_skill_presentation_input",
    "build_summary_generation_input",
    "BulletBudgetTracker",
    "resolve_total_bullet_budget",
    "SectionAssemblyService",
]
