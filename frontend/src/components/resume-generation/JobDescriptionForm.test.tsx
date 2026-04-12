import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { JobDescriptionForm } from "./JobDescriptionForm";
import { renderWithWorkflow } from "../../test/testUtils";

describe("JobDescriptionForm", () => {
  it("shows accessible labels and blocks invalid submission", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    renderWithWorkflow(
      <JobDescriptionForm
        debugVisible={false}
        onDebugToggle={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByLabelText("Paste the job description")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start generation" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Start generation" }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits a valid request and forwards debug mode when selected", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const onDebugToggle = vi.fn();

    renderWithWorkflow(
      <JobDescriptionForm
        debugVisible={false}
        onDebugToggle={onDebugToggle}
        onSubmit={onSubmit}
      />,
    );

    await user.type(
      screen.getByLabelText("Paste the job description"),
      "Senior software engineer role requiring React, TypeScript, accessibility, verification, structured content generation, team collaboration, backend integration, and operational debugging across resume workflow tooling in production.",
    );

    await user.click(screen.getByRole("button", { name: "Show advanced settings" }));
    await user.click(screen.getByRole("checkbox", { name: /Debug mode/i }));
    await user.click(screen.getByRole("button", { name: "Start generation" }));

    expect(onDebugToggle).toHaveBeenCalledWith(true);
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        job_description_text: expect.stringContaining("Senior software engineer role"),
        source_profile_path: "data/master_profile.example.json",
        template_id: "ats_standard",
        persist_intermediate_artifacts: true,
      }),
    );
  });

  it("shows loading and disabled states while a run is active", () => {
    renderWithWorkflow(
      <JobDescriptionForm
        disabled
        submitState="submitting"
        debugVisible={false}
        onDebugToggle={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Submitting run..." })).toBeDisabled();
  });
});
