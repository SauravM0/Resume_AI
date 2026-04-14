"""Start the backend server with correct environment variables."""

import os
import sys
from pathlib import Path

# Force load .env file before anything else
from dotenv import load_dotenv

project_root = Path(__file__).parent
load_dotenv(project_root / ".env", override=True)

# Add paths for new monorepo structure
apps_path = project_root / "apps"
packages_path = project_root / "packages"

# Add packages/resume_core/src FIRST so "resume_optimizer" resolves
resume_core_path = packages_path / "resume_core" / "src"
if str(resume_core_path) not in sys.path:
    sys.path.insert(0, str(resume_core_path))

# Add apps/backend to sys.path so "backend" package resolves
# Note: parent dir of "backend" package name
backend_parent = apps_path / "backend"
if str(backend_parent) not in sys.path:
    sys.path.insert(0, str(backend_parent))

# Add MiKTeX to PATH for pdflatex
miktex_path = r"C:\Users\Alexa\AppData\Local\Programs\MiKTeX\miktex\bin\x64"
if miktex_path not in os.environ.get("PATH", ""):
    os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + miktex_path

# Now start uvicorn
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
