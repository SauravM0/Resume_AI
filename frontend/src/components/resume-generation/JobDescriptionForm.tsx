import { useState } from "react";
import type { FormEvent } from "react";

import type { GenerateResumeRequest } from "../../types/pipeline";

export interface JobDescriptionFormProps {
  disabled?: boolean;
  onSubmit: (request: Pick<GenerateResumeRequest, "job_description_text" | "job_posting_url">) => void;
}

export function JobDescriptionForm({ disabled = false, onSubmit }: JobDescriptionFormProps) {
  const [jobDescriptionText, setJobDescriptionText] = useState("");
  const [jobPostingUrl, setJobPostingUrl] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedDescription = jobDescriptionText.trim();
    if (!trimmedDescription) {
      return;
    }
    onSubmit({
      job_description_text: trimmedDescription,
      job_posting_url: jobPostingUrl.trim() || undefined,
    });
  }

  return (
    <form onSubmit={handleSubmit} aria-label="Generate resume">
      <label>
        Job description
        <textarea
          required
          rows={10}
          value={jobDescriptionText}
          onChange={(event) => setJobDescriptionText(event.currentTarget.value)}
          disabled={disabled}
          placeholder="Paste the target job description here."
        />
      </label>
      <label>
        Job posting URL
        <input
          type="url"
          value={jobPostingUrl}
          onChange={(event) => setJobPostingUrl(event.currentTarget.value)}
          disabled={disabled}
          placeholder="https://example.com/job"
        />
      </label>
      <button type="submit" disabled={disabled || !jobDescriptionText.trim()}>
        {disabled ? "Generating..." : "Generate resume"}
      </button>
    </form>
  );
}
