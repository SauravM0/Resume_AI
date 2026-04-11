# Phase 5 Bounded Generation Contract

Old contract:
- One broad Phase 3 payload went into one broad generator call.
- The model could decide summary phrasing, bullet rewrites, skill highlighting, omission behavior, warning behavior, and some section-level strategy in the same response.
- The deterministic section plan existed, but the generator was not bounded to it.

New contract:
- Upstream code decides selected evidence, section plan, story strategy, page constraints, and style policy.
- Generation inputs are split into bounded task contracts:
  - `SummaryGenerationInput`
  - `BulletRewriteInput`
  - `SkillPresentationInput`
  - `SectionAssemblyInput`
  - `FullGenerationContext`
- Generation outputs are split into bounded result contracts:
  - `SummaryGenerationOutput`
  - `BulletRewriteOutput`
  - `SkillPresentationOutput`
  - `SectionAssemblyOutput`
  - `GenerationQualitySignals`

What the new contract forbids:
- The generator cannot decide which experiences, projects, skills, or certifications belong in scope.
- The generator cannot invent page-level story structure.
- The generator cannot assemble sections from items that were not selected and planned upstream.
- The generator cannot reference source items or bullet IDs outside the bounded provenance contract.

Why this is safer:
- Strategic selection is deterministic and inspectable before any generation happens.
- Each generation task has a smaller, easier-to-validate input surface.
- Provenance failures are caught at schema boundaries instead of after a vague model response.
- Section assembly cannot drift away from the approved section plan.
