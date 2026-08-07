"""
MEMORY · Step 3 — the WRITE path (memory forms over time).

A customer with NO prior memory. Turn 1: they reveal a durable preference. We form_memory() — the
episodic ticket is appended AND the durable fact is extracted into semantic memory. Turn 2 (a fresh,
later ticket): the agent recalls the fact it learned in turn 1. That is the full read+write loop.

    python3 memory/write_memory_demo.py
"""

import io
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from sessions.s10_full_agent.agent import classify
from memory.store import MemoryStore
from memory.formation import form_memory
from langfuse import get_client

STORE = MemoryStore().seed_from_world_state()
CID = "cust_pro_012"                                    # a customer with NO ticket history
CTX = {"customer_id": CID, "plan": "pro", "region": "US"}


def answer(ticket):
    block = STORE.recall(CID)
    with redirect_stdout(io.StringIO()):
        return classify(f"{ticket}\n\n{block}" if block else ticket, CTX)


def main():
    print("\n" + "#" * 96)
    print("  MEMORY · STEP 3 — the write path: learn a fact in turn 1, recall it in turn 2")
    print("#" * 96)

    print(f"\n  [BEFORE]  memory for {CID}: {STORE.recall(CID) or '(nothing — new customer)'}")

    # ── Turn 1: the customer reveals a durable preference ───────────────────────
    t1 = "One thing going forward — please always reply to me in French. Je préfère le français."
    print(f"\n  [TURN 1]  USER: {t1}")
    out1 = answer(t1)
    print(f"            AGENT: {out1['answer']}")

    # ── WRITE: form memory from the finished ticket ─────────────────────────────
    written = form_memory(STORE, CID, t1, out1)
    print(f"\n  [WRITE]   formed memory -> durable_facts={written['durable_facts']}")
    print(f"            episodic summary: {written['summary']}")
    print(f"\n  [MEMORY AFTER WRITE]\n{_indent(STORE.recall(CID))}")

    # ── Turn 2: a fresh, later ticket — does the agent recall? ───────────────────
    t2 = "How many seats does my plan include, and how many am I using?"
    print(f"\n  [TURN 2]  USER: {t2}")
    out2 = answer(t2)
    print(f"            AGENT: {out2['answer']}")

    ans = out2["answer"].lower()
    french = any(w in ans for w in ("votre", "vous", "sièges", "forfait", "utilisez",
                                    "êtes", "inclut", "bonjour", "français", "places"))
    print("\n  " + "=" * 90)
    print("  RESULT:", "✅ the preference learned in turn 1 was recalled AND applied in turn 2 (reply in French)"
          if french else "⚠ memory recalled, but the turn-2 reply is not in French — application gap")
    print("  The loop: end a ticket -> form_memory writes semantic+episodic -> next ticket recalls it.")
    print("  " + "=" * 90 + "\n")
    get_client().flush()


def _indent(s):
    return "\n".join("      " + ln for ln in s.splitlines())


if __name__ == "__main__":
    main()
