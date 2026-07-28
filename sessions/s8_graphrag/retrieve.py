"""
GraphRAG retrieval — query -> seeds -> traverse -> connected docs, checked against gold.

  1. link the query to graph entities (link_query.link)         -> seeds
  2. BFS the graph from the seeds up to N hops                   -> reached nodes
  3. collect the doc_ids on the traversed edges (provenance)     -> retrieved docs
  4. compare to the gold docs                                    -> recall

Runs with narrated step-by-step logging. Prereq: run build_graph.py first.
    python3 sessions/s8_graphrag/retrieve.py
"""

import json
import os
import sys
from collections import deque

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from sessions.s8_graphrag.link_query import link
from sessions.s8_graphrag import log as L

EDGES = json.load(open(os.path.join(os.path.dirname(__file__), "graph.json")))["edges"]
HOPS = 2                         # hops to walk out from the seeds (the precision<->recall knob)

TESTS = [
    ("We had the EU SSO login outage, INC-2041. Has this same cause hit us before, and how do we prevent it?",
     ["postmortem_inc2041", "postmortem_inc2037", "cert_rotation_runbook", "arch_saml_cert"]),
    ("Are the audit log exports affected by anything, and by what?",
     ["postmortem_inc2037", "arch_saml_cert"]),
]


def traverse(seeds, hops=HOPS):
    """BFS out from `seeds` up to `hops`; return (retrieved doc_ids, reached node names)."""
    adj = {}                                       # node -> edges touching it (treated as undirected)
    for e in EDGES:
        adj.setdefault(e["subject"], []).append(e)
        adj.setdefault(e["object"], []).append(e)
    L.step(f"traverse {hops} hops from seeds {seeds}", level=2,
           why="the answer's supporting docs are reachable through shared entities (e.g. two incidents "
               "meeting at the same root-cause node); walking edges pulls them in even when their text "
               "doesn't match the query.")
    reached, used, frontier = set(seeds), [], deque((s, 0) for s in seeds)
    while frontier:
        n, d = frontier.popleft()
        if d >= hops:
            continue
        for e in adj.get(n, []):
            used.append(e)                         # remember the edge — its docs are our provenance
            nxt = e["object"] if e["subject"] == n else e["subject"]
            if nxt not in reached:
                reached.add(nxt); frontier.append((nxt, d + 1))
                L.detail(f"hop {d+1}: '{n}' --{e['relation']}--> '{nxt}'   (doc(s) {e['doc_ids']})")
    docs = sorted({d for e in used for d in e["doc_ids"]})
    L.detail(f"docs on traversed edges: {docs}",
             why="we retrieve by EDGE provenance — each doc is pulled because a relationship we actually "
                 "walked came from it (keeps out docs that merely mention a node in passing).")
    return docs, reached


def main():
    L.section("GRAPHRAG RETRIEVAL (with gold check)")
    for query, gold in TESTS:
        L.step(f"QUERY: {query}")
        seeds = link(query)                        # 1) query -> seeds
        docs, reached = traverse(seeds)            # 2+3) traverse -> docs
        hit = [g for g in gold if g in docs]       # 4) gold ∩ retrieved
        missing = [g for g in gold if g not in docs]
        extra = [d for d in docs if d not in gold]
        L.step(f"reached nodes : {sorted(reached)}", level=2)
        L.step(f"retrieved docs: {docs}", level=2)
        L.step(f"gold docs     : {gold}", level=2)
        L.step(f"RECALL: {len(hit)}/{len(gold)} = {len(hit)/len(gold):.2f}"
               f"   {'✅ all gold retrieved' if not missing else '❌ missing '+str(missing)}", level=2)
        if extra:
            L.detail(f"extra (non-gold) retrieved: {extra}",
                     why="at this hop depth traversal pulls the whole connected cluster — fewer hops = "
                         "tighter/more precise, more hops = broader recall.")


if __name__ == "__main__":
    main()
