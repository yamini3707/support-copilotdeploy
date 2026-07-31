"""
Graph-side retrieval for the unified pipeline: query -> seed entities -> traverse -> doc_ids.

Reuses the resolution primitives from graph_build (embedding shortlist + LLM decide). Loads the
persisted graph.json (built once by graph_build.py).
"""

import json
import os
import re
import sys
from collections import deque

import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from eval.retry import call_with_retry
from sessions.s9_rag_final.graph_build import SHORTLIST, TOP_K, _emb, _link
from sessions.s9_rag_final import log as L

HERE = os.path.dirname(__file__)
_GRAPH = json.load(open(os.path.join(HERE, "graph.json")))
_EDGES = _GRAPH["edges"]
_ALL = list(dict.fromkeys(n for names in _GRAPH["entities"].values() for n in names))   # all entity names
_ALL_EMB = np.array([_emb(n) for n in _ALL]) if _ALL else np.zeros((0, 1))
_EXACT = {re.sub(r"[^a-z0-9]", "", n.lower()): n for n in _ALL}
HOPS = 2


def _query_names(query):
    """Ask the LLM which entities the query mentions (names only — types are unreliable on a short query)."""
    from openai import OpenAI
    system = ("List the specific entities/things the support query refers to, as short names "
              "(components, services, incidents, features). Be generous but only real mentions. "
              'Return JSON {"names":[".."]}.')
    resp = call_with_retry(OpenAI().chat.completions.create,
        model=os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o"), temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": query}])
    return json.loads(resp.choices[0].message.content).get("names", [])


def _resolve(name):
    """Match one query mention to a graph entity: exact -> embed shortlist -> LLM decide."""
    k = re.sub(r"[^a-z0-9]", "", name.lower())
    if k in _EXACT:
        L.detail(f"resolve {name!r} -> exact match {_EXACT[k]!r}")
        return _EXACT[k]
    if not len(_ALL):
        return None
    sims = _ALL_EMB @ _emb(name)
    cands, seen = [], set()
    for j in np.argsort(-sims):
        if sims[j] < SHORTLIST or len(cands) >= TOP_K:
            break
        if _ALL[j] not in seen:
            seen.add(_ALL[j]); cands.append((_ALL[j], _ALL[j]))
    if not cands:
        L.detail(f"resolve {name!r} -> no entity above the shortlist threshold; skipping")
        return None
    hit = _link("entity", name, cands)
    L.detail(f"resolve {name!r} -> embedding shortlist {[c[0] for c in cands]}, LLM chose {hit!r}",
             why="a fuzzy mention may paraphrase a known entity; the embedding narrows to candidates "
                 "and the LLM makes the precise alias-vs-new call.")
    return hit


def link(query):
    """Query -> list of graph seed entities."""
    names = _query_names(query)
    L.detail(f"query mentions (per LLM): {names}")
    seeds = [hit for name in names if (hit := _resolve(name))]
    seeds = list(dict.fromkeys(seeds))
    L.detail(f"graph seed entities: {seeds}")
    return seeds


def traverse(seeds, hops=HOPS):
    """BFS from seeds; return the doc_ids on the traversed edges (provenance)."""
    adj = {}
    for e in _EDGES:
        adj.setdefault(e["subject"], []).append(e)
        adj.setdefault(e["object"], []).append(e)
    reached, used, frontier = set(seeds), [], deque((s, 0) for s in seeds)
    while frontier:
        n, d = frontier.popleft()
        if d >= hops:
            continue
        for e in adj.get(n, []):
            used.append(e)
            nxt = e["object"] if e["subject"] == n else e["subject"]
            if nxt not in reached:
                reached.add(nxt); frontier.append((nxt, d + 1))
    docs = sorted({doc for e in used for doc in e["doc_ids"]})
    L.detail(f"traversed {hops} hop(s) from {list(seeds)} -> reached {len(reached)} entities, "
             f"{len(docs)} provenance doc(s): {docs}",
             why="every edge carries the doc_ids that stated it, so walking the graph hands back the "
                 "documents that connect the query's entities — even ones no keyword match would find.")
    return docs
