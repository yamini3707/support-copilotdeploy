"""
MEMORY · Step 6 — UNIFIED recall (graph + embedding), then answer with the agent.

Belt-and-suspenders retrieval (the Class-2 pattern): pull memory from BOTH
  - EMBEDDING over semantic + episodic memory (great for direct, word-overlapping facts), and
  - GRAPH traversal (great for indirect / multi-hop facts embedding misses),
merge + dedupe (tagging where each came from), inject the combined block, and let the s10 agent answer.

    python3 memory/unified_recall_demo.py
"""

import io
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from sessions.s10_full_agent.agent import classify
from memory.graph_build import build, _memory_items
from memory.graph_fetch import graph_fetch, embedding_rank
from langfuse import get_client

CID = "cust_enterprise_003"
CTX = {"customer_id": CID, "plan": "enterprise", "region": "US"}

CASES = [
    ("A", "We haven't received a single invoice all year — is something wrong with our account?", "F00"),
    ("B", "We'd like to turn on your new US-hosted analytics add-on. Can we just enable it?", "F01"),
]


def unified_recall(query, ents, edges, e2f, items, k=5, k_context=10):
    """Combine embedding retrieval (top-k) with graph traversal; dedupe, tag source.
    Entity extraction for the graph is enriched with a WIDER retrieval net (top-k_context) so the LLM
    can name specific entities (e.g. the parent company) that sit just outside the top-k. Returns
    ([(fact_id, source, text)], surfaced_entities, matched_nodes)."""
    text_of = dict(items)
    ranked = embedding_rank(query, items)
    emb_ids = [fid for _, fid, _ in ranked[:k]]
    context = "\n".join(f"- {t}" for _, _, t in ranked[:k_context])       # wide net, entity surfacing only
    terms, matched, graph_ids = graph_fetch(query, ents, edges, e2f, context=context)
    source = {}
    for fid in emb_ids:
        source[fid] = "EMBED"
    for fid in graph_ids:
        source[fid] = "BOTH" if fid in source else "GRAPH"
    return [(fid, source[fid], text_of[fid]) for fid in source], terms, matched


def _block(merged):
    lines = ["[MEMORY — retrieved facts about this customer. Honor any preferences, and CHECK for any "
             "constraint or conflict with the request before agreeing.]"]
    lines += [f"  - ({src}) {text}" for _, src, text in merged]
    return "\n".join(lines)


def main():
    print("\n" + "#" * 100)
    print("  MEMORY · UNIFIED RECALL — graph + embedding, merged, then answered by the agent")
    print("#" * 100)
    print("\n  building the memory graph ...")
    with redirect_stdout(io.StringIO()):
        ents, edges, e2f = build()
    items = _memory_items()

    for tag, query, bridge_fid in CASES:
        with redirect_stdout(io.StringIO()):
            merged, terms, matched = unified_recall(query, ents, edges, e2f, items)
            out = classify(f"{query}\n\n{_block(merged)}", CTX)

        print("\n" + "=" * 100)
        print(f"  CASE {tag}   QUERY: {query}")
        print(f"  entities surfaced (query + wide retrieval): {terms}")
        print(f"  graph nodes matched: {matched}")
        print("  RETRIEVED MEMORY (merged, tagged by source):")
        for fid, src, text in sorted(merged):
            star = "  ← ★ the bridge fact" if fid == bridge_fid else ""
            print(f"    [{src:5}] {fid}: {text[:72]}{star}")
        got = any(fid == bridge_fid for fid, _, _ in merged)
        print(f"\n  bridge fact {bridge_fid} in retrieved memory? {'YES ✅' if got else 'NO ❌'}")
        print(f"  AGENT ANSWER: {out['answer']}")

    print("\n" + "#" * 100)
    print("  Unified recall = EMBED (direct facts) + GRAPH (indirect facts). Case B's EU-residency fact")
    print("  now reaches the agent via GRAPH and it flags the conflict; Case A's parent-company fact is")
    print("  behind the customer hub — neither retriever reaches it (that's a job for CORE memory).")
    print("#" * 100 + "\n")
    get_client().flush()


if __name__ == "__main__":
    main()
