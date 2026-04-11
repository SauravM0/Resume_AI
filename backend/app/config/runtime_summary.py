"""Utilities for inspecting the effective runtime configuration safely."""

from __future__ import annotations

import json

from resume_optimizer.config import DEFAULT_SETTINGS, get_effective_config_summary


def render_effective_config_summary() -> str:
    """Return the redacted effective configuration as formatted JSON."""

    return json.dumps(get_effective_config_summary(), indent=2, sort_keys=True)


def main() -> None:
    if not DEFAULT_SETTINGS.diagnostics.config_summary_enabled:
        raise SystemExit("Config summary is disabled in the active environment.")
    print(render_effective_config_summary())


if __name__ == "__main__":
    main()
