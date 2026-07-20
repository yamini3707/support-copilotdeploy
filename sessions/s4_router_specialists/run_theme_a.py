"""
Run ONLY the Theme A (field-comparison) cases through the router→specialist GRAPH.

These are the cases the monolith couldn't do (seat_ceiling, blocked_downgrade, over_provisioned).
The account specialist now handles them from GENERAL principles ("look up the subscription and plan
catalog; answer from the actual seats/limits") — not per-ticket scripts.

    python3 sessions/s4_router_specialists/run_theme_a.py
"""

import io
import json
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from sessions.s4_router_specialists.graph import classify
from eval.scoring import score_case

CASE_KEYS = ["seat_ceiling", "blocked_downgrade", "over_provisioned"]


def main():
    cases = [c for c in json.load(open(os.path.join(ROOT, "data", "train.json")))
             if c["id"].split("_", 2)[-1] in CASE_KEYS]

    total = 0.0
    for c in cases:
        with redirect_stdout(io.StringIO()):
            r = classify(c["ticket"], c["customer_context"])
            s = score_case(r, c, use_judge=True)
        total += s["composite"]
        print("\n" + "=" * 90)
        print(f"{c['id']}   score {s['composite']:.2f}   cat={r['category']}")
        print(f"  ticket: {c['ticket']}")
        print(f"  tools:  {[t['tool'] for t in r['tool_calls']]}")
        print(f"  answer: {r['answer']}")

    print("\n" + "=" * 90)
    print(f"AVERAGE (Theme A, graph): {total / len(cases) * 100:.1f}   (n={len(cases)})")


if __name__ == "__main__":
    main()
