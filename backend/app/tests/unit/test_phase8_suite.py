from __future__ import annotations

import subprocess
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from backend.app.phase8.suite import (
    Phase8Area,
    Phase8AreaResult,
    render_human_report,
    run_phase8_suite,
)


def test_phase8_suite_marks_release_blocked_when_a_blocker_area_fails(monkeypatch) -> None:
    areas = (
        Phase8Area(name="passing_area", description="ok", node_ids=("tests/passing.py",)),
        Phase8Area(name="failing_area", description="bad", node_ids=("tests/failing.py",)),
    )
    calls: list[tuple[str, ...]] = []

    def fake_run(command, **kwargs):
        calls.append(tuple(command))
        if "tests/failing.py" in command:
            return subprocess.CompletedProcess(command, 1, stdout="1 failed", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="1 passed", stderr="")

    monkeypatch.setattr("backend.app.phase8.suite.subprocess.run", fake_run)

    report = run_phase8_suite(profile="quick", areas=areas, python_executable="python3")

    assert report.overall_status == "fail"
    assert report.release_recommendation == "blocked"
    assert [result.passed for result in report.area_results] == [True, False]
    assert len(calls) == 2


def test_phase8_suite_profile_selection_skips_full_only_areas(monkeypatch) -> None:
    areas = (
        Phase8Area(name="quick_area", description="ok", node_ids=("tests/quick.py",), profiles=("quick", "full")),
        Phase8Area(name="full_area", description="ok", node_ids=("tests/full.py",), profiles=("full",)),
    )

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="1 passed", stderr="")

    monkeypatch.setattr("backend.app.phase8.suite.subprocess.run", fake_run)

    report = run_phase8_suite(profile="quick", areas=areas, python_executable="python3")

    assert [result.name for result in report.area_results] == ["quick_area"]
    assert "Quick profile omits integration-only checks" in report.unresolved_risks[0]


def test_render_human_report_includes_recommendation_and_failure_excerpt() -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="1 failed", stderr="")

    import pytest

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("backend.app.phase8.suite.subprocess.run", fake_run)
    try:
        report_text = render_human_report(
            run_phase8_suite(
                profile="quick",
                areas=(
                    Phase8Area(name="area", description="desc", node_ids=("tests/area.py",)),
                ),
                python_executable="python3",
            )
        )
    finally:
        monkeypatch.undo()

    assert "Phase 8 Release Verification" in report_text
    assert "Release recommendation:" in report_text
    assert "Failure excerpts:" in report_text
