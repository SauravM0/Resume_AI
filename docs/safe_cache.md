# Safe Cache

The backend now uses a local deterministic cache for a small set of safe intermediate artifacts. The shared cache implementation lives in [storage.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/cache/storage.py), cache keys live in [keys.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/cache/keys.py), and cache metrics live in [metrics.py](/mnt/c/Users/Alexa/OneDrive/Desktop/ResumeAI/backend/app/cache/metrics.py).

## What Is Cached

Cached candidates are intentionally narrow and deterministic:

- normalized profile load from disk
  Key inputs: profile file content hash, file path, file encoding, loader/normalizer code hash
- normalized source-profile stage output
  Key inputs: normalized profile hash, normalization code hash
- parsed job-description result
  Key inputs: exact job-description hash, parser model/config hash, parser implementation hash
- deterministic Phase 2 candidate artifacts
  Key inputs: profile hash, evidence extraction/enrichment code hash
- deterministic Phase 2 job-ranking features
  Key inputs: normalized job-analysis hash, Phase 2 config hash, skill-normalization code hash
- loaded LaTeX template metadata and content
  Key inputs: template id, template version, template checksum, registry validation code hash

## What Is Not Cached

The cache explicitly avoids unsafe reuse:

- final PDFs or full final resume outputs across different request contexts
- verification results when any source input changes
- non-deterministic generation outputs
- partial outputs that could go stale without visible invalidation

## Invalidation Logic

Cache keys include all known correctness inputs, so changing any of the following forces a miss instead of silent reuse:

- job description text
- source profile content or profile id
- template file checksum or template version
- relevant deterministic config objects
- parser model selection
- implementation code hashes for the cached deterministic boundary

Entries also use TTLs and a bounded on-disk size. Expired entries are deleted on read and counted as stale invalidations. Explicit invalidation is available through `LocalJsonCache.invalidate(...)` and `LocalJsonCache.clear_namespace(...)`.

## Metrics

Cache metrics are written to `data/metrics/cache_metrics.jsonl` by default. The summary helper reports:

- hit count and miss count
- hit rate
- stale invalidation count
- estimated latency saved in milliseconds
- per-namespace breakdown

`latency_saved_estimate_ms` is based on the original miss-time compute duration stored with the cached entry, so it is only an estimate for repeated local runs.
