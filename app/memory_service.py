"""
Memory service — long-term memory for the deployed copilot.

Wraps the memory/ modules into one boot-once service:
  - a single in-memory MemoryStore, seeded on boot from world_state (episodic ticket history) plus a
    rich Acme demo fixture so the multi-hop graph win is reproducible live on cust_enterprise_003.
  - recall(): FULL unified recall — embedding retrieval (direct facts) + graph traversal (indirect,
    multi-hop facts embedding misses), merged and tagged, returned as a MEMORY block to inject.
  - form(): the write path — distills a finished ticket into durable facts + an episodic record.

Because graph construction runs one LLM extraction per fact, each customer's graph is built LAZILY
and CACHED; the cache is invalidated only when that customer's memory changes (after form()). So the
first ticket for a customer warms the graph and the rest are fast. Memory is in-memory (ephemeral):
it resets on restart — fine for a demo; swap MemoryStore for a persistent backend for real use.
"""

import json
import os
import sys
from contextlib import redirect_stdout
import io

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from memory.store import MemoryStore
from memory.formation import form_memory
from memory.graph_build import build_from_items, SEMANTIC as ACME_FACTS
from memory.graph_fetch import graph_fetch, embedding_rank

# customer_id -> display name(s), for the graph STOP node (the customer hub) and stop-list
_NAMES = {c["customer_id"]: c["name"]
          for c in json.load(open(os.path.join(ROOT, "data", "world_state.json"))).get("customers", [])}

# the rich Acme fixture's episodic side (its semantic side is graph_build.SEMANTIC == ACME_FACTS)
_ACME_HISTORY = [
    {"date": "2026-02-23", "category": "technical", "resolved": False,
     "summary": "Audit-log export returned partial data; promised follow-up."},
    {"date": "2026-02-10", "category": "billing", "resolved": True, "summary": "Question about the annual invoice."},
    {"date": "2026-01-30", "category": "account", "resolved": True, "summary": "Enabled SSO enforcement."},
    {"date": "2026-01-12", "category": "account", "resolved": True, "summary": "Increased seats from 30 to 40."},
    {"date": "2025-12-05", "category": "feature_request", "resolved": True, "summary": "Asked for a new analytics add-on."},
]
DEMO_CUSTOMER = "cust_enterprise_003"      # Acme Robotics — carries the multi-hop graph showcase


class MemoryService:
    def __init__(self):
        self.store = MemoryStore()
        self._graphs = {}                  # cid -> (ents, edges, entity_to_facts)   [lazy cache]

    def boot(self):
        """Seed memory once at startup: world_state history for everyone, plus the Acme demo fixture."""
        self.store.seed_from_world_state()
        for fact in ACME_FACTS:                        # rich semantic memory for the showcase customer
            self.store.add_semantic(DEMO_CUSTOMER, fact)
        for h in _ACME_HISTORY:
            self.store.add_history(DEMO_CUSTOMER, h)
        return self

    # ── memory items for THIS customer, as (fact_id, text) — the graph/embedding input ──────────
    def _items(self, cid):
        c = self.store.get(cid)
        texts = [s["text"] for s in c["semantic"]]
        for h in c["history"]:
            status = "resolved" if h.get("resolved") else "UNRESOLVED"
            texts.append(f"Ticket {h.get('date')} ({h.get('category')}, {status}): {h.get('summary')}")
        return [("F%02d" % i, t) for i, t in enumerate(texts)]

    def _graph(self, cid, items):
        if cid not in self._graphs:
            with redirect_stdout(io.StringIO()):       # build_from_items prints each fact; keep logs clean
                self._graphs[cid] = build_from_items(items, verbose=False)
        return self._graphs[cid]

    def _stop_names(self, cid):
        name = _NAMES.get(cid, "")
        return [n for n in {name, name.split()[0] if name else ""} if n]

    # ── READ path: unified recall (embedding + graph) → a MEMORY block to inject ────────────────
    def recall(self, cid, query, k=5, k_context=10):
        items = self._items(cid)
        if not items:
            return {"block": "", "facts": [], "graph_terms": [], "graph_nodes": []}
        text_of = dict(items)
        ranked = embedding_rank(query, items)
        emb_ids = [fid for _, fid, _ in ranked[:k]]
        context = "\n".join(f"- {t}" for _, _, t in ranked[:k_context])   # wide net to surface entities
        ents, edges, e2f = self._graph(cid, items)
        with redirect_stdout(io.StringIO()):
            terms, matched, graph_ids = graph_fetch(query, ents, edges, e2f,
                                                    context=context, stop_names=self._stop_names(cid))
        source = {fid: "EMBED" for fid in emb_ids}
        for fid in graph_ids:
            source[fid] = "BOTH" if fid in source else "GRAPH"
        facts = [(fid, source[fid], text_of[fid]) for fid in source]
        return {"block": self._block(facts), "facts": facts,
                "graph_terms": terms, "graph_nodes": matched}

    @staticmethod
    def _block(facts):
        if not facts:
            return ""
        lines = ["[MEMORY — retrieved facts about this customer, from past interactions. Honor any "
                 "standing preferences, and before agreeing to a request CHECK these for any constraint, "
                 "ownership, or conflict that explains or changes the right answer.]"]
        lines += [f"  - {text}" for _, _, text in facts]
        return "\n".join(lines)

    # ── WRITE path: distill a finished ticket into memory, then invalidate the graph cache ──────
    def form(self, cid, ticket, outcome):
        written = form_memory(self.store, cid, ticket, outcome)
        self._graphs.pop(cid, None)                    # memory changed → rebuild graph on next recall
        return written
