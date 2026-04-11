"""Deterministic factual validators for the Phase 6 verification gate.

These validators inspect generated content against source truth, provenance,
and the selected Phase 3 context without LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.schemas.verification import VerificationIssue
from backend.app.services.verification.extractors import (
    detect_escalation_phrases,
    extract_configured_keywords,
    extract_configured_phrases,
    extract_named_technologies,
    extract_numeric_tokens,
    extract_unsupported_leadership_terms,
)
from backend.app.services.verification.normalization import normalize_phrase, normalize_text, phrase_in_text
from backend.app.services.verification.provenance_service import ProvenanceMatch
from backend.app.services.verification.rules import DEFAULT_RULE_SET, DeterministicRuleSet
from backend.app.services.verification.types import (
    EvidenceStrength,
    FallbackAction,
    IssueCategory,
    IssueSeverity,
)
from resume_optimizer.models import MasterProfile, ProfileItem
from resume_optimizer.phase3_models import Phase3GenerationPayload


@dataclass(frozen=True, slots=True)
class DeterministicValidationInput:
    """Input for validating one generated item against provenance-backed sources."""

    item_id: str
    item_type: str
    generated_text: str
    provenance_matches: list[ProvenanceMatch]
    source_profile: MasterProfile
    job_keywords: list[str] | None = None
    generation_payload: Phase3GenerationPayload | None = None


@dataclass(frozen=True, slots=True)
class SelectedContentContext:
    """Phase 3 selection context exposed to deterministic validators."""

    selected_skill_names: set[str]
    selected_certification_names: set[str]
    selected_project_names: set[str]
    selected_requirement_terms: set[str]

    @classmethod
    def from_generation_payload(
        cls,
        generation_payload: Phase3GenerationPayload | None,
    ) -> "SelectedContentContext":
        if generation_payload is None:
            return cls(set(), set(), set(), set())
        return cls(
            selected_skill_names={item.skill_name for item in generation_payload.matched_skills},
            selected_certification_names={
                item.name for item in generation_payload.selected_certifications
            },
            selected_project_names={item.name for item in generation_payload.selected_projects},
            selected_requirement_terms={
                *generation_payload.role_context.must_have_skills,
                *generation_payload.role_context.preferred_skills,
                *generation_payload.role_context.must_have_requirements,
                *generation_payload.role_context.preferred_requirements,
            },
        )


@dataclass(frozen=True, slots=True)
class SourceContext:
    """Source text, taxonomies, and identifiers available for one validation target."""

    text: str
    tools: set[str]
    all_skill_names: set[str]
    domain_tags: set[str]
    canonical_tags: set[str]
    certification_names: set[str]
    award_titles: set[str]
    education_honors: set[str]
    project_names: set[str]
    education_fields: set[str]
    education_degrees: set[str]
    source_item_ids: set[str]
    source_bullet_ids: set[str]

    @classmethod
    def from_profile_and_matches(
        cls,
        *,
        source_profile: MasterProfile,
        provenance_matches: list[ProvenanceMatch],
    ) -> "SourceContext":
        entity_text_by_id, bullet_text_by_id, tools_by_entity_id, tools_by_bullet_id = _index_profile(source_profile)
        source_item_ids = {match.source_entity_id for match in provenance_matches}
        source_bullet_ids = {
            match.source_bullet_id for match in provenance_matches if match.source_bullet_id is not None
        }
        texts = [entity_text_by_id[item_id] for item_id in source_item_ids if item_id in entity_text_by_id]
        texts.extend(
            bullet_text_by_id[bullet_id]
            for bullet_id in source_bullet_ids
            if bullet_id in bullet_text_by_id
        )
        tools: set[str] = set()
        for item_id in source_item_ids:
            tools.update(tools_by_entity_id.get(item_id, set()))
        for bullet_id in source_bullet_ids:
            tools.update(tools_by_bullet_id.get(bullet_id, set()))
        matched_items = _profile_items_by_ids(source_profile, source_item_ids)
        return cls(
            text=" ".join(texts),
            tools=tools,
            all_skill_names={skill.name for skill in source_profile.skills},
            domain_tags={tag for item in matched_items for tag in item.domain_tags},
            canonical_tags={tag for item in matched_items for tag in item.canonical_tags},
            certification_names={
                entry.name for entry in source_profile.certifications if entry.id in source_item_ids
            },
            award_titles={entry.title for entry in source_profile.awards if entry.id in source_item_ids},
            education_honors={
                honor
                for entry in source_profile.education
                if entry.id in source_item_ids
                for honor in entry.honors
            },
            project_names={entry.name for entry in source_profile.projects if entry.id in source_item_ids},
            education_fields={
                entry.field_of_study
                for entry in source_profile.education
                if entry.id in source_item_ids and entry.field_of_study is not None
            },
            education_degrees={entry.degree for entry in source_profile.education if entry.id in source_item_ids},
            source_item_ids=source_item_ids,
            source_bullet_ids=source_bullet_ids,
        )

    @classmethod
    def from_entire_profile(cls, source_profile: MasterProfile) -> "SourceContext":
        entity_text_by_id, bullet_text_by_id, tools_by_entity_id, tools_by_bullet_id = _index_profile(source_profile)
        tools: set[str] = set()
        for values in tools_by_entity_id.values():
            tools.update(values)
        for values in tools_by_bullet_id.values():
            tools.update(values)
        all_items = _all_profile_items(source_profile)
        return cls(
            text=" ".join([*entity_text_by_id.values(), *bullet_text_by_id.values()]),
            tools=tools,
            all_skill_names={skill.name for skill in source_profile.skills},
            domain_tags={tag for item in all_items for tag in item.domain_tags},
            canonical_tags={tag for item in all_items for tag in item.canonical_tags},
            certification_names={entry.name for entry in source_profile.certifications},
            award_titles={entry.title for entry in source_profile.awards},
            education_honors={honor for entry in source_profile.education for honor in entry.honors},
            project_names={entry.name for entry in source_profile.projects},
            education_fields={
                entry.field_of_study for entry in source_profile.education if entry.field_of_study is not None
            },
            education_degrees={entry.degree for entry in source_profile.education},
            source_item_ids=set(entity_text_by_id),
            source_bullet_ids=set(bullet_text_by_id),
        )


class DeterministicValidator:
    """Run deterministic factual checks over generated resume items."""

    def __init__(self, rules: DeterministicRuleSet = DEFAULT_RULE_SET) -> None:
        self.rules = rules

    def validate_item(self, validation_input: DeterministicValidationInput) -> list[VerificationIssue]:
        """Run all deterministic validators for one generated item."""

        aggregate_context = SourceContext.from_entire_profile(validation_input.source_profile)
        matched_context = SourceContext.from_profile_and_matches(
            source_profile=validation_input.source_profile,
            provenance_matches=validation_input.provenance_matches,
        )
        selected_context = SelectedContentContext.from_generation_payload(
            validation_input.generation_payload
        )
        source_context = (
            aggregate_context
            if validation_input.item_type in {"summary", "skill_statement"}
            else matched_context
        )
        if validation_input.item_type == "skill_statement":
            return self.validate_skill_drift(validation_input, source_context, selected_context)
        issues: list[VerificationIssue] = []
        issues.extend(self.validate_numeric_claims(validation_input, source_context))
        issues.extend(self.validate_tools(validation_input, source_context))
        issues.extend(self.validate_ownership_drift(validation_input, source_context))
        issues.extend(self.validate_leadership_drift(validation_input, source_context))
        issues.extend(self.validate_scope_drift(validation_input, source_context))
        issues.extend(self.validate_certification_and_award_drift(validation_input, source_context))
        issues.extend(self.validate_domain_drift(validation_input, source_context))
        issues.extend(self.validate_keywords(validation_input, source_context))
        issues.extend(self.validate_role_inflation(validation_input, source_context))
        issues.extend(self.validate_seniority_leadership(validation_input, source_context))
        issues.extend(self.validate_skill_drift(validation_input, source_context, selected_context))
        if validation_input.item_type == "summary":
            issues.extend(
                self.validate_summary_facts(validation_input, aggregate_context, selected_context)
            )
        return issues

    def validate_numeric_claims(
        self,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        source_numbers = {token.normalized for token in extract_numeric_tokens(source_context.text)}
        issues: list[VerificationIssue] = []
        for token in extract_numeric_tokens(validation_input.generated_text):
            if token.normalized in source_numbers:
                continue
            issues.append(
                self._issue(
                    item_id=validation_input.item_id,
                    category=IssueCategory.UNSUPPORTED_METRIC,
                    severity=IssueSeverity.HIGH,
                    message=f"Generated numeric claim is not supported by provenance sources: {token.text}",
                    source_context=source_context,
                    validator_name="numeric_claim_validator",
                )
            )
        return issues

    def validate_tools(
        self,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        supported_tools = {
            token.normalized
            for token in extract_named_technologies(source_context.text, self.rules)
        } | {normalize_phrase(tool) for tool in source_context.tools}
        generated_tokens = [
            *extract_named_technologies(validation_input.generated_text, self.rules),
            *extract_configured_phrases(
                validation_input.generated_text,
                self.rules.cloud_platform_terms,
            ),
        ]
        issues: list[VerificationIssue] = []
        seen: set[str] = set()
        for token in generated_tokens:
            if token.normalized in seen:
                continue
            seen.add(token.normalized)
            if token.normalized in supported_tools:
                continue
            issues.append(
                self._issue(
                    item_id=validation_input.item_id,
                    category=IssueCategory.UNSUPPORTED_TOOL,
                    severity=IssueSeverity.HIGH,
                    message=f"Generated technology is not supported by mapped source evidence: {token.text}",
                    source_context=source_context,
                    validator_name="tool_technology_validator",
                )
            )
        return issues

    def validate_ownership_drift(
        self,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        issues: list[VerificationIssue] = []
        harmless_terms = {normalize_phrase(term) for term in self.rules.harmless_rewrite_allowlist}
        for token in extract_configured_phrases(validation_input.generated_text, self.rules.ownership_terms):
            if token.normalized in harmless_terms or self._source_supports_phrase(source_context, token.normalized):
                continue
            issues.append(
                self._issue(
                    item_id=validation_input.item_id,
                    category=IssueCategory.UNSUPPORTED_LEADERSHIP,
                    severity=IssueSeverity.HIGH,
                    message=f"Generated ownership claim is not supported by source evidence: {token.text}",
                    source_context=source_context,
                    validator_name="ownership_drift_validator",
                )
            )
        return issues

    def validate_leadership_drift(
        self,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        issues: list[VerificationIssue] = []
        for token in extract_configured_phrases(
            validation_input.generated_text,
            self.rules.leadership_drift_terms,
        ):
            if self._source_supports_phrase(source_context, token.normalized):
                continue
            issues.append(
                self._issue(
                    item_id=validation_input.item_id,
                    category=IssueCategory.UNSUPPORTED_LEADERSHIP,
                    severity=IssueSeverity.HIGH,
                    message=f"Generated leadership claim is not supported by source evidence: {token.text}",
                    source_context=source_context,
                    validator_name="leadership_drift_validator",
                )
            )
        return issues

    def validate_scope_drift(
        self,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        issues: list[VerificationIssue] = []
        for token in extract_configured_phrases(validation_input.generated_text, self.rules.scope_drift_terms):
            if self._source_supports_phrase(source_context, token.normalized):
                continue
            issues.append(
                self._issue(
                    item_id=validation_input.item_id,
                    category=IssueCategory.UNSUPPORTED_SCOPE,
                    severity=IssueSeverity.HIGH,
                    message=f"Generated scope or architecture claim is not supported by source evidence: {token.text}",
                    source_context=source_context,
                    validator_name="scope_drift_validator",
                )
            )
        return issues

    def validate_certification_and_award_drift(
        self,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        issues: list[VerificationIssue] = []
        for token in extract_configured_phrases(
            validation_input.generated_text,
            self.rules.certification_signal_terms,
        ):
            if self._source_supports_phrase(source_context, token.normalized):
                continue
            issues.append(
                self._issue(
                    item_id=validation_input.item_id,
                    category=IssueCategory.UNSUPPORTED_CERTIFICATION,
                    severity=IssueSeverity.HIGH,
                    message=f"Generated certification claim is not supported by source evidence: {token.text}",
                    source_context=source_context,
                    validator_name="certification_drift_validator",
                )
            )
        for token in extract_configured_phrases(
            validation_input.generated_text,
            self.rules.award_signal_terms,
        ):
            if self._source_supports_phrase(source_context, token.normalized):
                continue
            issues.append(
                self._issue(
                    item_id=validation_input.item_id,
                    category=IssueCategory.UNSUPPORTED_AWARD,
                    severity=(
                        IssueSeverity.MEDIUM
                        if validation_input.item_type == "summary"
                        else IssueSeverity.HIGH
                    ),
                    message=f"Generated award or prestige claim is not supported by source evidence: {token.text}",
                    source_context=source_context,
                    validator_name="certification_award_drift_validator",
                )
            )
        return issues

    def validate_domain_drift(
        self,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        issues: list[VerificationIssue] = []
        for token in extract_configured_phrases(
            validation_input.generated_text,
            self.rules.domain_expertise_terms,
        ):
            if self._source_supports_phrase(source_context, token.normalized):
                continue
            issues.append(
                self._issue(
                    item_id=validation_input.item_id,
                    category=IssueCategory.UNSUPPORTED_DOMAIN,
                    severity=IssueSeverity.HIGH,
                    message=f"Generated domain expertise claim is not supported by source evidence: {token.text}",
                    source_context=source_context,
                    validator_name="domain_drift_validator",
                )
            )
        return issues

    def validate_keywords(
        self,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        keywords = validation_input.job_keywords or []
        if not keywords:
            return []
        source_text_lower = normalize_text(source_context.text)
        explicit_skills = {normalize_phrase(skill) for skill in source_context.all_skill_names}
        issues: list[VerificationIssue] = []
        for token in extract_configured_keywords(validation_input.generated_text, keywords):
            if token.normalized in source_text_lower or token.normalized in explicit_skills:
                continue
            issues.append(
                self._issue(
                    item_id=validation_input.item_id,
                    category=IssueCategory.UNSUPPORTED_KEYWORD,
                    severity=IssueSeverity.HIGH,
                    message=f"Generated job keyword is not supported by source evidence or explicit skills: {token.text}",
                    source_context=source_context,
                    validator_name="keyword_support_validator",
                )
            )
        return issues

    def validate_role_inflation(
        self,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        issues: list[VerificationIssue] = []
        for match in detect_escalation_phrases(
            generated_text=validation_input.generated_text,
            source_text=source_context.text,
            rules=self.rules,
        ):
            issues.append(
                self._issue(
                    item_id=validation_input.item_id,
                    category=IssueCategory.UNSUPPORTED_LEADERSHIP,
                    severity=IssueSeverity.HIGH,
                    message=(
                        f"Generated role language escalates source evidence "
                        f"from {match.source_term} to {match.generated_term}."
                    ),
                    source_context=source_context,
                    validator_name="role_inflation_validator",
                )
            )
        return issues

    def validate_seniority_leadership(
        self,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
    ) -> list[VerificationIssue]:
        unsupported_terms = extract_unsupported_leadership_terms(
            generated_text=validation_input.generated_text,
            source_text=source_context.text,
            rules=self.rules,
        )
        return [
            self._issue(
                item_id=validation_input.item_id,
                category=IssueCategory.UNSUPPORTED_LEADERSHIP,
                severity=IssueSeverity.HIGH,
                message=f"Generated leadership/seniority claim is not supported by sources: {term}",
                source_context=source_context,
                validator_name="seniority_leadership_inflation_validator",
            )
            for term in unsupported_terms
        ]

    def validate_skill_drift(
        self,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
        selected_context: SelectedContentContext,
    ) -> list[VerificationIssue]:
        if validation_input.item_type != "skill_statement":
            return []
        normalized_generated = normalize_phrase(validation_input.generated_text)
        supported_skills = {
            *{normalize_phrase(skill) for skill in source_context.all_skill_names},
            *{normalize_phrase(skill) for skill in selected_context.selected_skill_names},
        }
        if normalized_generated in supported_skills:
            return []
        return [
            self._issue(
                item_id=validation_input.item_id,
                category=IssueCategory.UNSUPPORTED_CLAIM,
                severity=IssueSeverity.HIGH,
                message=f"Generated skill highlight is not supported by source evidence: {validation_input.generated_text}",
                source_context=source_context,
                validator_name="skill_drift_validator",
            )
        ]

    def validate_summary_facts(
        self,
        validation_input: DeterministicValidationInput,
        source_context: SourceContext,
        selected_context: SelectedContentContext,
    ) -> list[VerificationIssue]:
        issues: list[VerificationIssue] = []
        supported_summary_terms = {
            *{normalize_phrase(skill) for skill in selected_context.selected_skill_names},
            *{normalize_phrase(project) for project in selected_context.selected_project_names},
            *{normalize_phrase(cert) for cert in selected_context.selected_certification_names},
        }
        for token in extract_configured_phrases(
            validation_input.generated_text,
            self.rules.summary_breadth_terms,
        ):
            if self._source_supports_phrase(source_context, token.normalized):
                continue
            if token.normalized in supported_summary_terms:
                continue
            issues.append(
                self._issue(
                    item_id=validation_input.item_id,
                    category=IssueCategory.UNSUPPORTED_SCOPE,
                    severity=IssueSeverity.HIGH,
                    message=f"Summary breadth claim is unsupported by aggregate source truth: {token.text}",
                    source_context=source_context,
                    validator_name="summary_breadth_validator",
                )
            )
        unsupported_terms = extract_unsupported_leadership_terms(
            generated_text=validation_input.generated_text,
            source_text=source_context.text,
            rules=self.rules,
        )
        issues.extend(
            [
                self._issue(
                    item_id=validation_input.item_id,
                    category=IssueCategory.UNSUPPORTED_LEADERSHIP,
                    severity=IssueSeverity.HIGH,
                    message=f"Summary leadership claim is unsupported by aggregate source truth: {term}",
                    source_context=source_context,
                    validator_name="summary_fact_validator",
                )
                for term in unsupported_terms
            ]
        )
        return issues

    def _source_supports_phrase(self, source_context: SourceContext, phrase: str) -> bool:
        supported_values = {
            source_context.text,
            *source_context.tools,
            *source_context.all_skill_names,
            *source_context.domain_tags,
            *source_context.canonical_tags,
            *source_context.certification_names,
            *source_context.award_titles,
            *source_context.education_honors,
            *source_context.project_names,
            *source_context.education_fields,
            *source_context.education_degrees,
        }
        return any(phrase_in_text(value, phrase) for value in supported_values)

    def _issue(
        self,
        *,
        item_id: str,
        category: IssueCategory,
        severity: IssueSeverity,
        message: str,
        source_context: SourceContext,
        validator_name: str,
    ) -> VerificationIssue:
        return VerificationIssue(
            id=f"issue.{validator_name}.{item_id}",
            category=category,
            severity=severity,
            message=message,
            generated_item_id=item_id,
            source_item_ids=sorted(source_context.source_item_ids),
            source_bullet_ids=sorted(source_context.source_bullet_ids),
            evidence_strength=EvidenceStrength.NONE,
            suggested_fallback=FallbackAction.REQUIRE_HUMAN_REVIEW,
            validator_name=validator_name,
        )


def _index_profile(
    source_profile: MasterProfile,
) -> tuple[dict[str, str], dict[str, str], dict[str, set[str]], dict[str, set[str]]]:
    """Index source profile text and tools by entity and bullet IDs."""

    entity_text_by_id: dict[str, str] = {}
    bullet_text_by_id: dict[str, str] = {}
    tools_by_entity_id: dict[str, set[str]] = {}
    tools_by_bullet_id: dict[str, set[str]] = {}

    entity_text_by_id[source_profile.personal_profile.id] = " ".join(
        part
        for part in [
            source_profile.personal_profile.full_name,
            source_profile.personal_profile.headline,
            source_profile.personal_profile.summary,
        ]
        if part
    )
    tools_by_entity_id[source_profile.personal_profile.id] = set()

    for experience in source_profile.experience:
        entity_text_by_id[experience.id] = " ".join(
            part for part in [experience.organization, experience.title, " ".join(experience.tools)] if part
        )
        tools_by_entity_id[experience.id] = set(experience.tools)
        for bullet in experience.bullets:
            bullet_text_by_id[bullet.id] = bullet.text
            tools_by_bullet_id[bullet.id] = set(bullet.tools)

    for project in source_profile.projects:
        entity_text_by_id[project.id] = " ".join(
            part for part in [project.name, project.role, project.summary, " ".join(project.tools)] if part
        )
        tools_by_entity_id[project.id] = set(project.tools)
        for bullet in project.bullets:
            bullet_text_by_id[bullet.id] = bullet.text
            tools_by_bullet_id[bullet.id] = set(bullet.tools)

    for education in source_profile.education:
        entity_text_by_id[education.id] = " ".join(
            part
            for part in [
                education.institution,
                education.degree,
                education.field_of_study,
                " ".join(education.honors),
            ]
            if part
        )
        tools_by_entity_id[education.id] = set()
        for bullet in education.bullets:
            bullet_text_by_id[bullet.id] = bullet.text
            tools_by_bullet_id[bullet.id] = set(bullet.tools)

    for certification in source_profile.certifications:
        entity_text_by_id[certification.id] = " ".join(
            part for part in [certification.name, certification.issuer, certification.credential_id] if part
        )
        tools_by_entity_id[certification.id] = set(certification.canonical_tags)

    for award in source_profile.awards:
        entity_text_by_id[award.id] = " ".join(
            part for part in [award.title, award.awarder, award.summary] if part
        )
        tools_by_entity_id[award.id] = set()
        for bullet in award.bullets:
            bullet_text_by_id[bullet.id] = bullet.text
            tools_by_bullet_id[bullet.id] = set(bullet.tools)

    for skill in source_profile.skills:
        entity_text_by_id[skill.id] = " ".join([skill.name, skill.category, " ".join(skill.tools)])
        tools_by_entity_id[skill.id] = {skill.name, *skill.tools}

    return entity_text_by_id, bullet_text_by_id, tools_by_entity_id, tools_by_bullet_id


def _profile_items_by_ids(source_profile: MasterProfile, item_ids: set[str]) -> list[ProfileItem]:
    return [item for item in _all_profile_items(source_profile) if item.id in item_ids]


def _all_profile_items(source_profile: MasterProfile) -> list[ProfileItem]:
    return [
        source_profile.personal_profile,
        *source_profile.experience,
        *source_profile.projects,
        *source_profile.education,
        *source_profile.certifications,
        *source_profile.awards,
        *source_profile.skills,
    ]
