"""Canonical constants and controlled vocabularies for Phase 0."""

from __future__ import annotations

from types import MappingProxyType

APP_NAME = "resume-optimizer"
DEFAULT_PROFILE_ENCODING = "utf-8"
MASTER_PROFILE_EXAMPLE_PATH = "data/master_profile.example.json"

# Partial dates are supported as YYYY, YYYY-MM, or YYYY-MM-DD.
DATE_PATTERN = r"^\d{4}-\d{2}(-\d{2})?$"

ROLE_TYPES: tuple[str, ...] = (
    "individual_contributor",
    "manager",
    "lead",
    "consultant",
    "founder",
    "researcher",
    "student",
    "advisor",
)

SENIORITY_LEVELS: tuple[str, ...] = (
    "intern",
    "junior",
    "mid",
    "senior",
    "staff",
    "principal",
    "director",
    "executive",
)

EMPLOYMENT_TYPES: tuple[str, ...] = (
    "full_time",
    "part_time",
    "contract",
    "freelance",
    "internship",
    "temporary",
    "apprenticeship",
)

IMPACT_LEVELS: tuple[str, ...] = (
    "low",
    "medium",
    "high",
    "exceptional",
)

EVIDENCE_STRENGTHS: tuple[str, ...] = (
    "weak",
    "moderate",
    "strong",
    "verified",
)

VALIDATION_SEVERITIES: tuple[str, ...] = (
    "error",
    "warning",
    "info",
)

# Alias maps are explicit and conservative so future phases can audit why a value changed.
SKILL_ALIASES = MappingProxyType(
    {
        "js": "JavaScript",
        "javascript": "JavaScript",
        "ts": "TypeScript",
        "typescript": "TypeScript",
        "node": "Node.js",
        "nodejs": "Node.js",
        "node.js": "Node.js",
        "postgres": "PostgreSQL",
        "postgresql": "PostgreSQL",
        "py": "Python",
        "golang": "Go",
        "gcp": "Google Cloud Platform",
        "aws": "AWS",
    }
)

TITLE_ALIASES = MappingProxyType(
    {
        "sr": "Senior",
        "sr.": "Senior",
        "jr": "Junior",
        "jr.": "Junior",
        "swe": "Software Engineer",
        "pm": "Product Manager",
        "eng": "Engineer",
        "mgr": "Manager",
    }
)

ROLE_TYPE_ALIASES = MappingProxyType(
    {
        "ic": "individual_contributor",
        "individual contributor": "individual_contributor",
        "manager": "manager",
        "people manager": "manager",
        "lead": "lead",
        "tech lead": "lead",
        "team lead": "lead",
        "consultant": "consultant",
        "founder": "founder",
        "cofounder": "founder",
        "researcher": "researcher",
        "student": "student",
        "advisor": "advisor",
    }
)

SENIORITY_ALIASES = MappingProxyType(
    {
        "intern": "intern",
        "junior": "junior",
        "jr": "junior",
        "jr.": "junior",
        "mid": "mid",
        "mid-level": "mid",
        "mid level": "mid",
        "senior": "senior",
        "sr": "senior",
        "sr.": "senior",
        "staff": "staff",
        "principal": "principal",
        "director": "director",
        "exec": "executive",
        "executive": "executive",
        "vp": "executive",
        "svp": "executive",
        "cxo": "executive",
        "cto": "executive",
        "ceo": "executive",
    }
)

DOMAIN_ALIASES = MappingProxyType(
    {
        "fe": "frontend",
        "front-end": "frontend",
        "front end": "frontend",
        "ui": "frontend",
        "be": "backend",
        "back-end": "backend",
        "back end": "backend",
        "api": "backend",
        "ml": "machine-learning",
        "ai": "artificial-intelligence",
        "saas": "saas",
        "b2b": "b2b",
        "b2c": "b2c",
        "fintech": "fintech",
    }
)
