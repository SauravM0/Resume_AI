"""Deterministic extraction utilities for Phase 1 job descriptions."""

from __future__ import annotations

from collections import Counter
import re

from .models import NonEmptyStr
from .normalization import normalize_title_taxonomy
from .phase1_deterministic_canonicalizers import (
    canonicalize_action_verb,
    canonicalize_heading,
    canonicalize_requirement_text,
    canonicalize_tool_platform,
    canonicalize_work_model_signal,
    extract_explicit_domain_terms,
    extract_leadership_terms,
    extract_scope_terms,
    extract_tool_platform_terms,
    keyword_candidate_tokens,
    normalize_job_line,
)
from .phase1_deterministic_models import (
    DetectedSection,
    DeterministicFinding,
    DeterministicFindingType,
    DeterministicJobDescriptionExtraction,
    JDSectionKind,
    KeywordFrequencyFinding,
    RequirementMarkerFinding,
    RequirementStrength,
    YearsExperienceFinding,
)

_YEARS_EXPERIENCE_RE = re.compile(
    r"\b(?P<years>\d{1,2})\+?\s+years?(?:\s+of)?(?:\s+[a-zA-Z][a-zA-Z-]*){0,4}\s+experience\b",
    flags=re.IGNORECASE,
)
_WORK_MODEL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("hybrid", "hybrid"),
    ("remote", "remote"),
    ("work from home", "remote"),
    ("onsite", "onsite"),
    ("on-site", "onsite"),
    ("in office", "onsite"),
)
_EDUCATION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("bachelor", "bachelors"),
    ("bs ", "bachelors"),
    ("b.s.", "bachelors"),
    ("master", "masters"),
    ("ms ", "masters"),
    ("m.s.", "masters"),
    ("phd", "doctorate"),
    ("doctorate", "doctorate"),
    ("degree", "degree"),
    ("computer science", "computer_science"),
    ("software engineering", "software_engineering"),
)
_LEADERSHIP_PATTERNS: tuple[str, ...] = (
    "mentor",
    "coach",
    "lead",
    "manage",
    "hire",
    "staffing",
    "roadmap",
    "strategy",
    "stakeholder",
)
_SCOPE_PATTERNS: tuple[str, ...] = (
    "end-to-end",
    "multi-team",
    "cross-functional",
    "work across",
    "roadmap",
    "platform",
    "architecture",
    "organization-wide",
    "stakeholder",
)
_TITLE_LABEL_PATTERNS: tuple[str, ...] = ("job title", "title", "role")
_COMPANY_LABEL_PATTERNS: tuple[str, ...] = ("company", "about us", "about the company")
_MUST_HAVE_MARKERS: tuple[str, ...] = (
    "must have",
    "required",
    "requirements",
    "minimum qualifications",
    "basic qualifications",
    "you will need",
)
_PREFERRED_MARKERS: tuple[str, ...] = (
    "preferred",
    "preferred qualifications",
    "nice to have",
    "good to have",
)
_BONUS_MARKERS: tuple[str, ...] = ("bonus", "plus", "extra credit")
_SECTION_KIND_BY_HEADING: dict[str, JDSectionKind] = {
    "about us": JDSectionKind.COMPANY,
    "about the company": JDSectionKind.COMPANY,
    "company": JDSectionKind.COMPANY,
    "summary": JDSectionKind.SUMMARY,
    "overview": JDSectionKind.SUMMARY,
    "what you'll do": JDSectionKind.RESPONSIBILITIES,
    "what you will do": JDSectionKind.RESPONSIBILITIES,
    "responsibilities": JDSectionKind.RESPONSIBILITIES,
    "key responsibilities": JDSectionKind.RESPONSIBILITIES,
    "what we're looking for": JDSectionKind.REQUIREMENTS,
    "requirements": JDSectionKind.REQUIREMENTS,
    "minimum qualifications": JDSectionKind.QUALIFICATIONS,
    "basic qualifications": JDSectionKind.QUALIFICATIONS,
    "preferred qualifications": JDSectionKind.PREFERRED,
    "bonus points": JDSectionKind.PREFERRED,
    "benefits": JDSectionKind.BENEFITS,
}


def extract_deterministic_job_description_artifacts(
    raw_job_text: str,
) -> DeterministicJobDescriptionExtraction:
    """Build a structured deterministic extraction artifact from one raw JD."""

    normalized_lines = _normalized_lines(raw_job_text)
    sections = detect_job_description_sections(raw_job_text)
    title_candidates = detect_title_candidates(normalized_lines)
    company_candidates = detect_company_name_candidates(normalized_lines)
    years = extract_years_experience_findings(normalized_lines, sections)
    requirement_markers = extract_requirement_markers(normalized_lines, sections)
    tool_findings = extract_tool_platform_findings(normalized_lines, sections)
    repeated_keywords = extract_repeated_keywords(normalized_lines)
    action_verbs = extract_action_verb_findings(normalized_lines, sections)
    work_model = extract_work_model_findings(normalized_lines, sections)
    leadership = extract_leadership_findings(normalized_lines, sections)
    scope = extract_scope_indicator_findings(normalized_lines, sections)
    education = extract_education_requirement_findings(normalized_lines, sections)
    domains = extract_domain_findings(normalized_lines, sections)
    notes: list[str] = []
    if not title_candidates:
        notes.append("No deterministic title candidate cleared the heading/title heuristics.")
    if not sections:
        notes.append("JD section boundaries were not strongly signaled by headings.")
    if len(requirement_markers) + len(tool_findings) + len(domains) + len(work_model) <= 2:
        notes.append("Deterministic extraction found limited explicit requirement structure in this JD.")

    return DeterministicJobDescriptionExtraction(
        raw_job_text=raw_job_text.strip(),
        normalized_lines=normalized_lines,
        sections=sections,
        title_candidates=title_candidates,
        company_name_candidates=company_candidates,
        years_experience_findings=years,
        requirement_markers=requirement_markers,
        tool_platform_findings=tool_findings,
        repeated_keyword_findings=repeated_keywords,
        action_verb_findings=action_verbs,
        work_model_findings=work_model,
        leadership_findings=leadership,
        scope_indicator_findings=scope,
        education_requirement_findings=education,
        domain_findings=domains,
        extraction_notes=notes,
    )


def detect_job_description_sections(raw_job_text: str) -> list[DetectedSection]:
    """Detect section boundaries from noisy heading lines and repeated headings."""

    lines = _normalized_lines(raw_job_text)
    if not lines:
        return []

    sections: list[DetectedSection] = []
    current_heading: str | None = None
    current_kind = JDSectionKind.HEADER
    current_start = 0
    buffer: list[str] = []

    def flush(end_index: int) -> None:
        nonlocal current_heading, current_kind, current_start, buffer
        if not buffer:
            return
        sections.append(
            DetectedSection(
                id=f"section.{len(sections)}",
                kind=current_kind,
                heading=current_heading,
                line_start=current_start,
                line_end=end_index,
                text="\n".join(buffer),
                confidence=_section_confidence(current_heading, current_kind, buffer),
            )
        )
        buffer = []

    for index, line in enumerate(lines):
        heading_kind = _classify_heading(line)
        if heading_kind is not None and (index == 0 or len(line.split()) <= 6):
            flush(index - 1)
            current_heading = line
            current_kind = heading_kind
            current_start = index
            buffer = [line]
            continue
        if not buffer:
            current_start = index
        buffer.append(line)

    flush(len(lines) - 1)
    return sections


def detect_title_candidates(lines: list[str]) -> list[DeterministicFinding]:
    """Detect title candidates from the JD header and explicit title labels."""

    candidates: list[DeterministicFinding] = []
    for index, line in enumerate(lines[:6]):
        lowered = line.casefold()
        explicit_label = next((label for label in _TITLE_LABEL_PATTERNS if lowered.startswith(f"{label}:")), None)
        title_text = line.split(":", 1)[1].strip() if explicit_label and ":" in line else line
        if not _looks_like_title(title_text):
            continue
        normalized = normalize_title_taxonomy(title_text)
        confidence = 0.97 if explicit_label else 0.88 if index <= 1 else 0.72
        candidates.append(
            DeterministicFinding(
                finding_type=DeterministicFindingType.TITLE,
                value=title_text,
                canonical_value=normalized.canonical,
                source_text=line,
                line_index=index,
                confidence=confidence,
                notes=[
                    "Detected from explicit title label." if explicit_label else "Detected from early JD header lines."
                ],
            )
        )
    return _dedupe_findings(candidates)


def detect_company_name_candidates(lines: list[str]) -> list[DeterministicFinding]:
    """Detect likely company names from early header patterns."""

    candidates: list[DeterministicFinding] = []
    for index, line in enumerate(lines[:8]):
        lowered = line.casefold()
        if ":" in line and any(lowered.startswith(f"{label}:") for label in _COMPANY_LABEL_PATTERNS):
            company = line.split(":", 1)[1].strip()
            if company:
                candidates.append(
                    DeterministicFinding(
                        finding_type=DeterministicFindingType.COMPANY_NAME,
                        value=company,
                        canonical_value=company,
                        source_text=line,
                        line_index=index,
                        confidence=0.96,
                        notes=["Detected from explicit company label."],
                    )
                )
        for pattern in (
            r"^(?P<company>[A-Z][A-Za-z0-9&.,' -]{1,80})\s+is hiring\b",
            r"^join\s+(?P<company>[A-Z][A-Za-z0-9&.,' -]{1,80}?)(?:\s+as\b|$)",
            r"\bat\s+(?P<company>[A-Z][A-Za-z0-9&.,' -]{1,80})\b",
        ):
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if not match:
                continue
            company = match.group("company").strip(" ,.-")
            candidates.append(
                DeterministicFinding(
                    finding_type=DeterministicFindingType.COMPANY_NAME,
                    value=company,
                    canonical_value=company,
                    source_text=line,
                    line_index=index,
                    confidence=0.78 if pattern.startswith(r"\bat") else 0.9,
                    notes=["Detected from company-name text pattern."],
                )
            )
    return _dedupe_findings(candidates)


def extract_years_experience_findings(
    lines: list[str], sections: list[DetectedSection]
) -> list[YearsExperienceFinding]:
    """Extract explicit years-of-experience mentions with confidence heuristics."""

    findings: list[YearsExperienceFinding] = []
    for index, line in enumerate(lines):
        for match in _YEARS_EXPERIENCE_RE.finditer(line):
            years = int(match.group("years"))
            lowered = line.casefold()
            minimum_like = not any(marker in lowered for marker in _PREFERRED_MARKERS + _BONUS_MARKERS)
            findings.append(
                YearsExperienceFinding(
                    years=years,
                    source_text=line,
                    line_index=index,
                    section_id=_section_id_for_line(index, sections),
                    minimum_like=minimum_like,
                    confidence=0.92 if minimum_like else 0.72,
                )
            )
    return findings


def extract_requirement_markers(
    lines: list[str], sections: list[DetectedSection]
) -> list[RequirementMarkerFinding]:
    """Classify requirement lines as must-have, preferred, or bonus."""

    findings: list[RequirementMarkerFinding] = []
    for index, line in enumerate(lines):
        lowered = line.casefold()
        marker, strength = _classify_requirement_strength(lowered)
        if marker is None or strength is None:
            continue
        findings.append(
            RequirementMarkerFinding(
                strength=strength,
                text=line,
                canonical_text=canonicalize_requirement_text(line),
                line_index=index,
                section_id=_section_id_for_line(index, sections),
                marker_phrase=marker,
                confidence=_requirement_confidence(line, strength),
                extracted_keywords=_top_keywords_for_line(line),
            )
        )
    return findings


def extract_tool_platform_findings(
    lines: list[str], sections: list[DetectedSection]
) -> list[DeterministicFinding]:
    """Extract canonical tool/platform terms from explicit JD text."""

    findings: list[DeterministicFinding] = []
    for index, line in enumerate(lines):
        for term in extract_tool_platform_terms(line):
            findings.append(
                DeterministicFinding(
                    finding_type=DeterministicFindingType.TOOL_PLATFORM,
                    value=term,
                    canonical_value=canonicalize_tool_platform(term),
                    source_text=line,
                    line_index=index,
                    section_id=_section_id_for_line(index, sections),
                    confidence=0.8 if _section_kind_for_line(index, sections) in {
                        JDSectionKind.REQUIREMENTS,
                        JDSectionKind.PREFERRED,
                        JDSectionKind.QUALIFICATIONS,
                    } else 0.68,
                )
            )
    return _dedupe_findings(findings)


def extract_repeated_keywords(lines: list[str]) -> list[KeywordFrequencyFinding]:
    """Extract repeated normalized keywords from the JD body."""

    counter: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    for line in lines:
        tokens = keyword_candidate_tokens(line)
        for token in tokens:
            counter[token] += 1
            examples.setdefault(token, [])
            if len(examples[token]) < 3 and line not in examples[token]:
                examples[token].append(line)
    findings: list[KeywordFrequencyFinding] = []
    for keyword, count in counter.most_common():
        if count < 2:
            continue
        findings.append(
            KeywordFrequencyFinding(
                keyword=keyword,
                count=count,
                representative_texts=examples[keyword],
                confidence=min(0.95, 0.45 + count * 0.08),
            )
        )
    return findings[:25]


def extract_action_verb_findings(
    lines: list[str], sections: list[DetectedSection]
) -> list[DeterministicFinding]:
    """Extract canonical action verbs from JD lines."""

    findings: list[DeterministicFinding] = []
    for index, line in enumerate(lines):
        tokens = re.findall(r"[A-Za-z][A-Za-z-]+", line)
        for token in tokens:
            canonical = canonicalize_action_verb(token)
            if canonical == normalize_job_line(token).casefold() and canonical not in {
                "build",
                "lead",
                "optimize",
                "launch",
                "manage",
                "mentor",
                "reduce",
                "increase",
            }:
                continue
            findings.append(
                DeterministicFinding(
                    finding_type=DeterministicFindingType.ACTION_VERB,
                    value=token,
                    canonical_value=canonical,
                    source_text=line,
                    line_index=index,
                    section_id=_section_id_for_line(index, sections),
                    confidence=0.7,
                )
            )
    return _dedupe_findings(findings)


def extract_work_model_findings(
    lines: list[str], sections: list[DetectedSection]
) -> list[DeterministicFinding]:
    """Extract remote, hybrid, onsite, and related work-model signals."""

    findings: list[DeterministicFinding] = []
    for index, line in enumerate(lines):
        lowered = line.casefold()
        for pattern, canonical in _WORK_MODEL_PATTERNS:
            if pattern not in lowered:
                continue
            findings.append(
                DeterministicFinding(
                    finding_type=DeterministicFindingType.WORK_MODEL,
                    value=pattern,
                    canonical_value=canonicalize_work_model_signal(canonical),
                    source_text=line,
                    line_index=index,
                    section_id=_section_id_for_line(index, sections),
                    confidence=0.93 if canonical in {"remote", "hybrid"} else 0.86,
                )
            )
    return _dedupe_findings(findings)


def extract_leadership_findings(
    lines: list[str], sections: list[DetectedSection]
) -> list[DeterministicFinding]:
    """Extract explicit leadership or management signals."""

    findings: list[DeterministicFinding] = []
    for index, line in enumerate(lines):
        lowered = line.casefold()
        explicit_terms = extract_leadership_terms(line)
        for term in explicit_terms:
            findings.append(
                DeterministicFinding(
                    finding_type=DeterministicFindingType.LEADERSHIP,
                    value=term,
                    canonical_value=term,
                    source_text=line,
                    line_index=index,
                    section_id=_section_id_for_line(index, sections),
                    confidence=0.82,
                )
            )
        for pattern in _LEADERSHIP_PATTERNS:
            if pattern not in lowered:
                continue
            findings.append(
                DeterministicFinding(
                    finding_type=DeterministicFindingType.LEADERSHIP,
                    value=pattern,
                    canonical_value=pattern.replace(" ", "_"),
                    source_text=line,
                    line_index=index,
                    section_id=_section_id_for_line(index, sections),
                    confidence=0.74,
                )
            )
    return _dedupe_findings(findings)


def extract_scope_indicator_findings(
    lines: list[str], sections: list[DetectedSection]
) -> list[DeterministicFinding]:
    """Extract scope and cross-functional delivery indicators."""

    findings: list[DeterministicFinding] = []
    for index, line in enumerate(lines):
        explicit_terms = extract_scope_terms(line)
        for term in explicit_terms:
            findings.append(
                DeterministicFinding(
                    finding_type=DeterministicFindingType.SCOPE,
                    value=term,
                    canonical_value=term,
                    source_text=line,
                    line_index=index,
                    section_id=_section_id_for_line(index, sections),
                    confidence=0.82,
                )
            )
        lowered = line.casefold()
        for pattern in _SCOPE_PATTERNS:
            if pattern not in lowered:
                continue
            findings.append(
                DeterministicFinding(
                    finding_type=DeterministicFindingType.SCOPE,
                    value=pattern,
                    canonical_value=pattern.replace(" ", "_"),
                    source_text=line,
                    line_index=index,
                    section_id=_section_id_for_line(index, sections),
                    confidence=0.72,
                )
            )
    return _dedupe_findings(findings)


def extract_education_requirement_findings(
    lines: list[str], sections: list[DetectedSection]
) -> list[DeterministicFinding]:
    """Extract explicit education requirement markers."""

    findings: list[DeterministicFinding] = []
    for index, line in enumerate(lines):
        lowered = line.casefold()
        for pattern, canonical in _EDUCATION_PATTERNS:
            if pattern not in lowered:
                continue
            findings.append(
                DeterministicFinding(
                    finding_type=DeterministicFindingType.EDUCATION,
                    value=pattern,
                    canonical_value=canonical,
                    source_text=line,
                    line_index=index,
                    section_id=_section_id_for_line(index, sections),
                    confidence=0.9 if canonical in {"bachelors", "masters", "doctorate"} else 0.76,
                )
            )
    return _dedupe_findings(findings)


def extract_domain_findings(
    lines: list[str], sections: list[DetectedSection]
) -> list[DeterministicFinding]:
    """Extract explicit domain signals when they appear in the JD text."""

    findings: list[DeterministicFinding] = []
    for index, line in enumerate(lines):
        for term in extract_explicit_domain_terms(line):
            findings.append(
                DeterministicFinding(
                    finding_type=DeterministicFindingType.DOMAIN,
                    value=term,
                    canonical_value=term,
                    source_text=line,
                    line_index=index,
                    section_id=_section_id_for_line(index, sections),
                    confidence=0.81,
                )
            )
    return _dedupe_findings(findings)


def _normalized_lines(raw_job_text: str) -> list[str]:
    lines = [normalize_job_line(line) for line in raw_job_text.splitlines()]
    return [line for line in lines if line]


def _classify_heading(line: str) -> JDSectionKind | None:
    canonical = canonicalize_heading(line)
    return _SECTION_KIND_BY_HEADING.get(canonical)


def _section_confidence(
    heading: str | None,
    kind: JDSectionKind,
    buffer: list[str],
) -> float:
    if heading is None:
        return 0.42 if kind == JDSectionKind.HEADER else 0.35
    heading_key = canonicalize_heading(heading)
    if heading_key in _SECTION_KIND_BY_HEADING:
        return 0.95
    return 0.65


def _looks_like_title(value: str) -> bool:
    if not value or len(value) > 90:
        return False
    tokens = value.split()
    if len(tokens) > 10:
        return False
    lowered = value.casefold()
    if any(marker in lowered for marker in ("responsibilities", "requirements", "qualifications", "about us")):
        return False
    title_signals = (
        "engineer",
        "developer",
        "manager",
        "designer",
        "scientist",
        "analyst",
        "specialist",
        "consultant",
        "director",
        "head",
        "architect",
        "role",
    )
    return any(signal in lowered for signal in title_signals)


def _classify_requirement_strength(
    lowered_line: str,
) -> tuple[str | None, RequirementStrength | None]:
    for marker in _MUST_HAVE_MARKERS:
        if marker in lowered_line:
            return marker, RequirementStrength.MUST_HAVE
    for marker in _PREFERRED_MARKERS:
        if marker in lowered_line:
            return marker, RequirementStrength.PREFERRED
    for marker in _BONUS_MARKERS:
        if marker in lowered_line:
            return marker, RequirementStrength.BONUS
    return None, None


def _requirement_confidence(line: str, strength: RequirementStrength) -> float:
    base = {
        RequirementStrength.MUST_HAVE: 0.9,
        RequirementStrength.PREFERRED: 0.78,
        RequirementStrength.BONUS: 0.7,
    }[strength]
    if len(line.split()) <= 14:
        base += 0.04
    return min(base, 0.98)


def _top_keywords_for_line(line: str) -> list[NonEmptyStr]:
    tokens = keyword_candidate_tokens(line)
    unique: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        unique.append(token)
    return unique[:5]


def _dedupe_findings(findings: list[DeterministicFinding]) -> list[DeterministicFinding]:
    deduped: list[DeterministicFinding] = []
    seen: set[tuple[str, str, int]] = set()
    for item in findings:
        key = (item.finding_type.value, item.canonical_value.casefold(), item.line_index)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _section_id_for_line(index: int, sections: list[DetectedSection]) -> str | None:
    for section in sections:
        if section.line_start <= index <= section.line_end:
            return section.id
    return None


def _section_kind_for_line(index: int, sections: list[DetectedSection]) -> JDSectionKind | None:
    for section in sections:
        if section.line_start <= index <= section.line_end:
            return section.kind
    return None
