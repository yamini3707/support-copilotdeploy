"""
A/B test: does the "duplicate / already-refunded" prompt guidance help, on the claim-vs-reality cases?

OLD = the prompt WITHOUT any duplicate/already-refunded guidance at all (the true baseline).
NEW = the prompt WITH the current guidance (trust only the description's duplicate flag; and for an
already-refunded invoice, tell the customer the refund is underway).

Runs ONLY the claim-vs-reality cases through both prompts and prints a side-by-side comparison.
Nothing in agent.py's prompt is changed — we inject each version via classify(system=...).

    python3 sessions/s3_tools/compare_duplicate_prompt.py
"""

import io
import json
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from sessions.s3_tools.agent import classify, SYSTEM
from eval.scoring import score_case

CASE_KEYS = ["phantom_duplicate", "phantom_amount", "already_refunded"]

# The guidance block currently live in agent.py (this is what NEW adds and OLD lacks).
GUIDANCE_BLOCK = """WHAT COUNTS AS A DUPLICATE: the ONLY reliable signal is that an invoice's description flags it as a
duplicate. The same amount — even on the same date — is NOT necessarily a duplicate (a customer may
have legitimately made two purchases). If a customer claims they were "charged twice" but no invoice
is flagged as a duplicate, tell them there is no duplicate and no refund is needed.
ALREADY REFUNDED: if the invoice status is already "refunded", do NOT refund it again — tell the
customer the refund is already underway and the amount should appear in their account within a few days."""

# NEW = the current prompt (with the guidance). OLD = the same prompt with the guidance REMOVED.
SYSTEM_NEW = SYSTEM
SYSTEM_OLD = SYSTEM.replace(GUIDANCE_BLOCK + "\n\n", "")
assert SYSTEM_OLD != SYSTEM_NEW and GUIDANCE_BLOCK not in SYSTEM_OLD, \
    "GUIDANCE_BLOCK did not match agent.py — update it to match exactly."


def _run(classify_system, case):
    with redirect_stdout(io.StringIO()):
        r = classify(case["ticket"], case["customer_context"], system=classify_system)
        s = score_case(r, case, use_judge=True)
    return r, s


def main():
    cases = [c for c in json.load(open(os.path.join(ROOT, "data", "train.json")))
             if c["id"].split("_", 2)[-1] in CASE_KEYS]

    old_total = new_total = 0.0
    for c in cases:
        ro, so = _run(SYSTEM_OLD, c)
        rn, sn = _run(SYSTEM_NEW, c)
        old_total += so["composite"]
        new_total += sn["composite"]
        print("\n" + "=" * 90)
        print(f"{c['id']}   {c['ticket']}")
        print(f"  OLD  score {so['composite']:.2f}  refunded={any(t['tool']=='issue_refund' for t in ro['tool_calls'])}")
        print(f"       {ro['answer']}")
        print(f"  NEW  score {sn['composite']:.2f}  refunded={any(t['tool']=='issue_refund' for t in rn['tool_calls'])}")
        print(f"       {rn['answer']}")

    n = len(cases)
    print("\n" + "=" * 90)
    print(f"AVERAGE — OLD: {old_total / n * 100:.1f}   NEW: {new_total / n * 100:.1f}   (n={n})")


if __name__ == "__main__":
    main()
