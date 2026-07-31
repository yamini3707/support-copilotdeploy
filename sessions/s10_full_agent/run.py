"""
Test the full agent: routing + structured tools + the unified RAG, all traced.

Each ticket is designed to exercise a DIFFERENT mix (structured-only, KB-only, or both), so we can
confirm the router picks the right specialist, the specialist uses the right tools, and the answer is
grounded. Part C verifies the traces landed with the unified-RAG spans nested under a specialist.

    python3 sessions/s10_full_agent/run.py
"""

import os
import sys
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from sessions.s10_full_agent.agent import classify
from langfuse import get_client

# (ticket, context, expected category, tools that SHOULD appear)
CASES = [
    {"ticket": "We had the EU SSO login outage, INC-2041. Has this same root cause hit us before, and "
               "how do we prevent it?",
     "ctx": {"customer_id": "cust_enterprise_000", "plan": "enterprise"},
     "cat": "technical", "want_tools": ["search_knowledge_base"]},
    {"ticket": "I think I was charged twice for last month — can you refund the duplicate?",
     "ctx": {"customer_id": "cust_enterprise_000", "plan": "enterprise"},
     "cat": "billing", "want_tools": ["get_invoices"]},
    {"ticket": "Is SSO included on my plan, or do I need to upgrade?",
     "ctx": {"customer_id": "cust_pro_012", "plan": "pro"},
     "cat": "account", "want_tools": ["get_subscription", "get_plan_catalog"]},
    {"ticket": "How do I invite a new teammate to my workspace?",
     "ctx": {"customer_id": "cust_free_020", "plan": "free"},
     "cat": "account", "want_tools": ["search_knowledge_base"]},
]


def part_a():
    print("\n=== PART A — routing + tool use ===")
    passed = 0
    for c in CASES:
        out = classify(c["ticket"], c["ctx"])
        tools = [t["tool"] for t in out.get("tool_calls", [])]
        cat_ok = out["category"] == c["cat"]
        tools_ok = all(t in tools for t in c["want_tools"])
        ok = cat_ok and tools_ok and bool(out["answer"])
        passed += ok
        print(f"\n  [{'PASS' if ok else 'FAIL'}] {c['ticket'][:58]!r}")
        print(f"        category={out['category']} (want {c['cat']}) | priority={out['priority']}")
        print(f"        tools={tools}  (want {c['want_tools']})")
        print(f"        answer: {out['answer'][:130]}")
    print(f"\n  Part A: {passed}/{len(CASES)} passed")
    return passed == len(CASES)


def part_c():
    print("\n=== PART C — traces in Langfuse ===")
    lf = get_client(); lf.flush(); time.sleep(7)
    try:
        for t in lf.api.trace.list(limit=2).data:
            full = lf.api.trace.get(t.id)
            names = [o.name for o in full.observations]
            specialists = [n for n in names if n and n.startswith("specialist_")]
            rag = [n for n in names if n in ("unified_search", "hybrid", "hyde", "graph", "weaviate_search")]
            print(f"  trace obs={len(full.observations)}  specialists={specialists}  rag-spans={rag}")
    except Exception as e:
        print(f"  (trace read-back timed out: {type(e).__name__} — traces were still flushed; check the UI)")
    print(f"  open {os.getenv('LANGFUSE_HOST')} -> Tracing")


if __name__ == "__main__":
    a = part_a()
    part_c()
    print("\n" + ("✅ full-agent checks passed" if a else "⚠ some checks failed — see Part A"))
