"""
Run the Session 2 prompt-engineering experiments and compare them.

    python3 sessions/s2_prompt_engineering/run.py               # all 4 variants, full scoring
    python3 sessions/s2_prompt_engineering/run.py --fast         # skip the LLM judge (cheaper)
    python3 sessions/s2_prompt_engineering/run.py few_shot        # just one variant, full report

With no variant name it runs all four and prints a one-line-per-variant leaderboard so you can
see which strategy wins live. Naming a variant prints that variant's full per-case report.
"""

import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from eval.harness import evaluate, print_report
from sessions.s2_prompt_engineering.variants import VARIANTS

DATA = os.path.join(ROOT, "data", "train.json")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_judge = "--fast" not in sys.argv

    if args and args[0] in VARIANTS:
        cases, results = evaluate(VARIANTS[args[0]], DATA, use_judge=use_judge)
        print(f"\n### variant: {args[0]}")
        print_report(cases, results)
        return

    print("\nRunning all variants (this makes several LLM calls per case)...\n")
    board = []
    for name, fn in VARIANTS.items():
        _, results = evaluate(fn, DATA, use_judge=use_judge)
        overall = sum(r["composite"] for r in results) / len(results)
        routing = [r["dims"]["category"] for r in results if r["dims"].get("category") is not None]
        route_avg = sum(routing) / len(routing) if routing else 0
        invalid = sum(1 for r in results if r["errors"])
        board.append((name, overall, route_avg, invalid))

    board.sort(key=lambda x: -x[1])
    print("=" * 56)
    print(f"  {'variant':<14}{'overall':>9}{'category':>10}{'invalid':>9}")
    print("  " + "-" * 42)
    for name, overall, route, invalid in board:
        print(f"  {name:<14}{overall * 100:>8.1f}{route * 100:>10.1f}{invalid:>9}")
    print("=" * 56)
    print("  (overall is low for ALL — routing is ~20% of the job; tools/RAG/memory come next)\n")


if __name__ == "__main__":
    main()
