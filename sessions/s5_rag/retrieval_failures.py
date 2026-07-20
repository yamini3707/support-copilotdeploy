"""
The RAG "failure gallery" — runs ONLY the cases where naive dense retrieval fails, and spells out
what's wrong with each and which technique fixes it. Use this live in class so you don't have to
remember which cases break.

(Hybrid is excluded on purpose — our eval showed dense already handles exact tokens at this scale,
so hybrid isn't justified here.)

    python3 sessions/s5_rag/retrieval_failures.py
"""

import json
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from rag.search import search_kb

# slice → (what's wrong, the fix)
SLICES = {
    "metadata": ("query doesn't name the plan, so the wrong/generic tier is retrieved & ranked first",
                 "METADATA FILTER by the customer's plan"),
    "rerank":   ("the right doc IS retrieved but buried under near-duplicate variants — never ranked #1",
                 "RERANKING (reorder the retrieved set so the best is #1)"),
    "hyde":     ("lay wording misses the technical doc entirely (vocabulary gap)",
                 "QUERY REWRITE / HyDE (search with an answer-shaped query)"),
    "abstention": ("nothing in the KB answers this, but the retriever returns docs anyway",
                   "RELEVANCE GRADING / ABSTENTION (CRAG) — refuse instead of fabricating"),
}


def rank_of(gold, retrieved_unique):
    for g in gold:
        if g in retrieved_unique:
            return retrieved_unique.index(g) + 1, g   # 1-indexed
    return None, (gold[0] if gold else None)


def main():
    cases = json.load(open(os.path.join(ROOT, "data", "rag_cases.json")))
    for slice_, (whats_wrong, fix) in SLICES.items():
        group = [c for c in cases if c["slice"] == slice_]
        print("\n" + "█" * 96)
        print(f"  SLICE: {slice_.upper()}   ({len(group)} cases)")
        print(f"  WHAT'S WRONG : {whats_wrong}")
        print(f"  FIX (next)   : {fix}")
        print("█" * 96)

        for c in group:
            hits = search_kb(c["ticket"], k=5, mode="dense")
            uniq = list(dict.fromkeys(h["doc_id"] for h in hits))
            print(f"\n  • {c['id']}  (plan={c['customer_context']['plan']})")
            print(f"    ticket : {c['ticket']}")
            if not c["answerable"]:
                print(f"    gold   : (none — the agent SHOULD abstain / escalate)")
                print(f"    top-3  : {uniq[:3]}")
                print(f"    WRONG  : retriever surfaced those anyway → grounding on them = a made-up answer")
                continue
            print(f"    gold   : {c['gold_docs']}")
            print(f"    top-5  : " + ", ".join(("✓" + d if d in c['gold_docs'] else d) for d in uniq))
            rank, g = rank_of(c["gold_docs"], uniq)
            if rank is None:
                print(f"    WRONG  : gold '{g}' NOT retrieved at all → the agent answers from the wrong docs")
            elif rank == 1:
                print(f"    (ok)   : gold ranked #1 — this one actually passes")
            else:
                print(f"    WRONG  : gold '{g}' is only at rank #{rank}; #1 is '{uniq[0]}' (a wrong/related doc)")

    print("\n" + "█" * 96)
    print("  Each slice above = a measured retrieval failure → the technique on its FIX line.")
    print("█" * 96 + "\n")


if __name__ == "__main__":
    main()
