"""
The request lifecycle — everything the course built, in order, for ONE ticket.

    handle_ticket(ticket, context)
        1. MEMORY RECALL   — unified (embedding + graph) recall for this customer, injected as context
        2. AGENT           — router -> specialist -> scoped tools + unified RAG
                             (access-control guardrail enforced inside the tool dispatch)
        3. OUTPUT GUARDRAIL— disclosure filter scrubs the reply before it reaches the customer
        4. MEMORY FORMATION— distill the finished ticket into durable facts + an episodic record

The whole thing is one Langfuse span ("support_copilot"); the agent, RAG, tools and memory calls all
nest underneath it, so one ticket = one readable trace.
"""

import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from langfuse import observe, get_client
from app.config import MEMORY
from app.agent import classify
from app.guardrails import disclosure_filter


@observe(name="support_copilot")
def handle_ticket(ticket: str, context: dict | None = None, *, form_memory: bool = True) -> dict:
    """Run one ticket end to end. `context` must carry the authenticated customer_id (and plan/region).
    Returns the final answer plus a `trace` of what each layer did (for the demo/UI)."""
    context = context or {}
    cid = context.get("customer_id")

    # 1. recall — what do we remember about THIS customer that's relevant to THIS ticket?
    mem = MEMORY.recall(cid, ticket) if cid else {"block": "", "facts": [], "graph_terms": [], "graph_nodes": []}
    prompt = f"{ticket}\n\n{mem['block']}" if mem["block"] else ticket

    # 2. the agent (router -> specialist -> tools + RAG; access control inside the dispatch)
    out = classify(prompt, context)

    # 3. output guardrail — scrub any internal/confidential content before replying
    guard = disclosure_filter(out.get("answer", ""))
    out["answer"] = guard["safe_reply"]

    # 4. write path — remember this ticket for next time (skippable for read-only eval runs)
    written = MEMORY.form(cid, ticket, out) if (form_memory and cid) else None

    out["trace"] = {
        "memory_recall": {
            "facts_injected": [{"source": s, "text": t} for _, s, t in mem["facts"]],
            "graph_terms": mem["graph_terms"],
            "graph_nodes": mem["graph_nodes"],
        },
        "output_guardrail": {"flagged": guard["flagged"]},
        "memory_written": written,
    }
    return out


def flush():
    """Flush buffered Langfuse spans (call after a request when running as a script)."""
    try:
        get_client().flush()
    except Exception:
        pass


if __name__ == "__main__":
    # a quick end-to-end smoke: the Acme multi-hop showcase (needs OPENAI + WEAVIATE + LANGFUSE env)
    res = handle_ticket(
        "We'd like to turn on your new US-hosted analytics add-on. Can we just enable it?",
        {"customer_id": "cust_enterprise_003", "plan": "enterprise", "region": "US"},
        form_memory=False)
    print("\nANSWER:", res["answer"])
    print("category/priority:", res["category"], "/", res["priority"])
    print("memory facts injected:", len(res["trace"]["memory_recall"]["facts_injected"]))
    print("graph nodes matched:", res["trace"]["memory_recall"]["graph_nodes"])
    flush()
