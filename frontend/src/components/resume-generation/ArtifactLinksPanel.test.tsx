import { screen } from "@testing-library/react";

import { ArtifactLinksPanel } from "./ArtifactLinksPanel";
import { renderWithWorkflow } from "../../test/testUtils";
import { makeGenerationResult } from "../../test/fixtures/resumeGeneration";

describe("ArtifactLinksPanel", () => {
  it("shows missing, failed, and partial artifact states clearly", () => {
    renderWithWorkflow(
      <ArtifactLinksPanel
        debug
        result={makeGenerationResult({
          downloadable_outputs: [
            {
              kind: "structured_json",
              storage_kind: "url",
              reference: "https://example.com/run.partial/result.json",
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
              uri: "https://example.com/run.partial/compile.log",
            },
          ],
        })}
      />,
    );

    expect(screen.getByText("PDF generation failed for this run.")).toBeInTheDocument();
    expect(screen.getByText("Structured output is available even though final PDF output is incomplete.")).toBeInTheDocument();
    expect(screen.getByText("Diagnostics output is available.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview PDF" })).toBeDisabled();
  });
});
