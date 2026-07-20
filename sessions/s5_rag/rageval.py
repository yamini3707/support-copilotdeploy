"""
rageval.py — shared scorer for the step scripts.

Given a retrieval function fn(query, plan) -> [doc_id, ...] (ordered), print per-slice
Recall@1/@3/@5 over the engineered RAG cases. Reused by every step_*.py so they stay short.
"""

import json
import os
from collections import defaultdict

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
CASES = json.load(open(os.path.join(ROOT, "data", "rag_cases.json")))


def recall_at(retrieved, gold, k):
    top = list(dict.fromkeys(retrieved))[:k]
    return len([g for g in gold if g in top]) / len(gold) if gold else None


def per_slice(fn):
    """fn(query, plan) -> ordered list of doc_ids. Returns {slice: (r1, r3, r5, n)}."""
    agg = defaultdict(lambda: {"r1": [], "r3": [], "r5": []})
    for c in CASES:
        if not c["answerable"]:
            continue
        got = fn(c["ticket"], c["customer_context"]["plan"])
        gold = c["gold_docs"]
        agg[c["slice"]]["r1"].append(recall_at(got, gold, 1))
        agg[c["slice"]]["r3"].append(recall_at(got, gold, 3))
        agg[c["slice"]]["r5"].append(recall_at(got, gold, 5))
    return {s: (sum(d["r1"]) / len(d["r1"]), sum(d["r3"]) / len(d["r3"]),
                sum(d["r5"]) / len(d["r5"]), len(d["r5"])) for s, d in agg.items()}


def report(fn, title):
    res = per_slice(fn)
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("  " + "-" * 60)
    print(f"  {'slice':12}{'Recall@1':>11}{'Recall@3':>11}{'Recall@5':>11}")
    for s, (r1, r3, r5, n) in res.items():
        print(f"  {s:12}{r1:>11.2f}{r3:>11.2f}{r5:>11.2f}")
    print("═" * 70)
    return res
