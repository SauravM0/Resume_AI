"""Configurable deterministic verification rules.

Rules are centralized here so product changes can tune factual validation
without modifying validator control flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EscalationRule:
    """Disallowed generated escalation unless source evidence already supports it."""

    source_terms: tuple[str, ...]
    escalated_terms: tuple[str, ...]
    label: str


@dataclass(frozen=True, slots=True)
class DeterministicRuleSet:
    """Rule configuration for deterministic factual validators."""

    technologies: tuple[str, ...] = (
        "Airflow",
        "Angular",
        "Azure",
        "AWS",
        "BigQuery",
        "CI/CD",
        "Datadog",
        "Docker",
        "Elasticsearch",
        "FastAPI",
        "GCP",
        "GitHub Actions",
        "GraphQL",
        "Java",
        "JavaScript",
        "Kubernetes",
        "LangChain",
        "LLM",
        "Machine Learning",
        "MongoDB",
        "MySQL",
        "Next.js",
        "Node.js",
        "OpenAI",
        "PostgreSQL",
        "Python",
        "React",
        "Redis",
        "S3",
        "Snowflake",
        "Spark",
        "SQL",
        "Storybook",
        "Supabase",
        "Terraform",
        "TypeScript",
        "Vue",
    )
    cloud_platform_terms: tuple[str, ...] = (
        "AWS",
        "Azure",
        "GCP",
        "Google Cloud",
        "Amazon Web Services",
        "Kubernetes",
        "Terraform",
        "Snowflake",
        "BigQuery",
        "S3",
    )
    harmless_rewrite_allowlist: tuple[str, ...] = (
        "built",
        "build",
        "developed",
        "implemented",
        "improved",
        "improving",
        "collaborated",
        "partnered",
        "supported",
        "worked with",
        "worked on",
        "helped",
    )
    leadership_terms: tuple[str, ...] = (
        "architected",
        "architecture leadership",
        "cross-functional strategy",
        "drove",
        "led",
        "leadership",
        "mentored",
        "mentoring",
        "owned",
        "ownership",
        "people management",
        "stakeholder management",
        "strategy",
        "technical direction",
    )
    ownership_terms: tuple[str, ...] = (
        "architected",
        "drove",
        "led",
        "managed",
        "owned",
        "orchestrated",
        "spearheaded",
    )
    leadership_drift_terms: tuple[str, ...] = (
        "executive stakeholder management",
        "managed a team",
        "managed engineers",
        "mentored",
        "mentoring",
        "people management",
        "stakeholder management",
        "technical leadership",
        "technical direction",
    )
    scope_drift_terms: tuple[str, ...] = (
        "architecture",
        "architecture strategy",
        "business-critical",
        "company-wide",
        "distributed systems",
        "end-to-end ownership",
        "global scale",
        "large-scale",
        "multi-region",
        "org-wide",
        "platform strategy",
        "system design",
    )
    certification_signal_terms: tuple[str, ...] = (
        "aws certified",
        "certified",
        "certification",
        "google cloud certified",
        "microsoft certified",
    )
    award_signal_terms: tuple[str, ...] = (
        "award-winning",
        "dean's list",
        "honors",
        "scholarship",
        "top performer",
        "with distinction",
    )
    domain_expertise_terms: tuple[str, ...] = (
        "ai/ml",
        "artificial intelligence",
        "compliance",
        "distributed systems",
        "fintech",
        "healthcare",
        "machine learning",
        "payments",
        "security",
    )
    summary_breadth_terms: tuple[str, ...] = (
        "ai/ml",
        "distributed systems",
        "full-stack",
        "people management",
        "platform",
    )
    escalation_rules: tuple[EscalationRule, ...] = field(
        default_factory=lambda: (
            EscalationRule(("implemented",), ("led",), "implemented_to_led"),
            EscalationRule(("contributed",), ("owned",), "contributed_to_owned"),
            EscalationRule(("supported",), ("drove",), "supported_to_drove"),
            EscalationRule(("assisted",), ("architected",), "assisted_to_architected"),
            EscalationRule(("built", "implemented"), ("architected",), "built_to_architected"),
            EscalationRule(("contributed", "supported"), ("managed",), "support_to_managed"),
            EscalationRule(("helped", "partnered"), ("spearheaded",), "helped_to_spearheaded"),
        )
    )


DEFAULT_RULE_SET = DeterministicRuleSet()
