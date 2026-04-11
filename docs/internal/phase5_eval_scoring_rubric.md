# Phase 5 Eval Scoring Rubric

This rubric is used by the deterministic Phase 5 regression harness in `resume_optimizer.phase5_eval`.

## Check Dimensions

`summary_quality`
- Pass when a summary exists when required, stays within the case word budget, and does not rely on a forbidden fallback path unless the case explicitly allows it.

`bullet_faithfulness_indicators`
- Pass when rewritten bullets do not fall back to normalized source text unless the case explicitly allows bullet fallback.

`role_family_style_adherence`
- Pass when the final summary and bullets include at least one expected role-family or organization-mode term for the case.
- The check uses case-defined required terms first and falls back to the registered role-style policy vocabulary clusters.

`section_balance`
- Pass when the assembled output meets the case’s required section shape:
  - summary present when required
  - minimum experience/project counts met
  - skills section present when required
  - certification section present when required
  - omissions recorded when required

`omission_traceability`
- Pass when content that was planned but not assembled is explicitly represented in `omitted_items_with_reasons` for cases that require omission traceability.

`skills_compactness`
- Pass when rendered skill lines do not exceed the case cap.

`generation_quality_issues`
- Pass when hard failures are absent unless explicitly allowed, and all case-required warning dimensions are present.

`red_flags`
- Pass when banned phrases for the case do not appear in final summary or bullet text.

## Interpretation

- A case passes only when every check passes.
- The aggregate baseline is descriptive, not aspirational. Failing cases are valuable because they show exactly where the current branch is still weak.
- The baseline snapshot should only change when the actual Phase 5 behavior changes.

## Expected Use

- Review the text summary for a quick pass/fail scan.
- Review `baseline_snapshot.json` for the actual bounded inputs, generated artifacts, and unmet expectations.
- Use diffs in the baseline snapshot to detect regressions or quality improvements over time.
