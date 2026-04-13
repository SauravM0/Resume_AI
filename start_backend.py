"""Start the backend server with correct environment variables."""
import os
import sys
from pathlib import Path

# Force load .env file before anything else
from dotenv import load_dotenv
project_root = Path(__file__).parent
load_dotenv(project_root / ".env", override=True)

# Now start uvicorn
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
