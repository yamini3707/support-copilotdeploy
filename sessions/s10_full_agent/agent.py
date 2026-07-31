"""
FULL agent — the router→specialist tool-calling agent + the UNIFIED s9 RAG, fully traced.

This is the capstone: the production-shaped agent that does BOTH kinds of work.
  - structured tools : get_customer / get_subscription / get_invoices / issue_refund /
                       get_incident_status / get_plan_catalog / ... (facts about THIS customer)
  - knowledge tool   : search_knowledge_base -> the s9 unified pipeline (hybrid + HyDE + graph +
                       parent-child, then rerank + abstain) — ONE tool that replaces the old
                       separate search_kb + graph_lookup.

Router picks the specialist(s); each specialist has its OWN scoped tools plus the knowledge tool;
the aggregator computes priority in code. Every LLM call, tool call, retrieval strategy and DB query
is a nested Langfuse span, so one ticket = one trace.

    python3 sessions/s10_full_agent/agent.py        # one ticket
"""

import json
import operator
import os
import sys
from typing import Annotated, TypedDict

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "data_gen"))
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

from langgraph.graph import StateGraph, START, END
from tools.tools import REGISTRY                         # the structured (mock) tools over world_state
from tools.schemas import TOOL_SCHEMAS
from labeling import priority_rule
from eval.retry import call_with_retry
from sessions.s10_full_agent.prompts import ROUTER_PROMPT, SPECIALIST_PROMPTS
from sessions.s9_rag_final.pipeline import unified_search   # the unified divide-and-conquer RAG
from sessions.s9_rag_final import log as L

MODEL = os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o")
MARGIN = float(os.getenv("ROUTER_MARGIN", "0.25"))
MAX_STEPS = 5
CATEGORIES = list(SPECIALIST_PROMPTS)


# ── the knowledge tool: the whole s9 unified RAG behind one function ───────────────────────────
def search_knowledge_base(query: str, plan: str = None) -> dict:
    """One tool = hybrid + HyDE + graph + parent-child, reranked and abstention-gated (s9 pipeline).
    unified_search is itself an @observe span, so it nests under the calling specialist in the trace."""
    res = unified_search(query, plan)
    if res["abstain"]:
        return {"status": "NO_RELEVANT_DOCUMENTS", "docs": []}
    return {"status": "OK", "docs": [{"doc_id": d["doc_id"], "text": d["text"][:1200],
                                      "found_by": d["sources"]} for d in res["docs"]]}


SEARCH_KB_SCHEMA = {"type": "function", "function": {
    "name": "search_knowledge_base",
    "description": "Search the CloudDesk knowledge base. Runs hybrid + HyDE + graph retrieval in "
                   "parallel (so it also CONNECTS related docs across incidents), reranks, and returns "
                   "the most relevant passages, or NO_RELEVANT_DOCUMENTS. Use for any policy / how-to / "
                   "troubleshooting question AND for relational ones like 'has this incident happened "
                   "before / same root cause / how do we prevent it'.",
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "what to look up, in your own words"},
        "plan": {"type": "string", "enum": ["free", "pro", "business", "enterprise"],
                 "description": "the customer's plan — ONLY for own-account questions; omit for cross-plan/general"}},
        "required": ["query"]}}}

REGISTRY_ALL = {**REGISTRY, "search_knowledge_base": search_knowledge_base}
SCHEMAS_ALL = TOOL_SCHEMAS + [SEARCH_KB_SCHEMA]

# least-privilege tool scoping — each specialist gets its structured tools + the one knowledge tool.
# No separate graph_lookup: graph retrieval now lives INSIDE search_knowledge_base.
SPECIALIST_TOOLS = {
    "billing": ["get_customer", "get_subscription", "get_invoices", "check_refund_eligibility",
                "check_days_since", "issue_refund", "create_escalation", "search_knowledge_base"],
    "technical": ["get_customer", "get_subscription", "get_incident_status", "create_escalation",
                  "search_knowledge_base"],
    "account": ["get_customer", "get_subscription", "get_plan_catalog", "create_escalation",
                "search_knowledge_base"],
    "feature_request": ["get_subscription", "get_plan_catalog", "search_knowledge_base"],
    "other": [],
}

# hint for the technical specialist: the KB tool now covers relational/incident questions too
TECH_KB_HINT = ("\n\nFor questions about whether an incident has occurred before, shares a root cause "
                "with a past incident, or what a change/outage would also affect, use "
                "search_knowledge_base — it connects incidents, root causes and dependents across "
                "documents (it runs graph retrieval internally). Cite the doc_ids it returns.")


def _client():
    from openai import OpenAI
    return OpenAI()


def _as_confidence(v):
    if isinstance(v, (int, float)):
        v = float(v)
        return v / 100.0 if v > 1.0 else max(0.0, v)
    return {"high": 0.9, "medium": 0.6, "low": 0.3}.get(str(v).lower(), 0.5)


class State(TypedDict):
    ticket: str
    context: dict
    route: list
    specialist_outputs: Annotated[list, operator.add]


@observe(name="router")
def router(state: State) -> dict:
    user = f"Ticket:\n{state['ticket']}\n\nCustomer context: {state['context']}"
    resp = call_with_retry(_client().chat.completions.create,
        model=MODEL, temperature=0.0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": ROUTER_PROMPT}, {"role": "user", "content": user}])
    cands = json.loads(resp.choices[0].message.content).get("candidates", [])
    cands = sorted([c for c in cands if c.get("category") in CATEGORIES],
                   key=lambda c: c.get("confidence", 0), reverse=True) or [{"category": "other", "confidence": 1.0}]
    top = cands[0]["category"]
    if len(cands) == 1:
        route = [top]
    else:
        margin = cands[0].get("confidence", 0) - cands[1].get("confidence", 0)
        route = [top] if margin >= MARGIN else [c["category"] for c in cands[:3]
                                                if cands[0]["confidence"] - c["confidence"] < MARGIN]
    L.step(f"router -> {route}", why="route to the specialist(s); on a close call we fan out to the tied ones.")
    return {"route": route}


def _run_tool(name, args, allowed):
    if name not in allowed:                     # dispatch-level least-privilege guard
        return {"error": f"tool {name} is not available to this specialist"}
    fn = REGISTRY_ALL.get(name)
    if not fn:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(**args)
    except Exception as e:
        return {"error": f"{name} failed: {e}"}


def make_specialist(category: str):
    system = SPECIALIST_PROMPTS[category] + (TECH_KB_HINT if category == "technical" else "")
    allowed = SPECIALIST_TOOLS[category]
    schemas = [s for s in SCHEMAS_ALL if s["function"]["name"] in allowed]

    @observe(name=f"specialist_{category}")
    def node(state: State) -> dict:
        if category not in state["route"]:
            return {}
        L.step(f"specialist[{category}] handling ticket (tools: {allowed})")
        client = _client()
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": f"Ticket:\n{state['ticket']}\n\nCustomer context: {state['context']}"}]
        tool_log = []
        for _ in range(MAX_STEPS if schemas else 0):
            resp = call_with_retry(client.chat.completions.create,
                model=MODEL, temperature=0.0, tools=schemas, messages=messages)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                break
            messages.append(msg)
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                tool_log.append({"tool": tc.function.name, "args": args})
                L.detail(f"[{category}] tool call: {tc.function.name}({args})")
                result = _run_tool(tc.function.name, args, allowed)
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(result, default=str)})
        messages.append({"role": "user", "content": "Now return ONLY the final JSON described above."})
        final = call_with_retry(client.chat.completions.create,
            model=MODEL, temperature=0.0, response_format={"type": "json_object"}, messages=messages)
        out = json.loads(final.choices[0].message.content)
        out["_category"] = category
        out["tool_calls"] = tool_log
        return {"specialist_outputs": [out]}

    return node


@observe(name="aggregate")
def aggregator(state: State) -> dict:
    outs = state["specialist_outputs"]
    handled = [o for o in outs if o.get("handled")] or outs
    best = max(handled, key=lambda o: _as_confidence(o.get("confidence"))) if handled else {}
    ctx = state["context"]
    impact = best.get("impact") if best.get("impact") in ("blocked", "degraded", "inquiry") else "inquiry"
    scope = best.get("scope") if best.get("scope") in ("org", "single") else "single"
    final = {
        "category": best.get("_category", "other"),
        "priority": priority_rule(impact, scope, ctx.get("plan", "pro"), bool(best.get("is_financial"))),
        "requires_human": bool(best.get("requires_human")),
        "confidence": _as_confidence(best.get("confidence")),
        "answer": best.get("answer", ""),
        "citations": best.get("citations", []),
        "tool_calls": best.get("tool_calls", []),
    }
    return {"specialist_outputs": [{"_final": final}]}


def _build():
    g = StateGraph(State)
    g.add_node("router", router)
    for cat in CATEGORIES:
        g.add_node(cat, make_specialist(cat))
    g.add_node("aggregator", aggregator)
    g.add_edge(START, "router")
    g.add_conditional_edges("router", lambda s: s["route"], {c: c for c in CATEGORIES})
    for cat in CATEGORIES:
        g.add_edge(cat, "aggregator")
    g.add_edge("aggregator", END)
    return g.compile()


_APP = _build()


@observe(name="support_copilot")
def classify(ticket: str, customer_context: dict | None = None) -> dict:
    L.section(f"TICKET: {ticket}")
    result = _APP.invoke({"ticket": ticket, "context": customer_context or {},
                          "route": [], "specialist_outputs": []})
    out = next((o["_final"] for o in result["specialist_outputs"] if "_final" in o),
               {"category": "other", "priority": "low", "requires_human": False,
                "confidence": 0.0, "answer": "", "citations": [], "tool_calls": []})
    L.step(f"FINAL: [{out['category']}/{out['priority']}] {out['answer']}")
    return out


if __name__ == "__main__":
    lf = get_client()
    out = classify("We had the EU SSO login outage, INC-2041. Has this same root cause hit us before, "
                   "and how do we prevent it?", {"customer_id": "cust_enterprise_000", "plan": "enterprise"})
    print("\nANSWER:", out["answer"])
    print("category/priority:", out["category"], "/", out["priority"])
    print("tools used:", [t["tool"] for t in out["tool_calls"]])
    lf.flush()
    print("flushed to Langfuse.")
