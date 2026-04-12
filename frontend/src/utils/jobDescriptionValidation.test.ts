import {
  JOB_DESCRIPTION_MAX_LENGTH,
  JOB_DESCRIPTION_MIN_LENGTH,
  validateJobDescription,
} from "./jobDescriptionValidation";

describe("validateJobDescription", () => {
  it("flags empty input", () => {
    expect(validateJobDescription("   ")).toEqual({
      isValid: false,
      errors: ["Paste the target job description before starting a run."],
    });
  });

  it("flags too-short input", () => {
    const result = validateJobDescription("a".repeat(JOB_DESCRIPTION_MIN_LENGTH - 1));

    expect(result.isValid).toBe(false);
    expect(result.errors[0]).toContain("too short");
  });

  it("flags too-long input", () => {
    const result = validateJobDescription("a".repeat(JOB_DESCRIPTION_MAX_LENGTH + 1));

    expect(result.isValid).toBe(false);
    expect(result.errors[0]).toContain("too long");
  });

  it("accepts realistic valid input", () => {
    const result = validateJobDescription(
      "Senior React engineer role requiring accessibility, TypeScript, strong product judgment, backend collaboration, structured content generation, verification, and production workflow ownership across a resume generation platform.",
    );

    expect(result).toEqual({
      isValid: true,
      errors: [],
    });
  });
});
