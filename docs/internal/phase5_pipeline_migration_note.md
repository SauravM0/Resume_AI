# Phase 5 Pipeline Migration Note

Compatibility note: references to "Phase 4 verification" in this document now mean the Phase 6 verification gate unless the text is explicitly describing an old compatibility contract.

## Old generation path

The old pipeline called the monolithic Phase 3 generator directly:

- assemble one broad `Phase3GenerationPayload`
- compute a deterministic section plan
- send a single broad LLM request
- repair the result with `phase3_output_validation`
- hand the repaired `Phase3GenerationResult` to verification and rendering

That path mixed selection-adjacent decisions, writing, formatting, provenance packaging, and fallback behavior in one generation step.

## New generation path

The pipeline now uses bounded Phase 5 modules inside `Phase3Service`:

1. map upstream selection and planning artifacts into `FullGenerationContext`
2. generate a bounded summary
3. rewrite bullets independently
4. render selected skills deterministically
5. assemble deterministic section payloads
6. run rewrite-policy enforcement and generation-quality validation
7. adapt the bounded outputs back into the legacy `Phase3GenerationResult` and `Phase3ValidationReport`

## Compatibility

- Verification still receives `Phase3GenerationResult`
- Rendering still receives the verified Phase 3-compatible shape
- Upstream Phase 2 selection behavior is unchanged
- The stage output now also carries bounded generation artifacts for inspection and persistence

## Why this is safer

- strategy stays upstream
- generation modules are smaller and bounded
- rewrite policy enforcement runs before the Phase 6 verification gate
- quality validation runs before verification/rendering
- assembly is deterministic and traceable
