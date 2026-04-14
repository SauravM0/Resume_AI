"""Release-readiness verification runner for production-hardening checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
import subprocess
import sys
import time
from typing import Literal, Sequence


Phase8Profile = Literal["quick", "full"]


@dataclass(frozen=True, slots=True)
class Phase8Area:
    """One release-verification area with its pytest targets."""

    name: str
    description: str
    node_ids: tuple[str, ...]
    blocker: bool = True
    profiles: tuple[Phase8Profile, ...] = ("quick", "full")


@dataclass(frozen=True, slots=True)
class Phase8AreaResult:
    """Execution result for one verification area."""

    name: str
    description: str
    passed: bool
    blocker: bool
    duration_seconds: float
    command: tuple[str, ...]
    node_ids: tuple[str, ...]
    output_excerpt: str


@dataclass(frozen=True, slots=True)
class Phase8Report:
    """Aggregate release-readiness result for one suite run."""

    generated_at: str
    profile: Phase8Profile
    overall_status: Literal["pass", "fail"]
    release_recommendation: Literal["release_candidate_approved", "blocked"]
    required_environment_settings: tuple[str, ...]
    known_limitations: tuple[str, ...]
    unresolved_risks: tuple[str, ...]
    area_results: tuple[Phase8AreaResult, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable report payload."""

        payload = asdict(self)
        payload["area_results"] = [asdict(result) for result in self.area_results]
        return payload


DEFAULT_PHASE8_AREAS: tuple[Phase8Area, ...] = (
    Phase8Area(
        name="phase8_scenarios",
        description="Cross-area Phase 8 release-readiness scenarios.",
        node_ids=("backend/app/tests/phase8/test_phase8_release_readiness.py",),
    ),
    Phase8Area(
        name="structured_logging_and_privacy",
        description="Structured logging presence, JSON shape, and sensitive-content redaction.",
        node_ids=("backend/app/tests/unit/test_privacy_redaction.py",),
    ),
    Phase8Area(
        name="stage_metrics",
        description="Stage metric completeness and request tracing through stage timing records.",
        node_ids=(
            "backend/app/tests/unit/test_stage_metrics.py",
            "backend/app/tests/integration/test_stage_metrics_route.py",
        ),
        profiles=("full",),
    ),
    Phase8Area(
        name="failure_taxonomy",
        description="Typed failure categories, safe user messages, and deterministic handling metadata.",
        node_ids=("backend/app/tests/unit/test_failure_handling.py",),
    ),
    Phase8Area(
        name="retry_and_fallback_policy",
        description="Retryable versus non-retryable handling and explicit fallback behavior.",
        node_ids=(
            "backend/app/tests/unit/test_retry_fallback_policy.py",
            "backend/app/tests/unit/test_safe_fallbacks.py",
        ),
    ),
    Phase8Area(
        name="safe_cache",
        description="Deterministic cache correctness, invalidation, and no stale reuse across changes.",
        node_ids=("backend/app/tests/unit/test_safe_cache.py",),
    ),
    Phase8Area(
        name="runtime_config_and_secrets",
        description="Typed config validation, environment profiles, and secret redaction.",
        node_ids=("backend/app/tests/unit/test_runtime_config.py",),
    ),
    Phase8Area(
        name="artifact_cleanup",
        description="Artifact persistence boundaries and safe compile-workspace cleanup.",
        node_ids=("backend/app/tests/unit/test_artifact_manager.py",),
    ),
    Phase8Area(
        name="confidence_scoring",
        description="Internal confidence gating and degraded or unsafe classification.",
        node_ids=("backend/app/tests/unit/test_run_confidence.py",),
    ),
    Phase8Area(
        name="operator_tooling",
        description="Operator CLI health, safe diagnostics output, and support-safe redaction.",
        node_ids=("backend/app/tests/unit/test_support_tooling.py",),
    ),
    Phase8Area(
        name="duplicate_request_guard",
        description="Idempotency and duplicate-run protection for generation requests.",
        node_ids=("backend/app/tests/integration/test_generate_resume_idempotency.py",),
        profiles=("full",),
    ),
)


def run_phase8_suite(
    *,
    profile: Phase8Profile = "quick",
    python_executable: str | None = None,
    extra_pytest_args: Sequence[str] | None = None,
    areas: Sequence[Phase8Area] = DEFAULT_PHASE8_AREAS,
    workdir: str | Path | None = None,
) -> Phase8Report:
    """Run the selected Phase 8 verification areas and build a release report."""

    executable = python_executable or sys.executable
    pytest_args = tuple(extra_pytest_args or ())
    results: list[Phase8AreaResult] = []
    for area in areas:
        if profile not in area.profiles:
            continue
        command = (
            executable,
            "-m",
            "pytest",
            "-s",
            *pytest_args,
            *area.node_ids,
        )
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=str(workdir) if workdir is not None else None,
            capture_output=True,
            text=True,
            check=False,
        )
        duration_seconds = round(time.perf_counter() - started, 3)
        results.append(
            Phase8AreaResult(
                name=area.name,
                description=area.description,
                passed=completed.returncode == 0,
                blocker=area.blocker,
                duration_seconds=duration_seconds,
                command=command,
                node_ids=area.node_ids,
                output_excerpt=_truncate_output(completed.stdout, completed.stderr),
            )
        )

    unresolved_risks = _build_unresolved_risks(profile=profile, results=results)
    has_blocker_failure = any(result.blocker and not result.passed for result in results)
    return Phase8Report(
        generated_at=datetime.now(UTC).isoformat(),
        profile=profile,
        overall_status="fail" if has_blocker_failure else "pass",
        release_recommendation="blocked" if has_blocker_failure else "release_candidate_approved",
        required_environment_settings=(
            "RESUME_OPTIMIZER_ENV=test",
            "pytest and test extras installed",
            "Run from repository root",
            "Use the full profile before release",
        ),
        known_limitations=(
            "The suite validates the production-hardening layers and does not replace the full product regression suite.",
            "Idempotency verification is process-local and does not exercise distributed locking behavior.",
            "Artifact cleanup verification covers only the bounded compiler temp-workspace policy.",
        ),
        unresolved_risks=unresolved_risks,
        area_results=tuple(results),
    )


def render_human_report(report: Phase8Report) -> str:
    """Render a concise operator-facing release summary."""

    lines = [
        "Phase 8 Release Verification",
        f"Generated at: {report.generated_at}",
        f"Profile: {report.profile}",
        f"Overall status: {report.overall_status}",
        f"Release recommendation: {report.release_recommendation}",
        "",
        "Area results:",
    ]
    for result in report.area_results:
        status = "PASS" if result.passed else "FAIL"
        blocker = " blocker" if result.blocker else ""
        lines.append(f"- {result.name}: {status}{blocker} ({result.duration_seconds:.3f}s)")
    lines.extend(
        [
            "",
            "Required environment settings:",
            *[f"- {value}" for value in report.required_environment_settings],
            "",
            "Known limitations:",
            *[f"- {value}" for value in report.known_limitations],
            "",
            "Unresolved risks:",
            *[f"- {value}" for value in report.unresolved_risks],
        ]
    )
    failed = [result for result in report.area_results if not result.passed]
    if failed:
        lines.extend(
            [
                "",
                "Failure excerpts:",
                *[
                    f"- {result.name}: {result.output_excerpt or 'No output captured.'}"
                    for result in failed
                ],
            ]
        )
    return "\n".join(lines)


def _build_unresolved_risks(
    *,
    profile: Phase8Profile,
    results: Sequence[Phase8AreaResult],
) -> tuple[str, ...]:
    risks: list[str] = []
    failed = [result.name for result in results if not result.passed]
    if failed:
        risks.extend(f"Blocking verification area failed: {name}" for name in failed)
    if profile != "full":
        risks.append("Quick profile omits integration-only checks; full profile is required before release.")
    if not failed:
        risks.append("No blocking hardening regressions were detected in the selected profile.")
    return tuple(risks)


def _truncate_output(stdout: str, stderr: str, *, max_chars: int = 1200) -> str:
    text = (stdout or "").strip()
    if stderr.strip():
        text = f"{text}\n{stderr.strip()}".strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...[truncated]"
