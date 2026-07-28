"""
Query-side entity linking (names only, no type-scoping).

For a user query:
  Step 1  LLM pulls the entity mentions as short NAMES (its type guess on a short query is unreliable).
  Then resolve each name to a graph entity:
    Step 0  exact match (normalized) — catches ids like INC-2041 deterministically.
    Step 1  embed the name, shortlist the top-k most similar graph entities (ALL types) — cheap recall.
    Step 2  LLM decides which candidate it is, or none — precise dedup.

Runs with narrated step-by-step logging. Prereq: run build_graph.py first.
    python3 sessions/s8_graphrag/link_query.py
"""

import json
import os
import re
import sys

import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass
from sessions.s8_graphrag.embeddings import embed
from eval.retry import call_with_retry
from sessions.s8_graphrag.build_graph import SHORTLIST, TOP_K, _emb, _link   # reuse the graph's resolution pieces
from sessions.s8_graphrag import log as L

GRAPH = json.load(open(os.path.join(os.path.dirname(__file__), "graph.json")))
ALL = list(dict.fromkeys(n for names in GRAPH["entities"].values() for n in names))   # all entity names, flat
ALL_EMB = np.array([_emb(n) for n in ALL])                       # pre-embed every graph entity
EXACT = {re.sub(r"[^a-z0-9]", "", n.lower()): n for n in ALL}    # normalized -> canonical (for Step 0)

EXAMPLES = [
    "We had the EU SSO login outage, INC-2041. Has this same cause hit us before?",
    "What breaks if we rotate the signing cert?",
    "Are the audit log exports affected by anything?",
    "Why is my invoice so high?",
]


def _query_names(query):
    """Step 1: ask the LLM for the entity mentions in the query, as short names (no types)."""
    L.step("extract entity mentions from the query with the LLM", level=2,
           why="we only ask for NAMES, not types — on a short question the LLM's type guess is unreliable, "
               "and a wrong type would scope the search to the wrong entities.")
    prompt = ("List the specific entities/things this support query refers to, as short names "
              "(components, services, incidents, features). Be generous but only real mentions.\n\n"
              f'QUERY: {query}\n\nReturn JSON: {{"names":[".."]}}')
    from openai import OpenAI
    resp = call_with_retry(OpenAI().chat.completions.create,
        model=os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o"), temperature=0,
        response_format={"type": "json_object"}, messages=[{"role": "user", "content": prompt}])
    names = json.loads(resp.choices[0].message.content).get("names", [])
    L.detail(f"mentions: {names}")
    return names


def resolve(name):
    """Resolve one extracted name to a graph entity, or None — exact -> shortlist -> LLM."""
    k = re.sub(r"[^a-z0-9]", "", name.lower())
    if k in EXACT:                                # Step 0 — exact
        L.detail(f"'{name}' -> exact match '{EXACT[k]}'",
                 why="an exact (normalized) hit is unambiguous — e.g. an id like INC-2041 — so no fuzzy search.")
        return EXACT[k]
    sims = ALL_EMB @ _emb(name)                   # Step 1 — embed + shortlist across ALL entities
    cands, seen = [], set()
    for j in np.argsort(-sims):
        if sims[j] < SHORTLIST or len(cands) >= TOP_K:
            break
        if ALL[j] not in seen:
            seen.add(ALL[j]); cands.append((ALL[j], float(sims[j])))
    if not cands:
        L.detail(f"'{name}' -> no candidate >= {SHORTLIST} -> not in graph",
                 why="nothing in the graph is close enough to be this thing, so the query mentions "
                     "something the graph doesn't cover.")
        return None
    L.detail(f"'{name}' -> shortlist: " + ", ".join(f"'{c}'({s:.2f})" for c, s in cands),
             why="embedding cheaply narrows every graph entity down to a few candidates; the LLM then decides.")
    hit = _link("entity", name, [(c, c) for c, _ in cands])   # Step 2 — LLM decides (id == name here)
    L.detail(f"   LLM decision: {'-> '+hit if hit else 'none match (not in graph)'}")
    return hit


def link(query):
    """Link a whole query -> list of graph seed entities."""
    L.step(f"LINK QUERY: {query}")
    seeds = []
    for name in _query_names(query):
        hit = resolve(name)
        if hit:
            seeds.append(hit)
    seeds = list(dict.fromkeys(seeds))
    L.step(f"seeds: {seeds}", level=2)
    return seeds


def main():
    L.section("QUERY ENTITY LINKING")
    for q in EXAMPLES:
        link(q)


if __name__ == "__main__":
    main()
