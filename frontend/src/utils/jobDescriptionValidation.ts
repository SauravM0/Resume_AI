export const JOB_DESCRIPTION_MIN_LENGTH = 120;
export const JOB_DESCRIPTION_MAX_LENGTH = 20000;

export interface JobDescriptionValidationResult {
  isValid: boolean;
  errors: string[];
}

export function validateJobDescription(text: string): JobDescriptionValidationResult {
  const normalized = text.trim();
  const errors: string[] = [];

  if (!normalized) {
    errors.push("Paste the target job description before starting a run.");
  }

  if (normalized && normalized.length < JOB_DESCRIPTION_MIN_LENGTH) {
    errors.push(
      `Job description is too short. Paste a fuller posting with responsibilities and requirements (${JOB_DESCRIPTION_MIN_LENGTH}+ characters recommended).`,
    );
  }

  if (normalized.length > JOB_DESCRIPTION_MAX_LENGTH) {
    errors.push(
      `Job description is too long. Reduce it below ${JOB_DESCRIPTION_MAX_LENGTH.toLocaleString()} characters.`,
    );
  }

  return {
    isValid: errors.length === 0,
    errors,
  };
}
