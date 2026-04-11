"""Phase 5 rendering regression tests.

This suite is intended to catch failures where verified structured content no
longer maps into safe, deterministic LaTeX output. Rendering regressions are
dangerous in this product because a resume can pass verification but still ship
with missing sections, leaked placeholders, unsafe special characters, broken
PDF compilation, or insufficient diagnostics. Required placeholders, escaping,
layout trimming decisions, compile failures, and privacy-aware diagnostics must
never silently break.
"""
