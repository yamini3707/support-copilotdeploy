"""
Test + demo the unified RAG.

  Part A — pipeline checks: run unified_search on labeled queries and assert the right docs / behavior
           (graph multi-hop, parent-child recall, metadata filter, abstention).
  Part B — agent end-to-end on a couple of tickets.
  Part C — flush + verify the traces landed in Langfuse (nested, with the parallel strategy spans).

    python3 sessions/s9_rag_final/run.py
"""

import os
import sys
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from sessions.s9_rag_final.agent import answer          # importing sets up Langfuse tracing
from sessions.s9_rag_final.pipeline import unified_search
from sessions.s9_rag_final import log as L
from langfuse import get_client

# (query, plan, expectation)
CHECKS = [
    {"q": "We had the EU SSO login outage, INC-2041. Has this same root cause hit us before, and how "
          "do we prevent it?", "plan": None,
     "expect_any": ["postmortem_inc2037", "cert_rotation_runbook", "arch_saml_cert"], "expect_graph": True},
    {"q": "Can we get last month's charge refunded?", "plan": "enterprise",
     "expect_any": ["refund_policy_full"]},
    {"q": "How long can I recover deleted data?", "plan": "free",
     "expect_any": ["policy_retention_free", "data_retention_policy"]},
    {"q": "Can I pay my subscription with Bitcoin?", "plan": None, "expect_abstain": True},
]


def part_a():
    L.section("PART A — pipeline checks")
    passed = 0
    for c in CHECKS:
        res = unified_search(c["q"], c["plan"])
        docs = [d["doc_id"] for d in res["docs"]]
        sources = {s for d in res["docs"] for s in d["sources"]}
        ok = True
        if c.get("expect_abstain"):
            ok = res["abstain"]
            verdict = f"abstain={res['abstain']}"
        else:
            hit = [d for d in c.get("expect_any", []) if d in docs]
            ok = bool(hit) and not res["abstain"]
            if c.get("expect_graph"):
                ok = ok and ("graph" in sources)
            verdict = f"docs={docs} sources={sorted(sources)} matched={hit}"
        passed += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {c['q'][:55]!r}\n         {verdict}\n")
    print(f"  Part A: {passed}/{len(CHECKS)} passed")
    return passed == len(CHECKS)


def part_b():
    L.section("PART B — agent end-to-end")
    tickets = [
        ("We had the EU SSO login outage, INC-2041. Has this same root cause hit us before, and how "
         "do we prevent it?", {"customer_id": "cust_enterprise_000", "plan": "enterprise"}),
        ("Can we get last month's charge refunded?", {"customer_id": "cust_enterprise_000", "plan": "enterprise"}),
    ]
    for t, ctx in tickets:
        out = answer(t, ctx)
        print(f"\n  Q: {t[:60]}\n  DOCS: {out['docs']}\n  A: {out['answer'][:160]}")


def part_c():
    L.section("PART C — verify traces in Langfuse")
    lf = get_client()
    lf.flush()
    time.sleep(6)
    traces = lf.api.trace.list(limit=3)
    for t in traces.data[:2]:
        full = lf.api.trace.get(t.id)
        names = [o.name for o in full.observations]
        parallel = [n for n in names if n in ("hybrid", "hyde", "graph")]
        print(f"  trace {t.name} obs={len(full.observations)}  strategy spans={parallel}")
    print(f"  open {os.getenv('LANGFUSE_HOST')} -> Tracing")


if __name__ == "__main__":
    a = part_a()
    part_b()
    part_c()
    print("\n" + ("✅ pipeline checks all passed" if a else "⚠ some pipeline checks failed — see Part A"))
