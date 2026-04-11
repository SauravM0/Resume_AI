"""Tests for the Phase 2 evaluation runner and fixture pack."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.resume_optimizer.phase2_eval import (
    DEFAULT_PHASE2_EVAL_FIXTURE_ROOT,
    Phase2EvalFixtureError,
    load_phase2_eval_manifest,
    run_phase2_eval,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_phase2_eval_fixture_pack_exists_and_is_valid() -> None:
    fixture_root = DEFAULT_PHASE2_EVAL_FIXTURE_ROOT

    assert fixture_root.exists()
    assert (fixture_root / "eval_cases.json").exists()

    manifest = load_phase2_eval_manifest(fixture_root)

    assert manifest.cases
    for case in manifest.cases:
        assert (fixture_root / case.profile_fixture).exists()
        assert (fixture_root / case.job_analysis_fixture).exists()


def test_phase2_eval_missing_manifest_fails_early_with_clear_error(tmp_path: Path) -> None:
    with pytest.raises(Phase2EvalFixtureError, match="manifest not found"):
        load_phase2_eval_manifest(tmp_path)


def test_phase2_eval_missing_referenced_files_fail_validation(tmp_path: Path) -> None:
    manifest_path = tmp_path / "eval_cases.json"
    manifest_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "broken_case",
                        "description": "Broken fixture references",
                        "profile_fixture": "profiles/missing.json",
                        "job_analysis_fixture": "jobs/missing.json",
                        "expectation": {},
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(Phase2EvalFixtureError, match="profile fixture is missing"):
        load_phase2_eval_manifest(tmp_path)


def test_phase2_eval_invalid_job_analysis_schema_fails_validation(tmp_path: Path) -> None:
    (tmp_path / "profiles").mkdir()
    (tmp_path / "jobs").mkdir()
    source_profile = (
        REPO_ROOT
        / "backend/app/tests/fixtures/phase2_eval/profiles/senior_backend.json"
    )
    (tmp_path / "profiles" / "senior_backend.json").write_text(
        source_profile.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "jobs" / "broken.json").write_text(
        json.dumps({"role_type": "individual_contributor", "technical_skills": "not-a-list"}),
        encoding="utf-8",
    )
    (tmp_path / "eval_cases.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "broken_schema",
                        "description": "Broken job analysis schema",
                        "profile_fixture": "profiles/senior_backend.json",
                        "job_analysis_fixture": "jobs/broken.json",
                        "expectation": {},
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(Phase2EvalFixtureError, match="job analysis fixture is invalid"):
        load_phase2_eval_manifest(tmp_path)


def test_phase2_eval_unknown_case_id_fails_early() -> None:
    with pytest.raises(Phase2EvalFixtureError, match="Unknown Phase 2 eval case id"):
        run_phase2_eval(
            fixture_root=DEFAULT_PHASE2_EVAL_FIXTURE_ROOT,
            case_ids=["does_not_exist"],
        )


def test_phase2_eval_runner_succeeds_on_checked_in_pack() -> None:
    summary = run_phase2_eval(
        fixture_root=DEFAULT_PHASE2_EVAL_FIXTURE_ROOT,
        today=None,
    )

    assert summary.total_cases >= 2
    assert summary.failed_cases == 0
    assert summary.passed_cases == summary.total_cases


def test_phase2_eval_cli_runs_successfully_from_repo_root() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_phase2_eval.py", "--today", "2026-04-06"],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "Phase 2 Evaluation Summary" in completed.stdout
    assert "Passed:" in completed.stdout
