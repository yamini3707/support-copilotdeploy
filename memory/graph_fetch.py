"""
MEMORY · Step 5b — FETCH from the memory graph (recover what embedding missed).

The Class-2 recipe, on our support memory graph:
  1. extract the query's ENTITIES + RELATED entities (LLM world knowledge — the secret sauce:
     "US-hosted feature" ~ data residency / compliance; "invoice" ~ billing / account owner)
  2. fuzzy-match them to graph NODES, skipping the customer hub (a STOP node)
  3. BFS-traverse (2 hops) from the matched nodes, skipping stop nodes
  4. reverse-index reached nodes -> the memory facts they came from
Head-to-head with embedding retrieval on the two Step-4 cases.

    python3 memory/graph_fetch.py
"""

import io
import json
import os
import re
import sys
from collections import defaultdict, deque
from contextlib import redirect_stdout

import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from eval.retry import call_with_retry
from sessions.s9_rag_final.embeddings import embed
from memory.graph_build import build, _memory_items

STOP = {"acme", "acme robotics"}                         # the customer hub — do not seed/traverse through it

CASES = [
    ("A", "We haven't received a single invoice all year — is something wrong with our account?", "F00",
     "Acme is a subsidiary of Globex Corporation (billing handled by the parent)"),
    ("B", "We'd like to turn on your new US-hosted analytics add-on. Can we just enable it?", "F01",
     "Acme's data must remain in the EU (data-residency policy)"),
]


def _query_entities(query, context=""):
    """Extract the entities a query refers to. If `context` (facts already retrieved about the
    customer) is given, the LLM can also name SPECIFIC entities that appear in those facts — e.g.
    the parent company's actual name — which the raw query alone never reveals."""
    system = ("A customer asked a support question. Using the QUESTION and any KNOWN FACTS about the "
              "customer, list the entities the question refers to PLUS related entities a knowledgeable "
              "agent would associate with it. Prefer SPECIFIC named entities (organizations, people, "
              "policies, integrations, locations) — including any named in the known facts that are "
              "relevant to the question (e.g. a parent company's actual name). "
              'Return JSON {"entities":[".."], "related":[".."]}.')
    user = f"QUESTION: {query}"
    if context:
        user += f"\n\nKNOWN FACTS ABOUT THE CUSTOMER:\n{context}"
    from openai import OpenAI
    r = call_with_retry(OpenAI().chat.completions.create,
        model=os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o"), temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    d = json.loads(r.choices[0].message.content)
    return d.get("entities", []) + d.get("related", [])


def _fuzzy(term, name):
    t, n = term.lower(), name.lower()
    if t in n or n in t:
        return True
    tw = {w for w in re.findall(r"\w+", t) if len(w) >= 3}
    nw = {w for w in re.findall(r"\w+", n) if len(w) >= 3}
    return bool(tw & nw)


def embedding_rank(query, items):
    qv = np.array(embed(query)); qv /= np.linalg.norm(qv)
    out = []
    for fid, text in items:
        v = np.array(embed(text)); v /= np.linalg.norm(v)
        out.append((float(qv @ v), fid, text))
    out.sort(reverse=True)
    return out


def graph_fetch(query, ents, edges, e2f, context="", stop_names=None):
    # the customer hub is a STOP node (everything connects to it, so traversing through it is useless).
    # Defaults to the demo's Acme hub; in production pass the authenticated customer's own name(s).
    stop = {s.lower() for s in (stop_names if stop_names is not None else STOP)}
    stop_ids = {nid for nid, name in ents.display.items() if name.lower() in stop}
    adj = defaultdict(list)
    for (s, r, o) in edges:
        adj[s].append(o); adj[o].append(s)

    # Union of TWO extractions so we catch both kinds of multi-hop:
    #   raw query   -> WORLD-KNOWLEDGE related entities (reach facts beyond the retrieval net)
    #   + context   -> SPECIFIC named entities present in near-miss retrieved facts (e.g. the parent's name)
    terms = list(dict.fromkeys(_query_entities(query) + (_query_entities(query, context) if context else [])))
    matched = {nid for term in terms for nid, name in ents.display.items()
               if nid not in stop_ids and _fuzzy(term, name)}
    reached, frontier = set(matched), deque((m, 0) for m in matched)   # BFS 2 hops, skip stop nodes
    while frontier:
        n, d = frontier.popleft()
        if d >= 2:
            continue
        for nb in adj[n]:
            if nb not in reached and nb not in stop_ids:
                reached.add(nb); frontier.append((nb, d + 1))
    fact_ids = sorted({f for n in reached for f in e2f[n]})
    return terms, [ents.display[m] for m in matched], fact_ids


def main():
    print("\n" + "#" * 100)
    print("  MEMORY · GRAPH FETCH — build the graph, then recover the buried facts embedding missed")
    print("#" * 100)
    print("\n  building the memory graph ...")
    with redirect_stdout(io.StringIO()):
        ents, edges, e2f = build()
    items = _memory_items()
    text_of = dict(items)

    for tag, query, bridge_fid, bridge_desc in CASES:
        emb = embedding_rank(query, items)
        emb_top5 = [fid for _, fid, _ in emb[:5]]
        emb_rank = next(i + 1 for i, (_, fid, _) in enumerate(emb) if fid == bridge_fid)
        with redirect_stdout(io.StringIO()):
            terms, matched_nodes, g_facts = graph_fetch(query, ents, edges, e2f)

        print("\n" + "=" * 100)
        print(f"  CASE {tag}   QUERY: {query}")
        print(f"  bridge fact needed: {bridge_fid} — {bridge_desc}")
        print(f"\n  EMBEDDING: top-5 = {emb_top5}   |  bridge {bridge_fid} at rank {emb_rank}  "
              f"-> {'FOUND' if bridge_fid in emb_top5 else 'MISSED'}")
        print(f"  GRAPH    : query entities+related = {terms}")
        print(f"             matched graph nodes     = {matched_nodes}")
        print(f"             recovered facts         = {g_facts}   "
              f"-> bridge {bridge_fid} {'FOUND ✅' if bridge_fid in g_facts else 'still missed ❌'}")

    print("\n" + "#" * 100)
    print("  Read-out: embedding misses both bridges (word mismatch). GRAPH recovers the one whose bridge")
    print("  is an INFERABLE shared entity (data-residency); the parent-company link sits behind the")
    print("  customer hub, so graph can't reach it either — that fact belongs in always-injected CORE")
    print("  memory, not retrieval. (When graph memory helps, and when it doesn't.)")
    print("#" * 100 + "\n")


if __name__ == "__main__":
    main()
