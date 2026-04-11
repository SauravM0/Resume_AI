"""Phase 1 evaluation runner that handles both synthetic fixture-based and live model-based evaluations."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .phase1_eval import run_phase1_eval as run_synthetic_phase1_eval
from .phase1_eval import render_phase1_eval_summary as render_synthetic_summary
from .phase1_eval import phase1_eval_summary_json as synthetic_summary_json
from .phase1_eval import load_phase1_eval_manifest as load_synthetic_manifest

from .phase1_live_eval import (
    run_live_phase1_eval,
    render_live_eval_summary,
    live_eval_summary_json,
)


EvaluationType = Literal["synthetic", "live", "both"]


class CombinedPhase1EvalSummary:
    """Combined summary from both synthetic and live evaluations."""

    def __init__(
        self,
        synthetic_summary=None,
        live_summary=None,
    ):
        self.synthetic = synthetic_summary
        self.live = live_summary

    def render_text(self) -> str:
        """Render combined text summary."""
        lines = []

        if self.synthetic:
            lines.append("=" * 60)
            lines.append("SYNTHETIC Phase 1 Evaluation (fixture-based)")
            lines.append("=" * 60)
            lines.append(render_synthetic_summary(self.synthetic))
            lines.append("")

        if self.live:
            lines.append("=" * 60)
            lines.append("LIVE Phase 1 Evaluation (real model calls)")
            lines.append("=" * 60)
            lines.append(render_live_eval_summary(self.live))
            lines.append("")

        return "\n".join(lines)

    def render_json(self) -> str:
        """Render combined JSON summary."""
        import json

        return json.dumps(
            {
                "synthetic": self.synthetic.model_dump(mode="json")
                if self.synthetic
                else None,
                "live": self.live.model_dump(mode="json") if self.live else None,
            },
            indent=2,
        )


def run_phase1_evaluation(
    *,
    eval_type: EvaluationType = "both",
    synthetic_fixture_root: Path | None = None,
    live_manifest_path: Path | None = None,
    case_ids: list[str] | None = None,
    verbose: bool = False,
) -> CombinedPhase1EvalSummary:
    """Run Phase 1 evaluation with specified type(s).

    Args:
        eval_type: "synthetic" for fixture-based, "live" for real model calls,
                   or "both" to run both and produce a combined report.
        synthetic_fixture_root: Path to synthetic fixture directory.
        live_manifest_path: Path to live evaluation manifest.
        case_ids: Optional list of case IDs to filter.
        verbose: Whether to include full parsed output in results.

    Returns:
        CombinedPhase1EvalSummary with results from requested evaluation types.
    """
    synthetic_summary = None
    live_summary = None

    if eval_type in ("synthetic", "both"):
        try:
            synthetic_summary = run_synthetic_phase1_eval(
                fixture_root=synthetic_fixture_root
                or Path("backend/app/tests/fixtures/phase1_eval"),
                case_ids=case_ids,
            )
        except Exception as e:
            print(f"Synthetic evaluation failed: {e}")

    if eval_type in ("live", "both"):
        try:
            live_summary = run_live_phase1_eval(
                manifest_path=live_manifest_path,
                case_ids=case_ids,
                verbose=verbose,
            )
        except Exception as e:
            print(f"Live evaluation failed: {e}")

    return CombinedPhase1EvalSummary(
        synthetic_summary=synthetic_summary,
        live_summary=live_summary,
    )


def main():
    """CLI entry point for Phase 1 evaluation."""
    import argparse

    parser = argparse.ArgumentParser(description="Run Phase 1 evaluation")
    parser.add_argument(
        "--type",
        choices=["synthetic", "live", "both"],
        default="both",
        help="Type of evaluation to run",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include full parsed output in results",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )

    args = parser.parse_args()

    summary = run_phase1_evaluation(
        eval_type=args.type,
        verbose=args.verbose,
    )

    if args.output == "json":
        print(summary.render_json())
    else:
        print(summary.render_text())


if __name__ == "__main__":
    main()
