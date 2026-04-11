"""Pydantic models for the Phase 0 source-of-truth schema."""

from __future__ import annotations

from collections import Counter
from email.utils import parseaddr
from enum import StrEnum
import re
from typing import Annotated, Self

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .constants import DATE_PATTERN

StableId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OptionalUrl = AnyHttpUrl | None
OptionalPhone = Annotated[
    str | None,
    StringConstraints(
        strip_whitespace=True,
        min_length=7,
        max_length=32,
        pattern=r"^[+0-9().\-\s]+$",
    ),
]
ScoreValue = Annotated[float, Field(ge=0.0, le=1.0)]


class ItemType(StrEnum):
    PERSONAL_PROFILE = "personal_profile"
    EXPERIENCE = "experience"
    BULLET = "bullet"
    PROJECT = "project"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    SKILL = "skill"
    AWARD = "award"


class SourceType(StrEnum):
    RESUME = "resume"
    LINKEDIN = "linkedin"
    PORTFOLIO = "portfolio"
    INTERVIEW_NOTES = "interview_notes"
    CERTIFICATION_RECORD = "certification_record"
    PROJECT_DOC = "project_doc"
    OTHER = "other"


class RoleType(StrEnum):
    INDIVIDUAL_CONTRIBUTOR = "individual_contributor"
    MANAGER = "manager"
    LEAD = "lead"
    CONSULTANT = "consultant"
    FOUNDER = "founder"
    RESEARCHER = "researcher"
    STUDENT = "student"
    ADVISOR = "advisor"


class SeniorityLevel(StrEnum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    DIRECTOR = "director"
    EXECUTIVE = "executive"


class ImpactLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXCEPTIONAL = "exceptional"


class EvidenceStrength(StrEnum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERIFIED = "verified"


class VerifiedStatus(StrEnum):
    UNVERIFIED = "unverified"
    SELF_REPORTED = "self_reported"
    CORROBORATED = "corroborated"
    VERIFIED = "verified"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    APPRENTICESHIP = "apprenticeship"


class DatePrecision(StrEnum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"


class StrictModel(BaseModel):
    """Shared strict model configuration for the source-truth layer."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class SourceLink(StrictModel):
    source_type: SourceType
    source_id: StableId
    source_url: OptionalUrl = None
    excerpt: NonEmptyStr | None = None
    note: NonEmptyStr | None = None


class MetricEntry(StrictModel):
    id: StableId
    label: NonEmptyStr
    value: float | int | None = None
    unit: NonEmptyStr | None = None
    context: NonEmptyStr | None = None


class PartialDate(StrictModel):
    """
    Raw dates may arrive as YYYY, YYYY-MM, or YYYY-MM-DD.
    The model preserves the original value and stores normalized components.
    """

    raw_value: NonEmptyStr
    normalized_value: NonEmptyStr | None = None
    precision: DatePrecision | None = None
    year: int | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)

    @model_validator(mode="after")
    def normalize(self) -> Self:
        raw = self.raw_value
        parts = raw.split("-")
        if not 1 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
            raise ValueError("date must use YYYY, YYYY-MM, or YYYY-MM-DD format")

        year = int(parts[0])
        if len(parts[0]) != 4:
            raise ValueError("year must be four digits")

        month = int(parts[1]) if len(parts) >= 2 else None
        day = int(parts[2]) if len(parts) == 3 else None

        if month is not None and not re.fullmatch(DATE_PATTERN, raw) and len(parts) != 1:
            raise ValueError("month-based dates must use YYYY-MM or YYYY-MM-DD format")

        if month is not None and not 1 <= month <= 12:
            raise ValueError("month must be between 1 and 12")

        if day is not None and not 1 <= day <= 31:
            raise ValueError("day must be between 1 and 31")

        precision = (
            DatePrecision.DAY
            if day is not None
            else DatePrecision.MONTH
            if month is not None
            else DatePrecision.YEAR
        )

        object.__setattr__(self, "year", year)
        object.__setattr__(self, "month", month)
        object.__setattr__(self, "day", day)
        object.__setattr__(self, "precision", precision)

        normalized = f"{year:04d}"
        if month is not None:
            normalized = f"{normalized}-{month:02d}"
        if day is not None:
            normalized = f"{normalized}-{day:02d}"
        object.__setattr__(self, "normalized_value", normalized)
        return self

    def comparable_key(self) -> tuple[int, ...]:
        if self.precision == DatePrecision.YEAR:
            return (self.year or 0,)
        if self.precision == DatePrecision.MONTH:
            return (self.year or 0, self.month or 0)
        return (self.year or 0, self.month or 0, self.day or 0)


class IdentifiedModel(StrictModel):
    id: StableId


class ProfileItem(IdentifiedModel):
    item_type: ItemType
    source_links: list[SourceLink] = Field(default_factory=list)
    canonical_tags: list[NonEmptyStr] = Field(default_factory=list)
    domain_tags: list[NonEmptyStr] = Field(default_factory=list)
    verified_status: VerifiedStatus = VerifiedStatus.UNVERIFIED
    evidence_strength: EvidenceStrength = EvidenceStrength.WEAK
    rewrite_allowed: bool = True


class RankedItem(ProfileItem):
    impact_score: ScoreValue | None = None
    recency_score: ScoreValue | None = None


class BulletEntry(RankedItem):
    item_type: ItemType = ItemType.BULLET
    text: NonEmptyStr
    impact_level: ImpactLevel = ImpactLevel.MEDIUM
    tools: list[NonEmptyStr] = Field(default_factory=list)
    metrics: list[MetricEntry] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("bullet text must not be empty")
        return value


class PersonalProfile(ProfileItem):
    item_type: ItemType = ItemType.PERSONAL_PROFILE
    full_name: NonEmptyStr
    headline: NonEmptyStr | None = None
    summary: NonEmptyStr | None = None
    email: NonEmptyStr | None = None
    phone: OptionalPhone = None
    location: NonEmptyStr | None = None
    linkedin_url: OptionalUrl = None
    github_url: OptionalUrl = None
    website_url: OptionalUrl = None
    role_type: RoleType | None = None
    seniority_level: SeniorityLevel | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        _, parsed = parseaddr(value)
        if not parsed or "@" not in parsed:
            raise ValueError("email must be a valid email address")
        return parsed


class ExperienceEntry(RankedItem):
    item_type: ItemType = ItemType.EXPERIENCE
    organization: NonEmptyStr
    title: NonEmptyStr
    employment_type: EmploymentType | None = None
    role_type: RoleType | None = None
    seniority_level: SeniorityLevel | None = None
    location: NonEmptyStr | None = None
    start_date: PartialDate
    end_date: PartialDate | None = None
    current: bool = False
    bullets: list[BulletEntry] = Field(default_factory=list)
    tools: list[NonEmptyStr] = Field(default_factory=list)
    metrics: list[MetricEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        _validate_date_order(self.start_date, self.end_date)
        if self.current and self.end_date is not None:
            raise ValueError("current experience entries must not define end_date")
        return self


class ProjectEntry(RankedItem):
    item_type: ItemType = ItemType.PROJECT
    name: NonEmptyStr
    role: NonEmptyStr | None = None
    role_type: RoleType | None = None
    seniority_level: SeniorityLevel | None = None
    start_date: PartialDate | None = None
    end_date: PartialDate | None = None
    summary: NonEmptyStr | None = None
    bullets: list[BulletEntry] = Field(default_factory=list)
    tools: list[NonEmptyStr] = Field(default_factory=list)
    metrics: list[MetricEntry] = Field(default_factory=list)
    link_url: OptionalUrl = None

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        _validate_date_order(self.start_date, self.end_date)
        return self


class EducationEntry(ProfileItem):
    item_type: ItemType = ItemType.EDUCATION
    institution: NonEmptyStr
    degree: NonEmptyStr
    field_of_study: NonEmptyStr | None = None
    location: NonEmptyStr | None = None
    start_date: PartialDate | None = None
    end_date: PartialDate | None = None
    bullets: list[BulletEntry] = Field(default_factory=list)
    honors: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        _validate_date_order(self.start_date, self.end_date)
        return self


class CertificationEntry(ProfileItem):
    item_type: ItemType = ItemType.CERTIFICATION
    name: NonEmptyStr
    issuer: NonEmptyStr
    issue_date: PartialDate | None = None
    expiration_date: PartialDate | None = None
    credential_id: NonEmptyStr | None = None
    credential_url: OptionalUrl = None
    canonical_tags: list[NonEmptyStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        _validate_date_order(self.issue_date, self.expiration_date)
        return self


class AwardEntry(ProfileItem):
    item_type: ItemType = ItemType.AWARD
    title: NonEmptyStr
    awarder: NonEmptyStr | None = None
    award_date: PartialDate | None = None
    summary: NonEmptyStr | None = None
    bullets: list[BulletEntry] = Field(default_factory=list)


class SkillEntry(ProfileItem):
    item_type: ItemType = ItemType.SKILL
    name: NonEmptyStr
    category: NonEmptyStr
    tools: list[NonEmptyStr] = Field(default_factory=list)
    metrics: list[MetricEntry] = Field(default_factory=list)
    role_type: RoleType | None = None
    seniority_level: SeniorityLevel | None = None
    recency_score: ScoreValue | None = None


class MasterProfile(IdentifiedModel):
    personal_profile: PersonalProfile
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    awards: list[AwardEntry] = Field(default_factory=list)
    skills: list[SkillEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> Self:
        ids = [self.id, self.personal_profile.id]

        for entry in self.experience:
            ids.append(entry.id)
            ids.extend(bullet.id for bullet in entry.bullets)
            ids.extend(metric.id for metric in entry.metrics)
            for bullet in entry.bullets:
                ids.extend(metric.id for metric in bullet.metrics)

        for entry in self.projects:
            ids.append(entry.id)
            ids.extend(bullet.id for bullet in entry.bullets)
            ids.extend(metric.id for metric in entry.metrics)
            for bullet in entry.bullets:
                ids.extend(metric.id for metric in bullet.metrics)

        for entry in self.education:
            ids.append(entry.id)
            ids.extend(bullet.id for bullet in entry.bullets)
            for bullet in entry.bullets:
                ids.extend(metric.id for metric in bullet.metrics)

        for entry in self.certifications:
            ids.append(entry.id)

        for entry in self.awards:
            ids.append(entry.id)
            ids.extend(bullet.id for bullet in entry.bullets)
            for bullet in entry.bullets:
                ids.extend(metric.id for metric in bullet.metrics)

        for entry in self.skills:
            ids.append(entry.id)
            ids.extend(metric.id for metric in entry.metrics)

        duplicates = sorted(item_id for item_id, count in Counter(ids).items() if count > 1)
        if duplicates:
            duplicate_list = ", ".join(duplicates)
            raise ValueError(f"duplicate IDs detected in MasterProfile: {duplicate_list}")

        return self


def _validate_date_order(start_date: PartialDate | None, end_date: PartialDate | None) -> None:
    if start_date is None or end_date is None:
        return

    if start_date.precision != end_date.precision:
        return

    if end_date.comparable_key() < start_date.comparable_key():
        raise ValueError("end date cannot be before start date")
