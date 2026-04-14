import { render } from "@testing-library/react";
import type { PropsWithChildren, ReactElement } from "react";

import { WorkflowGlobalStyles } from "../components/resume-generation/WorkflowUI";

function WorkflowTestShell({ children }: PropsWithChildren) {
  return (
    <div className="resume-workflow">
      <WorkflowGlobalStyles />
      {children}
    </div>
  );
}

export function renderWithWorkflow(ui: ReactElement) {
  return render(ui, {
    wrapper: WorkflowTestShell,
  });
}
