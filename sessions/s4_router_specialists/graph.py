"""
Router → specialist architecture, built with LangGraph.

Flow:
  START → router → (conditional fan-out) → one or more specialists (parallel) → aggregator → END

- router: an LLM emits a confidence per category.
- fan-out-on-low-margin: if the top category dominates (top1 - top2 >= MARGIN) we run only that
  specialist; if it's a close call we run the tied specialists IN PARALLEL (LangGraph fans out by
  returning a list of node names from the conditional edge).
- each specialist: a small tool-using loop with its OWN prompt (its category's edge cases live
  there — see prompts.py). It can reject a misroute by returning handled=false.
- aggregator: drop rejects, pick the highest-confidence handler, compute priority in code.

Exposes classify(ticket, customer_context) so the shared eval harness can score it.
"""

import json
import operator
import os
import sys
from typing import Annotated, TypedDict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "data_gen"))

from langgraph.graph import StateGraph, START, END

from tools.tools import REGISTRY
from tools.schemas import TOOL_SCHEMAS
from labeling import priority_rule
from eval.retry import call_with_retry
from sessions.s4_router_specialists.prompts import ROUTER_PROMPT, SPECIALIST_PROMPTS

MODEL = os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o")
MARGIN = float(os.getenv("ROUTER_MARGIN", "0.25"))   # fan out when top1 - top2 < MARGIN
MAX_STEPS = 5
CATEGORIES = list(SPECIALIST_PROMPTS)

# Tool scoping — least privilege. Each specialist gets ONLY the tools its domain needs.
# Only billing can issue_refund; "other" gets no data tools, so it structurally cannot leak.
SPECIALIST_TOOLS = {
    "billing": ["get_customer", "get_subscription", "get_invoices",
                "check_refund_eligibility", "check_days_since", "issue_refund", "create_escalation"],
    "technical": ["get_customer", "get_subscription", "get_incident_status", "create_escalation"],
    "account": ["get_customer", "get_subscription", "get_plan_catalog", "create_escalation"],
    "feature_request": ["get_subscription", "get_plan_catalog"],
    "other": [],
}


def _client():
    from openai import OpenAI
    return OpenAI()


def _as_confidence(v):
    if isinstance(v, (int, float)):
        v = float(v)
        return v / 100.0 if v > 1.0 else max(0.0, v)
    return {"high": 0.9, "medium": 0.6, "low": 0.3}.get(str(v).lower(), 0.5)


# ── State ─────────────────────────────────────────────────────────────────────
# specialist_outputs uses operator.add so parallel specialist nodes append to one list (fan-in).
class State(TypedDict):
    ticket: str
    context: dict
    route: list                                  # [category, ...] chosen by the router
    specialist_outputs: Annotated[list, operator.add]


# ── Router node ───────────────────────────────────────────────────────────────
def router(state: State) -> dict:
    user = f"Ticket:\n{state['ticket']}\n\nCustomer context: {state['context']}"
    resp = call_with_retry(_client().chat.completions.create,
        model=MODEL, temperature=0.0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": ROUTER_PROMPT}, {"role": "user", "content": user}])
    cands = json.loads(resp.choices[0].message.content).get("candidates", [])
    # keep valid categories, sort by confidence
    cands = sorted([c for c in cands if c.get("category") in CATEGORIES],
                   key=lambda c: c.get("confidence", 0), reverse=True) or [{"category": "other", "confidence": 1.0}]

    top = cands[0]["category"]
    if len(cands) == 1:
        route = [top]
    else:
        margin = cands[0].get("confidence", 0) - cands[1].get("confidence", 0)
        # confident → just the top; close call → fan out to the tied specialists (cap at 3)
        route = [top] if margin >= MARGIN else [c["category"] for c in cands[:3]
                                                if cands[0]["confidence"] - c["confidence"] < MARGIN]
    return {"route": route}


# ── Specialist node factory ───────────────────────────────────────────────────
def _run_tool(name, args, allowed):
    if name not in allowed:   # dispatch-level guard: a specialist can't run out-of-scope tools
        return {"error": f"tool {name} is not available to this specialist"}
    fn = REGISTRY.get(name)
    if not fn:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(**args)
    except Exception as e:
        return {"error": f"{name} failed: {e}"}


def make_specialist(category: str):
    system = SPECIALIST_PROMPTS[category]
    allowed = SPECIALIST_TOOLS[category]
    schemas = [s for s in TOOL_SCHEMAS if s["function"]["name"] in allowed]   # only this specialist's tools

    def node(state: State) -> dict:
        # skip specialists this ticket wasn't routed to
        if category not in state["route"]:
            return {}
        client = _client()
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": f"Ticket:\n{state['ticket']}\n\nCustomer context: {state['context']}"}]
        tool_log = []
        for _ in range(MAX_STEPS if schemas else 0):   # no tools → skip straight to the answer
            resp = call_with_retry(client.chat.completions.create,
                model=MODEL, temperature=0.0, tools=schemas, messages=messages)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                break
            messages.append(msg)
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                tool_log.append({"tool": tc.function.name, "args": args})
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(_run_tool(tc.function.name, args, allowed), default=str)})
        messages.append({"role": "user", "content": "Now return ONLY the final JSON described above."})
        final = call_with_retry(client.chat.completions.create,
            model=MODEL, temperature=0.0, response_format={"type": "json_object"}, messages=messages)
        out = json.loads(final.choices[0].message.content)
        out["_category"] = category
        out["tool_calls"] = tool_log
        return {"specialist_outputs": [out]}

    return node


# ── Aggregator node ───────────────────────────────────────────────────────────
def aggregator(state: State) -> dict:
    outs = state["specialist_outputs"]
    handled = [o for o in outs if o.get("handled")] or outs   # if all rejected, fall back to all
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
        "actions": best.get("actions", []),
        "tool_calls": best.get("tool_calls", []),
    }
    return {"specialist_outputs": [{"_final": final}]}


# ── Build the graph ───────────────────────────────────────────────────────────
def _build():
    g = StateGraph(State)
    g.add_node("router", router)
    for cat in CATEGORIES:
        g.add_node(cat, make_specialist(cat))
    g.add_node("aggregator", aggregator)

    g.add_edge(START, "router")
    # conditional fan-out: the router's route list becomes the set of specialist nodes to run
    g.add_conditional_edges("router", lambda s: s["route"], {c: c for c in CATEGORIES})
    for cat in CATEGORIES:
        g.add_edge(cat, "aggregator")
    g.add_edge("aggregator", END)
    return g.compile()


_APP = _build()


def classify(ticket: str, customer_context: dict | None = None) -> dict:
    result = _APP.invoke({"ticket": ticket, "context": customer_context or {},
                          "route": [], "specialist_outputs": []})
    for o in result["specialist_outputs"]:
        if "_final" in o:
            return o["_final"]
    return {"category": "other", "priority": "low", "requires_human": False,
            "confidence": 0.0, "answer": "", "citations": [], "actions": [], "tool_calls": []}
