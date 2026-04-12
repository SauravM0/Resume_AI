import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { GenerationResult } from "./GenerationResult";
import { renderWithWorkflow } from "../../test/testUtils";
import { makeGenerationResult } from "../../test/fixtures/resumeGeneration";

describe("GenerationResult", () => {
  it("renders a clean success summary and hides diagnostics by default", () => {
    renderWithWorkflow(
      <GenerationResult
        result={makeGenerationResult()}
        onStartNewRun={vi.fn()}
      />,
    );

    expect(screen.getByText("Successful run")).toBeInTheDocument();
    expect(screen.getByText("Result summary")).toBeInTheDocument();
    expect(screen.queryByText("Diagnostics are not available for this run")).not.toBeInTheDocument();
    expect(screen.getByText("Selection summary")).toBeInTheDocument();
  });

  it("renders partial success honestly and reveals diagnostics on demand", async () => {
    renderWithWorkflow(
      <GenerationResult
        debug
        result={makeGenerationResult({
          overall_status: "succeeded_with_warnings",
          verification_warnings: [
            {
              message: "Claim needs review.",
              severity: "warning",
            },
          ],
          diagnostics: {
            summary: "Completed with warnings",
            messages: ["Repair path used"],
            warnings: [],
            fallback_repairs: [
              {
                applied: true,
                strategy: "safe_claim_filter",
              },
            ],
          },
          downloadable_outputs: [
            {
              kind: "pdf",
              storage_kind: "url",
              reference: "https://example.com/run.partial/resume.pdf",
              file_name: "resume.pdf",
            },
            {
              kind: "structured_json",
              storage_kind: "url",
              reference: "https://example.com/run.partial/result.json",
              file_name: "result.json",
            },
          ],
        })}
        onStartNewRun={vi.fn()}
      />,
    );

    expect(screen.getAllByText("Success with warnings").length).toBeGreaterThan(0);
    expect(screen.getByText("Review before using")).toBeInTheDocument();
    expect(screen.getByText("Warnings present")).toBeInTheDocument();

    expect(screen.getByText("Repair path used")).toBeInTheDocument();
    expect(screen.getByText("Claim needs review.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inspect structured output" })).toBeInTheDocument();
  });
});
