import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { GenerationFailure } from "./GenerationFailure";
import { renderWithWorkflow } from "../../test/testUtils";
import {
  makeBackendError,
  makeGenerationResult,
  makeProgressState,
  makeRunMetadata,
} from "../../test/fixtures/resumeGeneration";

describe("GenerationFailure", () => {
  it("shows phase-specific failure messaging and retry actions", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();

    renderWithWorkflow(
      <GenerationFailure
        error={makeBackendError({
          message: "Ranking failed.",
          stage_name: "rank_select_evidence",
          failure_type: "ranking_error",
        })}
        run={makeRunMetadata({ run_id: "run.failed" })}
        progress={makeProgressState()}
        result={makeGenerationResult()}
        onRetry={onRetry}
        onStartNewRun={vi.fn()}
        onReturnToEditor={vi.fn()}
      />,
    );

    expect(screen.getByText("Selection failed")).toBeInTheDocument();
    expect(screen.getByText(/Suggested next step/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry run" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("keeps raw diagnostics hidden until details are requested in standard mode", async () => {
    const user = userEvent.setup();

    renderWithWorkflow(
      <GenerationFailure
        error={makeBackendError({
          message: "PDF compilation failed.",
          stage_name: "compile_pdf",
          failure_type: "pdf_compile_error",
        })}
        run={makeRunMetadata()}
        progress={makeProgressState()}
        result={makeGenerationResult()}
        onRetry={vi.fn()}
        onStartNewRun={vi.fn()}
        onReturnToEditor={vi.fn()}
        debug={false}
      />,
    );

    expect(screen.queryByText("Diagnostics")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show details" }));

    expect(screen.getByText("Diagnostics")).toBeInTheDocument();
    expect(screen.getByText("Failure type")).toBeInTheDocument();
  });
});
