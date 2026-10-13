"""Shared synthetic owner/action destination contract for V2 test harnesses.

Not a runtime policy, permission grant, canonical record registry, or provider
capability claim. Independent oracle expectations must not import this mapping.
"""
CONTRACT_VERSION = "s1-owner-contract-1"

DESTINATIONS = {
    "health": frozenset({"/Health/health-longitudinal-log.md",
                         "mock:mental-wellbeing-record"}),
    "home": frozenset({"mock:food-stock"}),
    "finance": frozenset({"/Finance/purchase-plan.md"}),
    "purchase": frozenset({"/Purchases/purchase-lifecycle.md"}),
    "calendar": frozenset({"mock:calendar"}),
}
OWNERS = frozenset(DESTINATIONS)
ACTION_DESTINATIONS = {
    "stock_decrement": ("home", "mock:food-stock"),
    "health_note": ("health", "/Health/health-longitudinal-log.md"),
    "mental_note": ("health", "mock:mental-wellbeing-record"),
    "finance_review": ("finance", "/Finance/purchase-plan.md"),
    "purchase_note": ("purchase", "/Purchases/purchase-lifecycle.md"),
    "calendar_create": ("calendar", "mock:calendar"),
}

# Construction-time consistency, never a replacement for independent testing.
assert all(owner in DESTINATIONS and dest in DESTINATIONS[owner]
           for owner, dest in ACTION_DESTINATIONS.values())
