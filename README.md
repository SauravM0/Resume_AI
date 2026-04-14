# ResumeAI

ResumeAI is an AI-powered resume generation system that creates ATS-optimized resumes from your master profile and job descriptions. It uses a sophisticated multi-phase pipeline to analyze your experience, rank evidence, generate content, and verify factual accuracy before rendering to PDF.

## 🏗️ Project Architecture (Monorepo)

The project has been restructured into a monorepo for better separation of concerns and maintainability:

- **`apps/backend/`**: FastAPI backend application.
- **`apps/frontend/`**: React + Vite + TypeScript frontend.
- **`packages/resume_core/`**: Shared core logic, models, and resume optimization pipeline (`resume_optimizer` package).
- **`data/`**: Storage for master profiles (`master_profile.json`), example data, and reports.
- **`docs/`**: Comprehensive technical documentation, runbooks, and phase-specific details.
- **`archive/`**: Legacy code and internal phase documentation (safe to ignore for daily development).

---

## 🛠️ The "Problem" Solved

Moving to a monorepo structure often creates "ModuleNotFoundError" issues because packages are nested deep in the directory tree. 

**ResumeAI solves this with:**
1.  **`start_backend.py`**: A unified entry point that automatically injects the correct paths (`apps/backend` and `packages/resume_core/src`) into the Python environment.
2.  **`pyproject.toml`**: A central configuration for dependencies and package discovery.
3.  **Automated Path Injection**: No need to manually set `PYTHONPATH` in most cases when using the provided scripts.

---

## 🚀 How to Run the Project

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** (with npm)
- **MiKTeX** (Optional, for LaTeX PDF generation)
  - Recommended path: `C:\Users\Alexa\AppData\Local\Programs\MiKTeX\`

---

### Step 1: Initial Setup (One-Time)

#### 1. Backend Setup
```bash
# From the project root
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Unix/macOS

# Install in editable mode (installs all dependencies)
pip install -e .
```

#### 2. Frontend Setup
```bash
cd apps/frontend
npm install
cd ../..
```

#### 3. Environment Configuration
Copy `.env.example` to `.env` and add your Gemini API key:
```bash
copy .env.example .env
```
Edit `.env`:
```env
MASTER_PROFILE_PATH=data/master_profile.json
AI_PROVIDER=gemini
AI_MODEL=gemini-1.5-flash-latest
GEMINI_API_KEY=your_actual_api_key_here
```

---

### Step 2: Running the Servers

You need **two terminal windows** open (or use the `run_all.bat` script).

#### Terminal 1: Backend
```bash
# From project root, with .venv activated
python start_backend.py
```
- **Runs on**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health Check**: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

#### Terminal 2: Frontend
```bash
cd apps/frontend
npm run dev
```
- **Runs on**: [http://localhost:5173](http://localhost:5173)

---

### ⚡ Quick Start (Windows)
Double-click `run_all.bat` (if created) or run these commands in a single batch script to launch both:
```batch
@echo off
start cmd /k "python start_backend.py"
start cmd /k "cd apps/frontend && npm run dev"
```

---

## 🔍 Verification & Diagnostics

Once running, you can verify your setup:
1.  **Backend Health**: Visit `http://127.0.0.1:8000/api/health`. It checks if your profile is loaded and if the AI provider is correctly configured.
2.  **AI Diagnostics**: Visit `http://127.0.0.1:8000/api/diagnostics/ai` to see specific AI configuration status.
3.  **Tests**:
    - **Backend**: `pytest` from the root.
    - **Frontend**: `npm test` inside `apps/frontend`.

## 📂 Key Directories
- `apps/backend/backend/app/api/routes/`: API endpoint definitions.
- `packages/resume_core/src/resume_optimizer/`: The "brain" of the system.
- `data/master_profile.json`: Your source-of-truth career data.
- `apps/frontend/src/pages/`: Main application views.

---

## 🛠️ Troubleshooting

| Issue | Solution |
| :--- | :--- |
| `ModuleNotFoundError: No module named 'resume_optimizer'` | Always run the backend using `python start_backend.py` from the root. |
| `pdflatex` not found | Ensure MiKTeX is installed or check the path in `start_backend.py`. |
| API key errors | Ensure `GEMINI_API_KEY` is set in `.env` and that the file is in the root. |
| Port 8000 in use | Kill the process or change the port in `start_backend.py`. |
