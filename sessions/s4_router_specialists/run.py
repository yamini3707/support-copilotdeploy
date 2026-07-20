"""
Run the router→specialist graph over the golden dataset and print the score report.

    python3 sessions/s4_router_specialists/run.py            # full suite (needs OPENAI_API_KEY)
    python3 sessions/s4_router_specialists/run.py --fast      # skip the LLM judge (cheaper)

Compare the overall + per-dimension scores against the Session 3 monolith (sessions/s3_tools).
The interesting question isn't just "is it higher" — it's whether category edge cases (Theme A)
now pass WITHOUT the account rules bleeding into other categories.
"""

import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from eval.harness import evaluate, print_report
from sessions.s4_router_specialists.graph import classify

DATA = os.path.join(ROOT, "data", "train.json")


def main():
    use_judge = "--fast" not in sys.argv
    cases, results = evaluate(classify, DATA, use_judge=use_judge)
    print_report(cases, results)


if __name__ == "__main__":
    main()
