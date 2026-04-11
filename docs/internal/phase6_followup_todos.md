# Phase 6 Follow-up TODOs

- Replace legacy Phase 3 verification input contracts with bounded generation artifacts directly instead of Phase 3-compatible adapters.
- Move rendering input construction from verified legacy Phase 3 result to bounded assembled section artifacts.
- Add persistence schemas for bounded generation artifacts instead of storing them as generic JSON blobs.
- Add richer diagnostics surfacing for generation-quality scores and rewrite-policy outcomes in pipeline artifact viewers.
- Decide whether headline generation should remain omitted or be rebuilt as a bounded module.
- Add retry policies for summary-only and bullet-only regeneration when Phase 6 decides an item should be retried.
- Add verification rules that consume `quality_dimension` and `suggested_fallback_action` signals directly.
