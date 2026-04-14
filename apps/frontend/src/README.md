# Resume Generation Frontend Architecture

This frontend slice is organized as an operational workflow UI rather than a marketing page. The intent is to keep real backend behavior inspectable while the backend contracts continue to evolve.

## Folder Shape

```text
frontend/src/
  components/resume-generation/
    JobDescriptionForm.tsx
    ProgressTracker.tsx
    PhaseRow.tsx
    RunProgressHeader.tsx
    WhatIsHappeningPanel.tsx
    GenerationResult.tsx
    ResultActionBar.tsx
    SelectionSummary.tsx
    RunQualitySummary.tsx
    ArtifactLinksPanel.tsx
    ArtifactCodeViewer.tsx
    PdfPreview.tsx
    GenerationFailure.tsx
    ErrorDiagnosticsPanel.tsx
    DebugPanel.tsx
    JsonViewer.tsx
    JobAnalysisInspectorPanel.tsx
    EvidenceSelectionInspectorPanel.tsx
    VerificationInspectorPanel.tsx
    RenderArtifactInspectorPanel.tsx
    RawRunMetadataPanel.tsx
    ReadinessPanel.tsx
    ResumeSettingsPanel.tsx
    ResumeGenerationErrorBoundary.tsx
    RunStatusBanner.tsx
    ResumeGenerationPanel.tsx
    WorkflowUI.tsx
  constants/
    resumeGeneration.ts
  hooks/
    useResumeGeneration.ts
    usePipelineProgress.ts
    useSystemReadiness.ts
  pages/
    ResumeGenerationPage.tsx
  services/
    generateResume.ts
    progressStream.ts
    systemHealth.ts
  state/
    resumeGenerationState.ts
  types/
    pipeline.ts
    resume-generation.ts
  utils/
    artifactLinks.ts
    downloadHelpers.ts
    errorPresentation.ts
    debugInspector.ts
    resumeGenerationFormatters.ts
    jobDescriptionValidation.ts
    timingFormatters.ts
    progressDataMapper.ts
  test/
    fixtures/
      resumeGeneration.ts
    setupTests.ts
    testUtils.tsx
```

## Responsibilities

- `pages/ResumeGenerationPage.tsx`
  Route-level entry point. Keep router integration here.
- `components/resume-generation/ResumeGenerationPanel.tsx`
  Feature container that composes normal and debug views and applies shared workflow styling.
- `components/resume-generation/ReadinessPanel.tsx`
  Product-work readiness view for backend reachability and configured source inputs.
- `components/resume-generation/ResumeSettingsPanel.tsx`
  Advanced settings controls for output intent and diagnostics.
- `components/resume-generation/ProgressTracker.tsx`
  Phase-based progress UI with standard and debug modes.
- `components/resume-generation/RunProgressHeader.tsx`
  Run-level metadata and health summary for in-flight execution.
- `components/resume-generation/PhaseRow.tsx`
  One user-facing execution phase row that can expand backend details in debug mode.
- `components/resume-generation/GenerationResult.tsx`
  Result screen for success, partial success, downloads, selection summary, and review signals.
- `components/resume-generation/ResultActionBar.tsx`
  Primary actions for downloads, diagnostics, and reruns.
- `components/resume-generation/SelectionSummary.tsx`
  Human-readable summary of selected experiences, projects, and skills.
- `components/resume-generation/RunQualitySummary.tsx`
  Compact quality and trust summary for the completed run.
- `components/resume-generation/ArtifactLinksPanel.tsx`
  Artifact download panel for PDF, structured JSON, LaTeX, and debug outputs.
- `components/resume-generation/ArtifactCodeViewer.tsx`
  Lightweight code-view modal for LaTeX and structured JSON inspection.
- `components/resume-generation/PdfPreview.tsx`
  Lightweight modal preview surface for PDF artifacts.
- `components/resume-generation/GenerationFailure.tsx`
  Standard error card with retry and navigation actions.
- `components/resume-generation/ErrorDiagnosticsPanel.tsx`
  Advanced diagnostics surface for raw payloads, verification issues, and copyable debugging context.
- `components/resume-generation/DebugPanel.tsx`
  Internal debug inspector with structured panels for job understanding, selection, verification, artifacts, and raw metadata.
- `components/resume-generation/JsonViewer.tsx`
  Reusable raw JSON viewer used as a secondary inspection surface.
- `components/resume-generation/ResumeGenerationErrorBoundary.tsx`
  Route-level fallback for unexpected frontend exceptions.
- `components/resume-generation/WorkflowUI.tsx`
  Shared workflow presentation layer for status badges, calm cards, modal shells, empty states, focus treatment, and responsive behavior.
- `components/resume-generation/*`
  Presentational workflow views. These do not call `fetch` directly.
- `hooks/useResumeGeneration.ts`
  Main stateful controller for one generation run.
- `hooks/usePipelineProgress.ts`
  Transport hook for live progress updates. Today it uses SSE; polling can slot in behind the same boundary later.
- `hooks/useSystemReadiness.ts`
  Health and readiness controller for backend reachability plus configured source/template inputs.
- `services/generateResume.ts`
  API boundary for submit/start response normalization and backend error normalization.
- `services/progressStream.ts`
  EventSource boundary for progress events.
- `services/systemHealth.ts`
  Conservative backend reachability probe for work-screen readiness.
- `state/resumeGenerationState.ts`
  Reducer and state helpers for run transitions, progress accumulation, validation, and result shaping.
- `types/pipeline.ts`
  Central workflow contract for UI state, API payloads, diagnostics, outputs, retry/fallback metadata, and debug data.
- `types/resume-generation.ts`
  Backward-compatible shim that re-exports `pipeline.ts` while imports are migrated.
- `utils/statusMappings.ts`
  Central run-status and progress-status mapping helpers used by state orchestration.
- `utils/resumeGenerationFormatters.ts`
  Small display-only helpers.
- `utils/timingFormatters.ts`
  Shared timestamp and elapsed-duration formatting helpers.
- `utils/progressDataMapper.ts`
  Maps backend events and stages into user-facing execution phases.
- `utils/artifactLinks.ts`
  Helpers for locating and mapping per-run artifact states and links.
- `utils/downloadHelpers.ts`
  Download/file-name helpers for run-scoped artifact retrieval.
- `utils/errorPresentation.ts`
  Maps backend and frontend failures into user-facing error classes and messages.
- `utils/debugInspector.ts`
  Schema-tolerant extraction helpers that turn backend payloads into structured debug-inspection fields.
- `test/fixtures/resumeGeneration.ts`
  Stable builders for realistic workflow payloads and state shapes used across unit and component tests.
- `test/testUtils.tsx`
  Shared render wrapper for workflow-scoped styles in RTL tests.
- `../package.json` + `../vitest.config.ts`
  Minimal frontend-native test runner setup using Vitest and React Testing Library.

## Route And View Model

The current route entry is a single page:

- `ResumeGenerationPage`

Within that page, the container exposes explicit operational subviews:

- readiness and health
- input form
- advanced settings
- run status banner
- progress view
- result view
- error view
- debug panel

This keeps routing simple while still making normal mode and debug mode independent concerns.

## UX And Accessibility Layer

The workflow uses a small shared UI shell instead of one-off styles in each component:

- `WorkflowGlobalStyles` defines workflow-scoped CSS variables, focus-visible states, responsive button stacking, dialog styling, and reduced-motion handling.
- `SurfaceCard`, `StatusBadge`, `EmptyState`, and `ModalShell` keep result, error, progress, and debug surfaces visually consistent.
- Form fields and status regions expose semantic labels, `aria-live` updates, invalid state wiring, and dialog metadata so the product remains inspectable without becoming noisy.

This keeps the UI readable on laptop and mobile screens while preserving operational detail.

## State Model

`ResumeGenerationState.status` is the single UI run-state machine:

- `idle`
- `validating_input`
- `submitting`
- `queued`
- `phase_running`
- `phase_completed`
- `success`
- `partial_success`
- `failed`
- `cancelled`

The reducer owns transitions so components do not infer them independently.

## Extension Points

Planned additions can plug into existing boundaries without restructuring the UI:

- SSE progress: already handled by `usePipelineProgress`
- polling fallback: add a second transport inside `usePipelineProgress` or `services/`
- run history: add a list/query hook beside `useResumeGeneration`
- preview thumbnails: extend `DownloadableOutput` or `RenderArtifact`
- resume comparison: add comparison-specific components against `GenerationResultData`
- template selector: already represented by `template_id`
- 1-page / 2-page toggle: add to `generation_preferences`

## Test Coverage

The frontend tests are split by responsibility:

- validation and backend-shape normalization in `utils/` and `services/`
- state-machine regression checks in `state/`
- UI contract checks in `components/resume-generation/`

The fixtures intentionally model:

- full success
- partial success with warnings
- low-detail backend payloads
- phase failures
- missing or failed artifacts
- expanded diagnostics

This keeps backend evolution from forcing brittle test rewrites on every response-shape change.

## Contract Note

`types/pipeline.ts` is the canonical frontend contract for resume-generation workflow state and backend integration.
`types/resume-generation.ts` remains only as a temporary compatibility adapter so existing imports do not break during refactors.
