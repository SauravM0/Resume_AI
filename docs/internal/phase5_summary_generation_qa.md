# Phase 5 Summary QA Note

Expected behavior:
- The summary generator writes one short summary from bounded structured inputs only.
- It should sound different for backend, frontend, data, and management contexts because role family and organizational mode are explicit inputs.
- It should only surface tools, themes, domain language, and leadership signals that are supported by upstream evidence.
- It should stay short, recruiter-safe, and free of filler phrases.

Fallback behavior:
- If the model returns malformed JSON, unsupported evidence IDs, blocked filler language, unsupported numbers, or unsupported leadership language, the service replaces the summary with a deterministic bounded fallback.
- The fallback stays conservative and uses only role label, supported tools, supported themes, and supported leadership support when available.

Non-goals:
- The summary generator does not decide which items belong in the resume.
- The summary generator does not invent page strategy or overall story strategy.
- The summary generator does not rewrite bullets or assemble sections.
