"""Safe cleanup helpers for Phase 6 temporary artifacts."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile


class UnsafeCleanupPathError(ValueError):
    """Raised when cleanup is requested for a path outside safe temp scope."""


def cleanup_compile_workspace(workspace_path: str) -> bool:
    """Delete a compiler temp workspace only when it is safe to remove."""

    workspace = Path(workspace_path).resolve()
    if not is_safe_compile_workspace(workspace):
        raise UnsafeCleanupPathError(f"refusing to cleanup unsafe workspace path: {workspace}")
    if not workspace.exists():
        return False
    shutil.rmtree(workspace)
    return True


def is_safe_compile_workspace(workspace: Path) -> bool:
    """Return whether the path looks like a compiler-created temp workspace."""

    temp_root = Path(tempfile.gettempdir()).resolve()
    try:
        workspace.relative_to(temp_root)
    except ValueError:
        return False
    return workspace.name.startswith("resume-render-")
