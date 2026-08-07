"""
MEMORY · Step 1 — SHOW THE GAP.

The project ships 6 memory-GATED eval cases (t_065..t_070): a customer refers to something only a
LONG-TERM, cross-session memory would know — their usual language, a prior unresolved ticket, an
earlier refund request. None of it is in the current ticket or in any structured tool
(get_customer deliberately does NOT expose locale). It lives only in world_state.ticket_history.

Our current agent (s10) has NO memory layer, so it cannot recall any of it. This script runs all six
through the agent and scores the MEMORY dimension (via the LLM judge on memory_must_convey). Expect
~0 across the board — the failure that the memory session will fix.

    python3 memory/show_memory_gap.py
"""

import io
import json
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from sessions.s10_full_agent.agent import classify
from eval.judge import judge_answer
from langfuse import get_client

CASE_IDS = ["t_065_mem_language", "t_066_mem_language",
            "t_067_mem_prior_ticket", "t_068_mem_prior_ticket",
            "t_069_mem_followup", "t_070_mem_followup"]
WHAT = {"t_065_mem_language": "SEMANTIC memory — the customer's language preference (Spanish)",
        "t_066_mem_language": "SEMANTIC memory — the customer's language preference (Spanish)",
        "t_067_mem_prior_ticket": "EPISODIC memory — a prior UNRESOLVED ticket (audit-log export)",
        "t_068_mem_prior_ticket": "EPISODIC memory — a prior UNRESOLVED ticket (audit-log export)",
        "t_069_mem_followup": "EPISODIC memory — a prior ticket that was a refund request",
        "t_070_mem_followup": "EPISODIC memory — a prior ticket that was a refund request"}


def main():
    cases = {c["id"]: c for c in json.load(open(os.path.join(ROOT, "data", "train.json")))}
    scores = []
    print("\n" + "#" * 96)
    print("  MEMORY · STEP 1 — the current agent has no memory. Watch all six cases fail.")
    print("#" * 96)

    for tid in CASE_IDS:
        c = cases[tid]
        must = c["expected"].get("memory_must_convey", [])
        with redirect_stdout(io.StringIO()):
            out = classify(c["ticket"], c["customer_context"])
            mem = judge_answer(c["ticket"], out.get("answer", ""), [], [], must)["memory"]
        scores.append(mem)
        print("\n" + "=" * 96)
        print(f"  {tid}   [{WHAT[tid]}]")
        print(f"  customer     : {c['customer_context']['customer_id']}")
        print(f"  USER SAYS    : {c['ticket']}")
        print(f"  SHOULD RECALL: {must[0]}")
        print(f"  AGENT ANSWER : {out.get('answer', '')}")
        print(f"  >> MEMORY score: {mem:.2f}   {'✅ recalled' if mem >= 0.99 else '❌ FAILED — no memory'}")

    avg = sum(scores) / len(scores)
    print("\n" + "#" * 96)
    print(f"  MEMORY dimension across the 6 gated cases: {avg:.2f}   "
          f"({sum(s >= 0.99 for s in scores)}/{len(scores)} recalled)")
    print("  -> pinned near 0: the agent literally cannot see the customer's history. Next: add memory.")
    print("#" * 96 + "\n")
    get_client().flush()


if __name__ == "__main__":
    main()
