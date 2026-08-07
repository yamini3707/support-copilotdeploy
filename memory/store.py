"""
The long-term memory store — in-memory, per customer.

Shape (extensible — more buckets can be added later):

    memory = {
        <customer_id>: {
            "semantic": [ {text, source}, ... ],   # durable facts / preferences about the customer
            "history":  [ {ticket_id, date, category, summary, resolved, ...}, ... ]   # episodic: past tickets
        },
        ...
    }

It boots seeded from world_state.ticket_history (the episodic log), and derives any structured
preferences it finds in the notes into `semantic`. At runtime it grows: when a ticket ends we append
to `history`; when we learn a durable fact we append to `semantic`.

    from memory.store import MemoryStore
    store = MemoryStore().seed_from_world_state()
    block = store.recall("cust_enterprise_002")   # the context block to inject
"""

import json
import os
import re

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
LANG = {"es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
        "hi": "Hindi", "ja": "Japanese", "zh": "Chinese", "en": "English"}


class MemoryStore:
    def __init__(self):
        self._m = {}                                   # customer_id -> {"semantic": [...], "history": [...]}

    def _cust(self, cid):
        return self._m.setdefault(cid, {"semantic": [], "history": []})

    # ── boot: seed from the world's existing ticket history ─────────────────────
    def seed_from_world_state(self):
        ws = json.load(open(os.path.join(ROOT, "data", "world_state.json")))
        for cid, hist in ws.get("ticket_history", {}).items():
            self._cust(cid)["history"] = list(hist)
            for h in hist:                             # derive structured preferences from notes
                for k, v in re.findall(r"(\w+)\s*=\s*([\w-]+)", h.get("note") or ""):
                    if k == "language_pref":
                        self.add_semantic(cid, f"prefers replies in {LANG.get(v, v)} (language_pref={v})",
                                          source=h.get("ticket_id"))
        return self

    # ── writes (used now for seeding; the ticket-end write path comes next) ─────
    def add_semantic(self, cid, text, source=None):
        c = self._cust(cid)
        if not any(s["text"] == text for s in c["semantic"]):
            c["semantic"].append({"text": text, "source": source})

    def add_history(self, cid, entry):
        self._cust(cid)["history"].append(entry)

    # ── reads ───────────────────────────────────────────────────────────────────
    def get(self, cid):
        return self._m.get(cid, {"semantic": [], "history": []})

    def recall_relevant(self, cid, query, k=5):
        """Scale-realistic recall: once a customer has MANY memories you cannot dump them all, so you
        embed the query and return only the top-k most similar memory items. Returns (block, ranking)
        where ranking is the full [(score, kind, text)] list (sorted) for inspection."""
        import numpy as np
        from sessions.s9_rag_final.embeddings import embed
        c = self._m.get(cid) or {"semantic": [], "history": []}
        items = [("pref", s["text"]) for s in c["semantic"]] + \
                [("ticket", f"{h.get('date')} [{h.get('category')}] "
                            f"{'resolved' if h.get('resolved') else 'UNRESOLVED'}: {h.get('summary')}")
                 for h in c["history"]]
        if not items:
            return "", []
        qv = np.array(embed(query)); qv /= np.linalg.norm(qv)
        ranking = []
        for kind, text in items:
            v = np.array(embed(text)); v /= np.linalg.norm(v)
            ranking.append((float(qv @ v), kind, text))
        ranking.sort(reverse=True)
        block = "[MEMORY — most relevant to this query]\n" + "\n".join(f"  - {t}" for _, _, t in ranking[:k])
        return block, ranking

    def recall(self, cid):
        """Assemble the compact 'what we remember about this customer' block to inject into context.
        Returns '' when we have nothing on this customer (so new customers add no noise)."""
        c = self._m.get(cid)
        if not c or (not c["semantic"] and not c["history"]):
            return ""
        lines = ["[MEMORY — what we remember about this customer, from past interactions]"]
        if c["semantic"]:
            lines.append("Standing preferences / facts (honor these in your reply):")
            lines += [f"  - {s['text']}" for s in c["semantic"]]
        if c["history"]:
            lines.append("Past tickets (most recent first):")
            for h in sorted(c["history"], key=lambda x: x.get("date", ""), reverse=True):
                status = "resolved" if h.get("resolved") else "UNRESOLVED"
                lines.append(f"  - {h.get('date')} [{h.get('category')}] {status}: {h.get('summary')}")
        return "\n".join(lines)
