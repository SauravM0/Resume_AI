from __future__ import annotations

from resume_optimizer.normalization import (
    infer_action_verbs_from_text,
    infer_cloud_services_from_text,
    infer_delivery_scope_phrases_from_text,
    infer_domains_from_text,
    infer_frameworks_from_text,
    infer_leadership_phrases_from_text,
    infer_ownership_phrases_from_text,
    infer_programming_languages_from_text,
    infer_stakeholder_phrases_from_text,
    infer_tool_platforms_from_text,
    normalize_action_verb,
    normalize_cloud_service,
    normalize_domain,
    normalize_evidence_text,
    normalize_framework,
    normalize_programming_language,
    normalize_title_taxonomy,
    normalize_tool_platform,
)
from resume_optimizer.normalization.models import NormalizationStatus


def test_exact_and_alias_normalization_for_core_tech_terms() -> None:
    assert normalize_tool_platform("postgres").canonical == "PostgreSQL"
    assert normalize_tool_platform("postgres").status == NormalizationStatus.ALIAS
    assert normalize_cloud_service("gcp").canonical == "Google Cloud Platform"
    assert normalize_framework("react.js").canonical == "React"
    assert normalize_programming_language("py").canonical == "Python"
    assert normalize_action_verb("refactored").canonical == "optimize"
    assert normalize_domain("health care").canonical == "healthcare"


def test_title_normalization_preserves_specificity_while_canonicalizing() -> None:
    normalized = normalize_title_taxonomy("Sr Backend Engineer")

    assert normalized.canonical == "Senior Backend Engineer"
    assert normalized.role_family == "engineering"
    assert normalized.seniority_hint == "senior"
    assert normalized.role_type_hint == "backend"


def test_phrase_and_text_inference_support_multiple_canonical_tags() -> None:
    text = (
        "Led cross-functional delivery of a customer-facing platform on AWS Lambda and S3 "
        "with React, TypeScript, PostgreSQL, and executive stakeholders."
    )
    bundle = normalize_evidence_text(text, title="Staff Platform Engineer")

    assert {term.canonical for term in bundle.cloud_services} >= {"AWS Lambda", "Amazon S3"}
    assert {term.canonical for term in bundle.frameworks_libraries} >= {"React"}
    assert {term.canonical for term in bundle.programming_languages} >= {"TypeScript"}
    assert {term.canonical for term in bundle.tool_platforms} >= {"PostgreSQL"}
    assert {term.canonical for term in bundle.leadership_phrases} >= {"cross_functional_leadership"}
    assert {term.canonical for term in bundle.delivery_scope_phrases} >= {"platform_scope", "product_scope"}
    assert {term.canonical for term in bundle.stakeholder_phrases} >= {"stakeholder_management"}


def test_text_inference_is_stable_and_non_destructive() -> None:
    raw_text = "Owned the checkout workflow and reduced p95 latency using Node.js and Redis."
    first = normalize_evidence_text(raw_text)
    second = normalize_evidence_text(raw_text)

    assert first == second
    assert first.raw_text == raw_text
    assert "Node.js" in {term.canonical for term in first.tool_platforms}
    assert "Redis" in {term.canonical for term in first.tool_platforms}
    assert "ownership" in {term.canonical for term in first.ownership_phrases}


def test_safe_fallback_behavior_keeps_unknown_terms() -> None:
    unknown_framework = normalize_framework("BespokeUI")
    unknown_language = normalize_programming_language("LangX")

    assert unknown_framework.canonical == "Bespokeui"
    assert unknown_framework.status == NormalizationStatus.PASSTHROUGH
    assert unknown_language.canonical == "Langx"
    assert unknown_language.status == NormalizationStatus.PASSTHROUGH


def test_broad_text_inference_helpers_cover_ambiguous_inputs() -> None:
    text = [
        "Mentored engineers, partnered with product and design, and rolled out an org-wide platform migration on kubernetes and ec2.",
    ]

    assert {term.canonical for term in infer_tool_platforms_from_text(text)} >= {"Kubernetes"}
    assert {term.canonical for term in infer_cloud_services_from_text(text)} >= {"Amazon EC2"}
    assert {term.canonical for term in infer_action_verbs_from_text(text)} >= {"mentor", "launch"}
    assert {term.canonical for term in infer_leadership_phrases_from_text(text)} >= {"mentorship"}
    assert {term.canonical for term in infer_ownership_phrases_from_text(text)} == set()
    assert {term.canonical for term in infer_delivery_scope_phrases_from_text(text)} >= {"platform_scope", "organizational_scope"}
    assert {term.canonical for term in infer_stakeholder_phrases_from_text(text)} >= {"cross_functional_collaboration"}
    assert {term.canonical for term in infer_domains_from_text(text)} >= {"platform"}
    assert {term.canonical for term in infer_frameworks_from_text(["Built a FastAPI service."])} >= {"FastAPI"}
    assert {term.canonical for term in infer_programming_languages_from_text(["Python and SQL automation"])} >= {"Python", "SQL"}
