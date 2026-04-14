# Phase 6 Readiness Validator

This directory records the pre-orchestration readiness boundary for Phase 6.

Phase 6 will reuse:

- Phase 0-5 Pydantic contracts in `src/resume_optimizer/**` and `backend/app/**`.
- `build_phase2_ranking_artifacts` for deterministic Phase 2 artifacts.
- `Phase3Service.run` for structured generation artifacts.
- `VerificationOrchestrator.run` for Phase 4 verification.
- Phase 5 render primitives: template registry, LaTeX mapper, layout manager, document assembler, PDF compiler, and render diagnostics.

Phase 6 will wrap:

- OpenAI calls and malformed-output retries.
- Local default profile loading.
- SQLAlchemy repository/session creation.
- Verification and rendering persistence.
- PDF compilation workspace and artifact lifecycle.

Phase 6 must not touch yet:

- Product idea or resume optimization behavior.
- Controlled LaTeX template structure except via validated placeholders.
- `build/lib/**` generated copies.
- Frontend code, because no React/TypeScript frontend files exist in this checkout.
- Supabase-specific behavior until a concrete Supabase integration is added.

Primary audit artifact:

- `for_ai_agent/phase_6/phase6_readiness_report.md`
