"""
Show the router's decisions: when it's confident it picks ONE specialist; when it's torn it
FANS OUT to the tied specialists (which then run in parallel in the graph).

    python3 sessions/s4_router_specialists/demo_routing.py

Cheap — this only calls the router node, not the specialists.
"""

import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from sessions.s4_router_specialists.graph import router, MARGIN

TICKETS = [
    # clear → single specialist
    ("I was charged twice this month, refund the duplicate.", {"plan": "pro"}),
    ("Our SSO is down for the whole team.", {"plan": "business"}),
    ("Hello!", {"plan": "free"}),
    # ambiguous → fan out to the tied specialists (parallel)
    ("Is SSO included in my plan and how much extra will it cost?", {"plan": "pro"}),
    ("My export is failing and I think I was double charged for it too.", {"plan": "business"}),
    ("something is wrong", {"plan": "pro"}),
]


def main():
    print(f"(fan out when top1 - top2 < MARGIN={MARGIN})\n")
    for ticket, ctx in TICKETS:
        route = router({"ticket": ticket, "context": ctx, "route": [], "specialist_outputs": []})["route"]
        tag = f"FAN-OUT → {route}" if len(route) > 1 else f"single  → {route[0]}"
        print(f"  {tag:32}  {ticket}")


if __name__ == "__main__":
    main()
