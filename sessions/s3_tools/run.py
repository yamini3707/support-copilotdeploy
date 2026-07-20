"""
Run the Session 3 tool-using agent against the golden dataset and print the score report.

    python3 sessions/s3_tools/run.py          # full scoring (needs OPENAI_API_KEY in .env)
    python3 sessions/s3_tools/run.py --fast    # skip the LLM judge (routing/tools/retrieval only)

Compare the tool_use and grounded lines against Session 1/2 — that jump is what tools bought.
"""

import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from eval.harness import evaluate, print_report
from sessions.s3_tools.agent import classify

DATA = os.path.join(ROOT, "data", "train.json")


def main():
    use_judge = "--fast" not in sys.argv
    cases, results = evaluate(classify, DATA, use_judge=use_judge)
    print_report(cases, results)


if __name__ == "__main__":
    main()
