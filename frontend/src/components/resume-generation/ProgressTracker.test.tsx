import { screen } from "@testing-library/react";

import { ProgressTracker } from "./ProgressTracker";
import { renderWithWorkflow } from "../../test/testUtils";
import {
  makeProgressState,
  makeRunMetadata,
} from "../../test/fixtures/resumeGeneration";

describe("ProgressTracker", () => {
  it("renders current, completed, retry, and fallback progress states", () => {
    renderWithWorkflow(
      <ProgressTracker
        run={makeRunMetadata({ run_id: "run.progress" })}
        overallStatus="phase_running"
        progress={makeProgressState({
          run_id: "run.progress",
          retry_notices: [
            {
              event_id: "retry-1",
              event_type: "retry_scheduled",
              run_id: "run.progress",
              timestamp: "2026-04-12T10:00:08.000Z",
              stage_name: "verify_generated_content",
              machine_status: "retrying",
              human_message: "Retry in progress",
              metadata: {},
            },
          ],
          fallback_notices: [
            {
              event_id: "fallback-1",
              event_type: "fallback_applied",
              run_id: "run.progress",
              timestamp: "2026-04-12T10:00:10.000Z",
              stage_name: "verify_generated_content",
              machine_status: "fallback_applied",
              human_message: "Repair path applied",
              metadata: { fallback_strategy: "safe_claim_filter" },
            },
          ],
          stages: [
            {
              stage_name: "ingest_job_description",
              machine_status: "succeeded",
              human_message: "Input accepted",
              updated_at: "2026-04-12T10:00:02.000Z",
            },
            {
              stage_name: "parse_job_description",
              machine_status: "succeeded",
              human_message: "Job requirements analyzed",
              updated_at: "2026-04-12T10:00:05.000Z",
            },
            {
              stage_name: "verify_generated_content",
              machine_status: "retrying",
              human_message: "Verification retry in progress",
              updated_at: "2026-04-12T10:00:10.000Z",
              metadata: {
                attempt_number: 2,
                fallback_strategy: "safe_claim_filter",
              },
            },
          ],
          completed_stages: [
            {
              stage_name: "ingest_job_description",
              machine_status: "succeeded",
              human_message: "Input accepted",
              updated_at: "2026-04-12T10:00:02.000Z",
            },
            {
              stage_name: "parse_job_description",
              machine_status: "succeeded",
              human_message: "Job requirements analyzed",
              updated_at: "2026-04-12T10:00:05.000Z",
            },
          ],
          current_stage: {
            stage_name: "verify_generated_content",
            machine_status: "retrying",
            human_message: "Verification retry in progress",
            updated_at: "2026-04-12T10:00:10.000Z",
            metadata: {
              attempt_number: 2,
              fallback_strategy: "safe_claim_filter",
            },
          },
          latest_event: {
            event_id: "progress-verify",
            event_type: "retry_scheduled",
            run_id: "run.progress",
            timestamp: "2026-04-12T10:00:10.000Z",
            stage_name: "verify_generated_content",
            machine_status: "retrying",
            human_message: "Verification retry in progress",
            metadata: {
              attempt_number: 2,
              fallback_strategy: "safe_claim_filter",
            },
          },
        })}
        debug
      />,
    );

    expect(screen.getByText("Run ID")).toBeInTheDocument();
    expect(screen.getByText("Retry in progress")).toBeInTheDocument();
    expect(screen.getByText("Reading job requirements")).toBeInTheDocument();
    expect(screen.getAllByText(/Fallback or repair used/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/retrying/i).length).toBeGreaterThan(0);
  });
});
