"""Role-family-specific style guidance for bounded Phase 5 generation."""

from __future__ import annotations

from ..models import NonEmptyStr, StrictModel
from ..phase1_role_modeling import FunctionalRoleFamily, OrganizationalRoleMode


class RoleStylePolicy(StrictModel):
    """Bounded style guidance derived from role family and org mode."""

    policy_id: NonEmptyStr
    policy_label: NonEmptyStr
    preferred_phrasing_patterns: list[NonEmptyStr]
    preferred_emphasis_types: list[NonEmptyStr]
    preferred_vocabulary_clusters: list[NonEmptyStr]
    discouraged_wording_patterns: list[NonEmptyStr]
    summary_tone_guidance: list[NonEmptyStr]
    bullet_rewrite_emphasis_guidance: list[NonEmptyStr]


_NEUTRAL_POLICY = RoleStylePolicy(
    policy_id="neutral",
    policy_label="Neutral Engineering",
    preferred_phrasing_patterns=[
        "use concrete role language from supported evidence",
        "prefer direct factual phrasing over brand language",
    ],
    preferred_emphasis_types=[
        "supported delivery work",
        "clear technical contribution",
    ],
    preferred_vocabulary_clusters=[
        "delivery",
        "implementation",
        "systems",
        "results",
    ],
    discouraged_wording_patterns=[
        "generic corporate adjectives",
        "unsupported specialty claims",
    ],
    summary_tone_guidance=[
        "keep tone concise and recruiter-safe",
        "sound credible rather than impressive",
    ],
    bullet_rewrite_emphasis_guidance=[
        "lead with the concrete action",
        "keep one factual claim per clause",
    ],
)

_POLICY_BY_FAMILY: dict[FunctionalRoleFamily, RoleStylePolicy] = {
    FunctionalRoleFamily.BACKEND: RoleStylePolicy(
        policy_id="backend",
        policy_label="Backend Engineering",
        preferred_phrasing_patterns=[
            "frame work around APIs, services, or backend systems when source supports it",
            "prefer reliability and data-flow language over generic shipping language",
        ],
        preferred_emphasis_types=[
            "service delivery",
            "reliability",
            "scalability",
            "data flow",
        ],
        preferred_vocabulary_clusters=[
            "apis",
            "services",
            "backend",
            "reliability",
            "scalability",
            "data flow",
            "architecture",
        ],
        discouraged_wording_patterns=[
            "ui-first phrasing",
            "generic full product ownership language",
        ],
        summary_tone_guidance=[
            "sound technically grounded and operationally credible",
            "keep focus on backend execution and system behavior",
        ],
        bullet_rewrite_emphasis_guidance=[
            "surface the system action before the outcome",
            "prefer service, API, and reliability wording when evidence supports it",
        ],
    ),
    FunctionalRoleFamily.FRONTEND: RoleStylePolicy(
        policy_id="frontend",
        policy_label="Frontend Engineering",
        preferred_phrasing_patterns=[
            "frame work around interfaces, user experience, or client performance when source supports it",
            "prefer design-system and accessibility wording over vague product polish language",
        ],
        preferred_emphasis_types=[
            "interface quality",
            "ux",
            "accessibility",
            "performance",
        ],
        preferred_vocabulary_clusters=[
            "interfaces",
            "frontend",
            "ux",
            "accessibility",
            "performance",
            "design systems",
        ],
        discouraged_wording_patterns=[
            "backend infrastructure framing",
            "generic visual flair wording",
        ],
        summary_tone_guidance=[
            "sound user-facing and implementation-aware",
            "keep emphasis on interface quality and frontend delivery",
        ],
        bullet_rewrite_emphasis_guidance=[
            "put the user-facing surface or interface first when supported",
            "prefer concise accessibility, performance, or design-system wording",
        ],
    ),
    FunctionalRoleFamily.FULLSTACK: RoleStylePolicy(
        policy_id="fullstack",
        policy_label="Full-Stack Engineering",
        preferred_phrasing_patterns=[
            "show balanced frontend and backend contribution when both are supported",
            "use end-to-end language only if the source already supports cross-surface work",
        ],
        preferred_emphasis_types=[
            "cross-stack delivery",
            "product functionality",
            "integration",
        ],
        preferred_vocabulary_clusters=[
            "full-stack",
            "frontend",
            "backend",
            "apis",
            "interfaces",
            "integration",
        ],
        discouraged_wording_patterns=[
            "single-surface specialization when evidence is broader",
            "architecture inflation",
        ],
        summary_tone_guidance=[
            "sound balanced, practical, and execution-oriented",
            "avoid overstating breadth beyond supported stack coverage",
        ],
        bullet_rewrite_emphasis_guidance=[
            "keep stack breadth explicit only when source supports both sides",
            "prefer integration wording over vague versatility claims",
        ],
    ),
    FunctionalRoleFamily.DEVOPS: RoleStylePolicy(
        policy_id="devops_platform",
        policy_label="DevOps / Platform Engineering",
        preferred_phrasing_patterns=[
            "frame work around automation, deployment, or reliability operations when source supports it",
            "prefer observability and workflow language over generic tooling language",
        ],
        preferred_emphasis_types=[
            "automation",
            "reliability",
            "deployment",
            "observability",
            "developer workflow",
        ],
        preferred_vocabulary_clusters=[
            "automation",
            "infrastructure",
            "ci/cd",
            "deployment",
            "observability",
            "reliability",
        ],
        discouraged_wording_patterns=[
            "pure product-feature framing",
            "unsupported platform ownership language",
        ],
        summary_tone_guidance=[
            "sound operationally disciplined and systems-aware",
            "keep focus on reliability and infrastructure execution",
        ],
        bullet_rewrite_emphasis_guidance=[
            "lead with the automation or reliability action",
            "surface infra or deployment context when directly supported",
        ],
    ),
    FunctionalRoleFamily.PLATFORM: RoleStylePolicy(
        policy_id="devops_platform",
        policy_label="DevOps / Platform Engineering",
        preferred_phrasing_patterns=[
            "frame work around platform enablement and internal systems when source supports it",
            "prefer workflow, tooling, and reliability language over vague enablement wording",
        ],
        preferred_emphasis_types=[
            "platform enablement",
            "developer workflow",
            "automation",
            "reliability",
        ],
        preferred_vocabulary_clusters=[
            "platform",
            "internal tooling",
            "developer workflow",
            "automation",
            "reliability",
            "deployment",
        ],
        discouraged_wording_patterns=[
            "customer-ui framing",
            "unsupported org-wide ownership language",
        ],
        summary_tone_guidance=[
            "sound infrastructure-aware and internally enabling",
            "keep focus on platform reliability and workflow support",
        ],
        bullet_rewrite_emphasis_guidance=[
            "prefer platform and workflow language when evidence supports it",
            "keep claims operational, not strategic",
        ],
    ),
    FunctionalRoleFamily.DATA: RoleStylePolicy(
        policy_id="data_analytics",
        policy_label="Data / Analytics",
        preferred_phrasing_patterns=[
            "frame work around pipelines, modeling, or analysis when source supports it",
            "prefer insight and data-movement language over generic reporting language",
        ],
        preferred_emphasis_types=[
            "pipelines",
            "modeling",
            "analysis",
            "experimentation",
            "insights",
        ],
        preferred_vocabulary_clusters=[
            "pipelines",
            "etl",
            "modeling",
            "analysis",
            "insights",
            "warehouse",
        ],
        discouraged_wording_patterns=[
            "unsupported ml-specialist phrasing",
            "generic business strategy claims",
        ],
        summary_tone_guidance=[
            "sound analytical and implementation-grounded",
            "keep focus on data systems or insight generation",
        ],
        bullet_rewrite_emphasis_guidance=[
            "lead with the data action such as built, modeled, or analyzed",
            "keep metrics and data-platform terms explicit when supported",
        ],
    ),
    FunctionalRoleFamily.ANALYTICS: RoleStylePolicy(
        policy_id="data_analytics",
        policy_label="Data / Analytics",
        preferred_phrasing_patterns=[
            "frame work around analysis, experimentation, or reporting when source supports it",
            "prefer evidence-backed insight language over vague decision support wording",
        ],
        preferred_emphasis_types=[
            "analysis",
            "insights",
            "experimentation",
            "reporting",
        ],
        preferred_vocabulary_clusters=[
            "analysis",
            "insights",
            "experimentation",
            "reporting",
            "metrics",
            "dashboards",
        ],
        discouraged_wording_patterns=[
            "unsupported data-engineering depth",
            "executive-strategy inflation",
        ],
        summary_tone_guidance=[
            "sound evidence-led and outcome-aware",
            "keep focus on credible analytical contribution",
        ],
        bullet_rewrite_emphasis_guidance=[
            "put the analytical action before the business result",
            "prefer concise experiment, insight, or reporting wording",
        ],
    ),
    FunctionalRoleFamily.PRODUCT: RoleStylePolicy(
        policy_id="product",
        policy_label="Product",
        preferred_phrasing_patterns=[
            "frame work around prioritization, roadmap, and user outcomes when source supports it",
            "prefer cross-functional delivery language over generic vision language",
        ],
        preferred_emphasis_types=[
            "prioritization",
            "roadmap",
            "user impact",
            "cross-functional delivery",
        ],
        preferred_vocabulary_clusters=[
            "roadmap",
            "prioritization",
            "outcomes",
            "user impact",
            "cross-functional",
            "delivery",
        ],
        discouraged_wording_patterns=[
            "unsupported technical specialization claims",
            "visionary fluff",
        ],
        summary_tone_guidance=[
            "sound outcome-focused and execution-aware",
            "keep claims grounded in shipped work or user impact evidence",
        ],
        bullet_rewrite_emphasis_guidance=[
            "lead with the product decision or coordination action when supported",
            "prefer outcome wording over feature-list phrasing",
        ],
    ),
}

_MANAGEMENT_POLICY = RoleStylePolicy(
    policy_id="engineering_management",
    policy_label="Engineering Management / Leadership",
    preferred_phrasing_patterns=[
        "frame work around team delivery, stakeholder alignment, and execution management when source supports it",
        "prefer team development and delivery language over generic inspiration language",
    ],
    preferred_emphasis_types=[
        "leadership",
        "team development",
        "delivery",
        "stakeholder alignment",
    ],
    preferred_vocabulary_clusters=[
        "leadership",
        "team development",
        "delivery",
        "stakeholder alignment",
        "execution",
        "roadmaps",
    ],
    discouraged_wording_patterns=[
        "heroic individual-contributor framing",
        "unsupported org-scale leadership claims",
    ],
    summary_tone_guidance=[
        "sound steady, credible, and execution-oriented",
        "avoid inspirational or visionary language unless directly supported",
    ],
    bullet_rewrite_emphasis_guidance=[
        "lead with the management or coordination action when explicitly supported",
        "keep stakeholder and team claims factual and bounded",
    ],
)


def resolve_role_style_policy(
    *,
    role_family: FunctionalRoleFamily,
    organizational_role_mode: OrganizationalRoleMode,
) -> RoleStylePolicy:
    """Resolve the bounded style policy for the given role family and org mode."""

    if organizational_role_mode in {
        OrganizationalRoleMode.PEOPLE_MANAGER,
        OrganizationalRoleMode.DIRECTOR_OR_HEAD,
    }:
        return _MANAGEMENT_POLICY
    return _POLICY_BY_FAMILY.get(role_family, _NEUTRAL_POLICY)


def neutral_role_style_policy() -> RoleStylePolicy:
    """Return the neutral fallback style policy."""

    return _NEUTRAL_POLICY
