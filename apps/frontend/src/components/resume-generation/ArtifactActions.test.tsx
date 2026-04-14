import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ArtifactActions } from "./ArtifactActions";
import { renderWithWorkflow } from "../../test/testUtils";
import { makeGenerationResult } from "../../test/fixtures/resumeGeneration";

describe("ArtifactActions", () => {
  it("renders run-scoped artifact states and exposes debug inspection actions", () => {
    renderWithWorkflow(
      <ArtifactActions
        debug
        result={makeGenerationResult({
          run_metadata: { run_id: "run.partial-artifacts" },
          downloadable_outputs: [
            {
              kind: "structured_json",
              storage_kind: "url",
              reference: "https://example.com/run.partial-artifacts/result.json",
              file_name: "result.json",
              content_type: "application/json",
            },
          ],
          render_artifacts: [
            {
              artifact_id: "artifact.compile-log",
              kind: "compile_log",
              stage_name: "compile_pdf",
              storage_backend: "url",
              schema_version: "1",
              uri: "https://example.com/run.partial-artifacts/compile.log",
            },
          ],
        })}
        onStartNewRun={vi.fn()}
      />,
    );

    expect(screen.getByText("run.partial-artifacts")).toBeInTheDocument();
    expect(screen.getByText("PDF generation failed for this run.")).toBeInTheDocument();
    expect(screen.getByText("This run produced outputs, but LaTeX source was not returned.")).toBeInTheDocument();
    expect(screen.getByText("Structured output is available even though final PDF output is incomplete.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview PDF" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Inspect structured output" })).toBeEnabled();
  });

  it("forwards start-new-run actions", async () => {
    const user = userEvent.setup();
    const onStartNewRun = vi.fn();

    renderWithWorkflow(
      <ArtifactActions result={makeGenerationResult()} onStartNewRun={onStartNewRun} />,
    );

    await user.click(screen.getByRole("button", { name: "Start new run" }));

    expect(onStartNewRun).toHaveBeenCalledTimes(1);
  });
});
