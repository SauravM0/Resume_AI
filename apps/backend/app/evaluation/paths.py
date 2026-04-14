"""Repository paths reserved for Phase 7 fixtures and outputs."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVALUATION_FIXTURE_ROOT = REPO_ROOT / "fixtures" / "evaluation"
JD_PARSE_FIXTURE_DIR = DEFAULT_EVALUATION_FIXTURE_ROOT / "jd_parse"
SELECTION_FIXTURE_DIR = DEFAULT_EVALUATION_FIXTURE_ROOT / "selection"
END_TO_END_FIXTURE_DIR = DEFAULT_EVALUATION_FIXTURE_ROOT / "end_to_end"
RED_TEAM_FIXTURE_DIR = DEFAULT_EVALUATION_FIXTURE_ROOT / "red_team"
DEFAULT_EVALUATION_OUTPUT_ROOT = REPO_ROOT / "outputs" / "evaluation_runs"

EVALUATION_FIXTURE_DIRS: tuple[Path, ...] = (
    JD_PARSE_FIXTURE_DIR,
    SELECTION_FIXTURE_DIR,
    END_TO_END_FIXTURE_DIR,
    RED_TEAM_FIXTURE_DIR,
)
