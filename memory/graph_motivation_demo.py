"""
MEMORY · Step 4 — why flat memory needs a GRAPH (the multi-hop failure).

Our recall so far dumps the customer's whole memory. That only works because our demo customers have
1-2 facts. Give a customer a RICH memory (many facts + tickets) and you must RETRIEVE the relevant
few — you can't inject them all. Embedding retrieval then FAILS on INDIRECT links: the fact that
answers the query shares almost no words with it, so it never makes the top-k — while distractors
that DO share words crowd the top.

Two self-evident cases (bridge fact marked ★):
  A) BILLING routed to a PARENT company:
     query "we've had no invoices all year"  needs  "Acme is a subsidiary of Globex; Globex handles
     Acme's account" — but the query says 'invoice' and the fact says 'subsidiary/parent'.
  B) A DATA-RESIDENCY constraint on a new request:
     query "can we enable your new US-hosted analytics add-on?"  needs  "all of Acme's data must stay
     in the EU" — 'US analytics add-on' and 'EU data residency' share no words at all.

    python3 memory/graph_motivation_demo.py
"""

import io
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from sessions.s10_full_agent.agent import classify
from memory.store import MemoryStore
from langfuse import get_client

CID = "cust_enterprise_003"                              # Acme Robotics
CTX = {"customer_id": CID, "plan": "enterprise", "region": "US"}

# ── a rich, realistic memory: 2 bridge facts (★) + many distractors that share query words ──────
SEMANTIC = [
    "★ Acme is a subsidiary of Globex Corporation, and Globex's central finance team handles all of Acme's account matters.",  # bridge A
    "★ Acme operates under a strict data-residency policy: all of Acme's data must remain within the EU.",                      # bridge B
    "Acme is billed annually in US dollars.",                         # 'invoice/billing/US' distractor
    "Acme's billing contact is finance@acme.example.",                # 'billing' distractor
    "Acme's renewal date is April 1.",                                # 'billing' distractor
    "Acme relies heavily on the analytics dashboard.",                # 'analytics' distractor
    "Acme previously asked for a US-based support contact.",          # 'US' distractor
    "Acme has 40 seats purchased and typically uses about 32.",
    "Acme authenticates users through Okta as their identity provider.",
    "Acme prefers to be contacted by email rather than live chat.",
    "Acme's primary admin is Priya Nair.",
    "Acme defaults to the Kanban board view.",
    "Acme requested SSO enforcement for all members.",
    "Acme onboarded in 2024 and renews annually.",
]
HISTORY = [
    {"date": "2026-02-23", "category": "technical", "resolved": False,
     "summary": "Audit-log export returned partial data. Left unresolved, promised follow-up."},
    {"date": "2026-02-10", "category": "billing", "resolved": True, "summary": "Question about the annual invoice."},
    {"date": "2026-01-30", "category": "account", "resolved": True, "summary": "Enabled SSO enforcement."},
    {"date": "2026-01-12", "category": "account", "resolved": True, "summary": "Increased seats from 30 to 40."},
    {"date": "2025-12-05", "category": "feature_request", "resolved": True, "summary": "Asked for a new analytics add-on."},
]

# (tag, query, bridge-fact needle(s), EXPECTED answer if the bridge fact had been recalled)
CASES = [
    ("A", "We haven't received a single invoice all year — is something wrong with our account?",
     ["subsidiary of Globex"],
     "Nothing is wrong: Acme is a subsidiary of Globex Corporation, and Globex's finance team "
     "handles Acme's account centrally — so CloudDesk invoices go to Globex, not to Acme directly."),
    ("B", "We'd like to turn on your new US-hosted analytics add-on. Can we just enable it?",
     ["data must remain within the EU"],
     "We should NOT simply enable it: Acme is under a strict EU data-residency policy (all data must "
     "stay in the EU), and a US-hosted add-on would process data in the US — violating that policy. "
     "It needs review against the residency requirement first."),
]


def seed():
    s = MemoryStore()
    for f in SEMANTIC:
        s.add_semantic(CID, f)
    for h in HISTORY:
        s.add_history(CID, h)
    return s


def main():
    store = seed()
    n = len(store.get(CID)["semantic"]) + len(store.get(CID)["history"])
    print("\n" + "#" * 100)
    print(f"  MEMORY · STEP 4 — multi-hop failure ({CID} has {n} memories; we must retrieve, not dump)")
    print("#" * 100)

    for tag, query, needles, expected in CASES:
        with redirect_stdout(io.StringIO()):
            block, ranking = store.recall_relevant(CID, query, k=5)
            out = classify(f"{query}\n\n{block}", CTX)
        print("\n" + "=" * 100)
        print(f"  CASE {tag}   QUERY: {query}")
        print(f"  embedding ranking (score · item) — only the top-5 [IN] get injected into context:")
        for i, (score, kind, text) in enumerate(ranking):
            mark = "[IN] " if i < 5 else "     "
            star = "  ← ★ BRIDGE FACT (the actual answer)" if any(nb in text for nb in needles) else ""
            print(f"    {mark}{score:.2f}  {text[:80]}{star}")
        bridge_ranks = [i + 1 for i, (_, _, t) in enumerate(ranking) if any(nb in t for nb in needles)]
        missed = not all(r <= 5 for r in bridge_ranks)
        print(f"\n  bridge fact rank: {bridge_ranks}  ->  {'MISSED — not in the top-5 injected' if missed else 'in top-5'}")
        print(f"\n  ✗ ACTUAL answer   (bridge fact NOT retrieved): {out['answer']}")
        print(f"  ✓ EXPECTED answer (if the bridge fact WERE recalled): {expected}")

    print("\n" + "#" * 100)
    print("  Both bridge facts EXIST in memory, but embedding retrieval can't reach them — the link is")
    print("  INDIRECT and shares no words with the query (invoice→parent company; US feature→EU data rule),")
    print("  while word-sharing distractors crowd the top-5. This is what GRAPH memory solves: traverse")
    print("  entity relationships (Acme→Globex; request→data-location→EU-rule) instead of matching text.")
    print("#" * 100 + "\n")
    get_client().flush()


if __name__ == "__main__":
    main()
