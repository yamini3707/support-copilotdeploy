"""
Run the CURRENT tool agent on only the Theme A (field-comparison diagnosis) cases and report.

No prompt changes yet — this is the baseline measurement: can the agent diagnose these by
comparing seats_used / seats_purchased / plan cap from get_subscription?

    python3 sessions/s3_tools/run_theme_a.py
"""

import io
import json
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from sessions.s3_tools.agent import classify
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
        print(f"{c['id']}   score {s['composite']:.2f}")
        print(f"  ticket: {c['ticket']}")
        print(f"  tools:  {[t['tool'] for t in r['tool_calls']]}")
        print(f"  answer: {r['answer']}")
        print(f"  expect: {c['expected']['must_mention']}")

    print("\n" + "=" * 90)
    print(f"AVERAGE (Theme A, current agent): {total / len(cases) * 100:.1f}   (n={len(cases)})")


if __name__ == "__main__":
    main()
