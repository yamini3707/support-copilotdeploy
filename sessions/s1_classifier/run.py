"""
Run the Session 1 classifier against the golden dataset and print the score report.

    python3 sessions/s1_classifier/run.py          # full scoring (needs OPENAI_API_KEY in .env)
    python3 sessions/s1_classifier/run.py --fast    # skip the LLM judge (routing/tools/retrieval only, cheaper)

Prints per-case results, one overall score, and a per-dimension breakdown.
"""

import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from eval.harness import evaluate, print_report
from sessions.s1_classifier.agent import classify

DATA = os.path.join(ROOT, "data", "train.json")


def main():
    use_judge = "--fast" not in sys.argv
    cases, results = evaluate(classify, DATA, use_judge=use_judge)
    print_report(cases, results)


if __name__ == "__main__":
    main()
