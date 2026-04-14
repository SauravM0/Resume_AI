# Phase 5 Generation Quality Rubric

Phase 5 generation quality validation is deterministic and inspectable. It is not a truth-verification layer. Its job is to catch weak writing, bad hygiene, and unstable resume phrasing before verification and rendering.

## Dimensions

- `repetition`
  Flags repeated bullets or repeated phrasing patterns across bullets.
- `generic_filler`
  Flags generic resume filler such as `results-driven` or `dynamic professional`.
- `keyword_stuffing`
  Flags repeated role or skill terms that make text feel mechanical.
- `summary_strength`
  Flags weak summary wording such as vague professional framing.
- `bullet_naturalness`
  Flags bullets that read stitched together or mechanically unnatural.
- `section_balance`
  Flags assembled output that is heavily imbalanced across major sections.
- `bullet_length`
  Flags bullets that are too long for resume use.
- `skills_compactness`
  Flags oversized or overly dense skills output.
- `summary_density`
  Flags summaries that are too thin to function as a credible summary.
- `claim_boundedness`
  Flags suspiciously broad claims even when they are not yet proven false.

## Severity usage

- `warning`
  The output is usable, but quality is weaker than desired.
- `error`
  The output should not pass unchanged.

## Suggested fallback actions

- `fallback_to_bounded_summary`
- `rewrite_summary_with_stronger_supported_themes`
- `trim_repeated_terms`
- `prefer_source_or_more_varied_rewrites`
- `prefer_simpler_rewrite_or_source_text`
- `fallback_to_source_or_trim`
- `reduce_groups_or_trim_skill_list`
- `deduplicate_skill_rendering`
- `trim_skill_section`
- `rebalance_sections_or_accept_planner_tradeoff`

## Integration points

- After summary generation
- After bullet rewriting
- After skill presentation
- After section assembly

## Design constraints

- Deterministic first
- Machine-readable issues
- Stable section and bullet references
- No strategy redesign inside the validator
- No relaxation of truth guardrails
