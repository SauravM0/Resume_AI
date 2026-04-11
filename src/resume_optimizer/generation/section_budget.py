"""Deterministic content-budget helpers for Phase 5 section assembly."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import AssemblyBudgetSignals, PageConstraints

_MAX_TOTAL_BULLETS_BY_PAGE_COUNT = {
    1: 8,
    2: 14,
}


def resolve_total_bullet_budget(page_constraints: PageConstraints) -> int:
    """Return the deterministic total bullet budget for the configured page count."""

    return _MAX_TOTAL_BULLETS_BY_PAGE_COUNT[page_constraints.target_page_count]


@dataclass(slots=True)
class BulletBudgetTracker:
    """Track deterministic bullet-budget usage during section assembly."""

    page_constraints: PageConstraints
    max_total_bullets: int = field(init=False)
    used_total_bullets: int = 0
    omitted_item_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.max_total_bullets = resolve_total_bullet_budget(self.page_constraints)

    @property
    def remaining_bullet_budget(self) -> int:
        return max(0, self.max_total_bullets - self.used_total_bullets)

    def can_take(self, count: int = 1) -> bool:
        return self.used_total_bullets + count <= self.max_total_bullets

    def consume(self, count: int = 1) -> None:
        if count < 0:
            raise ValueError("bullet budget consumption cannot be negative")
        if not self.can_take(count):
            raise ValueError("bullet budget exceeded")
        self.used_total_bullets += count

    def note_omission(self, source_item_id: str) -> None:
        if source_item_id not in self.omitted_item_ids:
            self.omitted_item_ids.append(source_item_id)

    def to_signals(self) -> AssemblyBudgetSignals:
        return AssemblyBudgetSignals(
            target_page_count=self.page_constraints.target_page_count,
            max_total_bullets=self.max_total_bullets,
            used_total_bullets=self.used_total_bullets,
            remaining_bullet_budget=self.remaining_bullet_budget,
            within_budget=self.used_total_bullets <= self.max_total_bullets,
            omitted_item_ids=list(self.omitted_item_ids),
        )
