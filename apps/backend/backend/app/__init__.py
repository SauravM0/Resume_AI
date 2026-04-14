"""Application package namespace."""

from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in project root
_project_root = Path(__file__).resolve().parents[2]
_env_path = _project_root / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
