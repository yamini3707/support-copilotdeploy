"""
labeling.py — INSTRUCTOR-SIDE priority rule (see PROJECT_DESIGN.md §4).

Priority is a RULE, not a vibe, so every label is defensible and reverse-engineerable.
Factors:
  impact ∈ {blocked, degraded, inquiry}   (blocked = cannot use core product)
  scope  ∈ {org, single}
  plan   ∈ {free, pro, business, enterprise}
  is_financial: active money harm (double charge, wrong charge) → floor at 'medium'

Base (impact × scope), then plan bump, then billing floor.
"""

PRIORITIES = ["low", "medium", "high", "urgent"]

_BASE = {
    ("blocked", "org"): "urgent",
    ("blocked", "single"): "high",
    ("degraded", "org"): "high",
    ("degraded", "single"): "medium",
    ("inquiry", "org"): "low",
    ("inquiry", "single"): "low",
}


def _clamp(i: int) -> int:
    return max(0, min(len(PRIORITIES) - 1, i))


def priority_rule(impact: str, scope: str, plan: str, is_financial: bool = False) -> str:
    p = PRIORITIES.index(_BASE[(impact, scope)])

    # Plan bump: enterprise always +1; business +1 only if the issue actually hurts (blocked/degraded)
    if plan == "enterprise":
        p = _clamp(p + 1)
    elif plan == "business" and impact in ("blocked", "degraded"):
        p = _clamp(p + 1)

    # Billing floor
    if is_financial:
        p = max(p, PRIORITIES.index("medium"))

    return PRIORITIES[p]


if __name__ == "__main__":
    # quick sanity: the PROJECT_DESIGN examples
    assert priority_rule("blocked", "org", "enterprise") == "urgent"
    assert priority_rule("degraded", "single", "pro", is_financial=True) == "medium"
    assert priority_rule("blocked", "single", "pro") == "high"       # API 500 blocking a Pro integration
    assert priority_rule("inquiry", "single", "free") == "low"
    print("priority_rule sanity checks pass")
