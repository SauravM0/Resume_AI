import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ResumeGenerationPanel } from "./ResumeGenerationPanel";
import { renderWithWorkflow } from "../../test/testUtils";
import {
  makeBackendHealth,
  makeGenerationResult,
  makeProgressState,
  makeReadinessIndicators,
  makeResumeGenerationState,
  makeRunMetadata,
} from "../../test/fixtures/resumeGeneration";

const useResumeGenerationMock = vi.fn();
const useSystemReadinessMock = vi.fn();

vi.mock("../../hooks/useResumeGeneration", () => ({
  useResumeGeneration: (...args: unknown[]) => useResumeGenerationMock(...args),
}));

vi.mock("../../hooks/useSystemReadiness", () => ({
  useSystemReadiness: (...args: unknown[]) => useSystemReadinessMock(...args),
}));

describe("ResumeGenerationPanel", () => {
  beforeEach(() => {
    useSystemReadinessMock.mockReturnValue({
      backendHealth: makeBackendHealth(),
      readiness: makeReadinessIndicators(),
      refresh: vi.fn(),
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the initial empty workflow state", () => {
    useResumeGenerationMock.mockReturnValue({
      state: makeResumeGenerationState(),
      submit: vi.fn(),
      retry: vi.fn(),
      cancel: vi.fn(),
      reset: vi.fn(),
      toggleDebug: vi.fn(),
    });

    renderWithWorkflow(<ResumeGenerationPanel />);

    expect(screen.getByText("No run started yet")).toBeInTheDocument();
    expect(screen.getByText("No result available yet")).toBeInTheDocument();
    expect(screen.getByText("System readiness")).toBeInTheDocument();
  });

  it("submits a valid job description through the main workflow form", async () => {
    const user = userEvent.setup();
    const submit = vi.fn().mockResolvedValue(undefined);

    useResumeGenerationMock.mockReturnValue({
      state: makeResumeGenerationState(),
      submit,
      retry: vi.fn(),
      cancel: vi.fn(),
      reset: vi.fn(),
      toggleDebug: vi.fn(),
    });

    renderWithWorkflow(<ResumeGenerationPanel />);

    await user.type(
      screen.getByLabelText("Paste the job description"),
      "Staff software engineer role requiring React, TypeScript, accessibility, resume generation systems, verification, rendering, collaboration, and production debugging across a hiring workflow platform.",
    );
    await user.click(screen.getByRole("button", { name: "Start generation" }));

    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        job_description_text: expect.stringContaining("Staff software engineer role"),
        source_profile_path: "data/master_profile.example.json",
        template_id: "ats_standard",
      }),
    );
  });

  it("shows debug inspector only when debug mode is enabled", async () => {
    const user = userEvent.setup();
    const toggleDebug = vi.fn();

    useResumeGenerationMock.mockReturnValue({
      state: makeResumeGenerationState({
        debug_visible: false,
      }),
      submit: vi.fn(),
      retry: vi.fn(),
      cancel: vi.fn(),
      reset: vi.fn(),
      toggleDebug,
    });

    const { rerender } = renderWithWorkflow(<ResumeGenerationPanel />);

    expect(screen.queryByText("Debug inspector")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show advanced settings" }));
    await user.click(screen.getByRole("checkbox", { name: /Debug mode/i }));

    expect(toggleDebug).toHaveBeenCalledWith(true);

    useResumeGenerationMock.mockReturnValue({
      state: makeResumeGenerationState({
        debug_visible: true,
        status: "success",
        view: "result",
        result: makeGenerationResult(),
        run: makeRunMetadata(),
      }),
      submit: vi.fn(),
      retry: vi.fn(),
      cancel: vi.fn(),
      reset: vi.fn(),
      toggleDebug,
    });

    rerender(<ResumeGenerationPanel />);

    expect(screen.getByText("Debug inspector")).toBeInTheDocument();
  });

  it("keeps progress visible while an active run is executing and exposes retry controls on failure", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();

    useResumeGenerationMock.mockReturnValue({
      state: makeResumeGenerationState({
        status: "failed",
        view: "error",
        debug_visible: false,
        run: makeRunMetadata({ run_id: "run.failed" }),
        progress: makeProgressState({ run_id: "run.failed" }),
        result: makeGenerationResult({
          run_metadata: { run_id: "run.failed" },
        }),
        error: {
          message: "Transport network error",
          error_source: "transport",
          run_id: "run.failed",
        },
      }),
      submit: vi.fn(),
      retry,
      cancel: vi.fn(),
      reset: vi.fn(),
      toggleDebug: vi.fn(),
    });

    renderWithWorkflow(<ResumeGenerationPanel />);

    expect(screen.getByText("Progress phases")).toBeInTheDocument();
    expect(screen.getByText("Transport failure")).toBeInTheDocument();

    const retryButtons = screen.getAllByRole("button", { name: "Retry run" });
    const enabledRetryButton = retryButtons.find((button) => !button.hasAttribute("disabled"));
    expect(enabledRetryButton).toBeDefined();
    await user.click(enabledRetryButton!);

    expect(retry).toHaveBeenCalled();
  });

  it("allows reset from the run status banner without hiding the failure context prematurely", async () => {
    const user = userEvent.setup();
    const reset = vi.fn();

    useResumeGenerationMock.mockReturnValue({
      state: makeResumeGenerationState({
        status: "failed",
        view: "error",
        run: makeRunMetadata({ run_id: "run.reset" }),
        progress: makeProgressState({ run_id: "run.reset" }),
        error: {
          message: "Verification failed.",
          stage_name: "verify_generated_content",
          run_id: "run.reset",
          error_source: "backend",
        },
      }),
      submit: vi.fn(),
      retry: vi.fn(),
      cancel: vi.fn(),
      reset,
      toggleDebug: vi.fn(),
    });

    renderWithWorkflow(<ResumeGenerationPanel />);

    expect(screen.getByText("Run failure")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset" }));

    expect(reset).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Run failure")).toBeInTheDocument();
  });

  it("renders completed results without stale progress-only placeholders", () => {
    useResumeGenerationMock.mockReturnValue({
      state: makeResumeGenerationState({
        status: "success",
        view: "result",
        run: makeRunMetadata({ run_id: "run.success" }),
        progress: makeProgressState({ run_id: "run.success" }),
        result: makeGenerationResult({
          run_metadata: { run_id: "run.success" },
        }),
      }),
      submit: vi.fn(),
      retry: vi.fn(),
      cancel: vi.fn(),
      reset: vi.fn(),
      toggleDebug: vi.fn(),
    });

    renderWithWorkflow(<ResumeGenerationPanel />);

    expect(screen.getByText("Result summary")).toBeInTheDocument();
    expect(screen.queryByText("No result available yet")).not.toBeInTheDocument();
  });
});
