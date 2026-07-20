"""
harness.py — the evaluation library.

    from eval.harness import evaluate, print_report
    cases, results = evaluate(classify, "data/train.json", use_judge=True)
    print_report(cases, results)

Prints per-case (input / expected / got / score) plus one overall score AND a per-dimension
breakdown (routing / tool_use / retrieval / grounded / memory / safety) so you can see which
capability is dragging the score — and watch each one climb as later sessions add it.
"""

import json

from eval.schema import validate
from eval.scoring import WEIGHTS, score_case

_DIMS = ["category", "priority", "requires_human", "tool_use", "retrieval", "grounded", "memory"]


def evaluate(classify, data_path: str, use_judge: bool = True):
    """Run `classify(ticket, context)` over every case and score it. Returns (cases, results)."""
    cases = json.load(open(data_path))
    results = []
    for case in cases:
        try:
            resp = classify(case["ticket"], case.get("customer_context"))
            errors = validate(resp)
        except Exception as e:
            resp, errors = {}, [f"agent raised: {e}"]

        if errors:
            scored = {"dims": {d: None for d in _DIMS}, "safety": "pass", "composite": 0.0}
        else:
            scored = score_case(resp, case, use_judge=use_judge)

        results.append({
            "id": case["id"],
            "expected": case["expected"],
            "got": {k: resp.get(k) for k in ("category", "priority", "requires_human")},
            "answer": resp.get("answer", ""),
            "errors": errors,
            **scored,
        })
    return cases, results


def print_report(cases, results) -> float:
    for case, r in zip(cases, results):
        e, g = r["expected"], r["got"]
        print(f"\n{r['id']}   score {r['composite']:.2f}   safety={r['safety']}")
        print(f"  in:  {case['ticket']}")
        print(f"  exp: {e['category']} / {e['priority']} / human={e['requires_human']}"
              f"   tools={e.get('required_tools') or '-'}  docs={e.get('required_docs') or '-'}")
        print(f"  got: {g['category']} / {g['priority']} / human={g['requires_human']}")
        print(f"  answer: {r['answer']}")
        if r["errors"]:
            print(f"  ⚠ {r['errors']}")

    n = len(results)
    overall = sum(r["composite"] for r in results) / n

    # per-dimension average over cases where the dimension applied
    print("\n" + "=" * 60)
    print(f"  OVERALL SCORE: {overall * 100:.1f} / 100   (n={n})")
    print("  " + "-" * 40)
    for d in _DIMS:
        vals = [r["dims"][d] for r in results if r["dims"].get(d) is not None]
        if vals:
            print(f"  {d:<16} {sum(vals) / len(vals) * 100:5.1f}   (applies to {len(vals)})")
    violations = sum(1 for r in results if r["safety"] == "violation")
    print(f"  {'safety':<16} {'PASS' if not violations else str(violations) + ' VIOLATION(S)'}")
    print("=" * 60 + "\n")
    return overall
