from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from resume_optimizer.normalization import normalize_title_taxonomy
from resume_optimizer.phase1_role_modeling import (
    FunctionalRoleFamily,
    OrganizationalRoleMode,
    compatibility_role_type_value,
    infer_role_axes,
)


def test_senior_backend_engineer_separates_backend_from_senior_ic() -> None:
    inferred = infer_role_axes(
        job_title="Senior Backend Engineer",
        raw_job_text="We are hiring a Senior Backend Engineer to build APIs and distributed systems.",
    )

    assert inferred.functional_role_family is FunctionalRoleFamily.BACKEND
    assert inferred.organizational_role_mode is OrganizationalRoleMode.SENIOR_INDIVIDUAL_CONTRIBUTOR


def test_engineering_manager_platform_separates_platform_from_people_manager() -> None:
    inferred = infer_role_axes(
        job_title="Engineering Manager, Platform",
        raw_job_text=(
            "Engineering Manager, Platform. You will manage a team of platform engineers, "
            "partner with leadership, and drive platform strategy."
        ),
    )

    assert inferred.functional_role_family is FunctionalRoleFamily.PLATFORM
    assert inferred.organizational_role_mode is OrganizationalRoleMode.PEOPLE_MANAGER


def test_lead_product_manager_maps_to_product_plus_tech_lead_mode() -> None:
    inferred = infer_role_axes(
        job_title="Lead Product Manager",
        raw_job_text=(
            "Lead Product Manager responsible for roadmap, product strategy, and mentoring PMs."
        ),
    )

    assert inferred.functional_role_family is FunctionalRoleFamily.PRODUCT
    assert inferred.organizational_role_mode is OrganizationalRoleMode.TECH_LEAD


def test_founding_full_stack_engineer_maps_to_fullstack_plus_founder_generalist() -> None:
    inferred = infer_role_axes(
        job_title="Founding Full-Stack Engineer",
        raw_job_text=(
            "Join as a founding full-stack engineer in an early-stage startup. "
            "You will work across frontend, backend, and product needs."
        ),
    )

    assert inferred.functional_role_family is FunctionalRoleFamily.FULLSTACK
    assert inferred.organizational_role_mode is OrganizationalRoleMode.FOUNDER_OR_GENERALIST


def test_data_scientist_maps_to_ml_plus_ic() -> None:
    inferred = infer_role_axes(
        job_title="Data Scientist",
        raw_job_text="Data Scientist focused on machine learning models, experimentation, and analytics.",
    )

    assert inferred.functional_role_family is FunctionalRoleFamily.ML
    assert inferred.organizational_role_mode is OrganizationalRoleMode.INDIVIDUAL_CONTRIBUTOR


def test_director_of_engineering_maps_to_other_plus_director_head() -> None:
    inferred = infer_role_axes(
        job_title="Director of Engineering",
        raw_job_text=(
            "Director of Engineering responsible for multiple teams, org planning, hiring, and stakeholder management."
        ),
    )

    assert inferred.functional_role_family is FunctionalRoleFamily.OTHER
    assert inferred.organizational_role_mode is OrganizationalRoleMode.DIRECTOR_OR_HEAD


def test_title_normalization_exposes_new_role_axis_hints_and_legacy_compat_alias() -> None:
    normalized = normalize_title_taxonomy("Engineering Manager, Platform")

    assert normalized.functional_role_family_hint == "platform"
    assert normalized.organizational_role_mode_hint == "people_manager"
    assert normalized.role_type_hint == "management"


def test_legacy_compatibility_value_prefers_org_mode_when_needed() -> None:
    assert (
        compatibility_role_type_value(
            functional_role_family=FunctionalRoleFamily.BACKEND,
            organizational_role_mode=OrganizationalRoleMode.TECH_LEAD,
        )
        == "leadership"
    )
    assert (
        compatibility_role_type_value(
            functional_role_family=FunctionalRoleFamily.PRODUCT,
            organizational_role_mode=OrganizationalRoleMode.PEOPLE_MANAGER,
        )
        == "management"
    )
