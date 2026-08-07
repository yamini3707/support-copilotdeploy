"""
MEMORY · Step 2 — LOAD memory into context, then re-run the six gated cases.

For each ticket we look up the customer's memory (semantic + history), inject it as a context block,
and let the SAME s10 agent answer. Compare the MEMORY score against Step 1 (which was 0.00 across the
board). This is the read path: recall -> inject -> better answer.

    python3 memory/run_with_memory.py
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
from memory.store import MemoryStore
from langfuse import get_client

STORE = MemoryStore().seed_from_world_state()

CASE_IDS = ["t_065_mem_language", "t_066_mem_language",
            "t_067_mem_prior_ticket", "t_068_mem_prior_ticket",
            "t_069_mem_followup", "t_070_mem_followup"]


def answer_with_memory(ticket, ctx):
    """Read this customer's memory and inject it as a context block, then run the agent."""
    block = STORE.recall(ctx.get("customer_id"))
    augmented = f"{ticket}\n\n{block}" if block else ticket    # load memory into the agent's context
    return classify(augmented, ctx)


def main():
    cases = {c["id"]: c for c in json.load(open(os.path.join(ROOT, "data", "train.json")))}
    scores = []
    print("\n" + "#" * 96)
    print("  MEMORY · STEP 2 — recall + inject, then re-run the six cases (Step 1 was 0.00)")
    print("#" * 96)

    for tid in CASE_IDS:
        c = cases[tid]
        must = c["expected"].get("memory_must_convey", [])
        with redirect_stdout(io.StringIO()):
            out = answer_with_memory(c["ticket"], c["customer_context"])
            mem = judge_answer(c["ticket"], out.get("answer", ""), [], [], must)["memory"]
        scores.append(mem)
        print("\n" + "=" * 96)
        print(f"  {tid}   customer={c['customer_context']['customer_id']}")
        print(f"  USER SAYS    : {c['ticket']}")
        print(f"  SHOULD RECALL: {must[0]}")
        print(f"  AGENT ANSWER : {out.get('answer', '')}")
        print(f"  >> MEMORY score: {mem:.2f}   {'✅ recalled' if mem >= 0.99 else '❌ still missing'}")

    avg = sum(scores) / len(scores)
    print("\n" + "#" * 96)
    print(f"  MEMORY dimension WITH memory: {avg:.2f}   "
          f"({sum(s >= 0.99 for s in scores)}/{len(scores)} recalled)   [was 0.00 in Step 1]")
    print("#" * 96 + "\n")
    get_client().flush()


if __name__ == "__main__":
    main()
