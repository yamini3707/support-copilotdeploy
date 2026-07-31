"""
The unified agentic-RAG agent — everything wired together, fully traced.

A small agentic loop with ONE powerful tool, `search_knowledge_base(query, plan)`:
  - the LLM decides whether to pass `plan` (the metadata filter) — own-account question -> filter,
    cross-plan/other-plan -> omit,
  - the tool runs the DIVIDE-AND-CONQUER pipeline (hybrid + hyde + graph in parallel -> merge ->
    rerank -> abstain),
  - the LLM grounds its answer in the returned docs, or escalates if the KB abstained.

Every LLM call is traced (patched OpenAI client) and each stage is an @observe span, so one ticket =
one nested Langfuse trace.

    python3 sessions/s9_rag_final/agent.py        # one ticket
"""

import json
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

# trace every OpenAI call by swapping in the instrumented client BEFORE anything calls it
import openai as _openai_mod
from langfuse.openai import OpenAI as _LFOpenAI
_openai_mod.OpenAI = _LFOpenAI
from langfuse import observe, get_client

from eval.retry import call_with_retry
from sessions.s9_rag_final.pipeline import unified_search
from sessions.s9_rag_final import log as L

MODEL = os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o")
MAX_STEPS = 3

SYSTEM = (
    "You are CloudDesk's support agent. Use the search_knowledge_base tool to ground every answer in "
    "the knowledge base.\n"
    "- Pass `plan` ONLY when the question is about the customer's OWN account/plan (so results are "
    "filtered to their tier). For a cross-plan or general question, omit `plan`.\n"
    "- Answer strictly from the returned docs, and cite the doc_ids you used.\n"
    "- If the tool returns NO_RELEVANT_DOCUMENTS, do not fabricate — say you don't have that "
    "information and will escalate.")

TOOL = {"type": "function", "function": {
    "name": "search_knowledge_base",
    "description": "Search the CloudDesk knowledge base (runs hybrid + HyDE + graph retrieval in "
                   "parallel, then reranks). Returns the most relevant docs, or NO_RELEVANT_DOCUMENTS.",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "what to look up, in your own words"},
        "plan": {"type": "string", "enum": ["free", "pro", "business", "enterprise"],
                 "description": "the customer's plan — ONLY for own-account questions; omit otherwise"}},
        "required": ["query"]}}}


def _client():
    from openai import OpenAI
    return OpenAI()


@observe(name="support_copilot")
def answer(ticket, customer_context=None):
    L.section(f"TICKET: {ticket}")
    client = _client()
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Ticket:\n{ticket}\n\nCustomer context: {customer_context or {}}"}]
    used_docs = []
    for turn in range(MAX_STEPS):
        L.step(f"agent turn {turn + 1}/{MAX_STEPS}: ask the LLM what to do next",
               why="the agent loops — it may search, read results, then search again or answer; it "
                   "decides whether to call the tool or produce the final answer.")
        resp = call_with_retry(client.chat.completions.create,
            model=MODEL, temperature=0, tools=[TOOL], messages=messages)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            L.step("LLM produced no tool call -> it's ready to answer; leaving the loop")
            break
        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            L.step(f"tool call: search_knowledge_base(query={args.get('query')!r}, plan={args.get('plan')})",
                   why="the LLM passes `plan` only for own-account questions (so results are filtered to "
                       "the customer's tier); it omits it for cross-plan/general questions.")
            result = unified_search(args.get("query", ticket), args.get("plan"))
            if result["abstain"]:
                payload = {"status": "NO_RELEVANT_DOCUMENTS", "docs": []}
                L.step("tool result: NO_RELEVANT_DOCUMENTS",
                       why="the pipeline abstained, so we tell the agent nothing was found — it must "
                           "escalate rather than invent an answer.")
            else:
                used_docs = result["docs"]
                # text is already a bounded retrieval unit (chunk / parent block / graph slice); the
                # cap is just a safety bound, generous enough not to cut a unit mid-way.
                payload = {"status": "OK", "docs": [{"doc_id": d["doc_id"], "text": d["text"][:1600],
                                                     "found_by": d["sources"]} for d in used_docs]}
                L.step(f"tool result: OK -> {len(used_docs)} doc(s): "
                       f"{[d['doc_id'] for d in used_docs]} (the agent must ground its answer in these)")
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(payload)})
    final = msg.content or ""
    L.step(f"ANSWER: {final}")
    return {"answer": final, "docs": [d["doc_id"] for d in used_docs]}


if __name__ == "__main__":
    lf = get_client()
    out = answer("We had the EU SSO login outage, INC-2041. Has this same root cause hit us before, "
                 "and how do we prevent it?", {"customer_id": "cust_enterprise_000", "plan": "enterprise"})
    print("\nFINAL:", out["answer"])
    print("docs used:", out["docs"])
    lf.flush()
    print("flushed to Langfuse.")
