"""
Session 2 — Prompt-engineering experiments.

FOUR strategies to improve the Session-1 classifier's ROUTING, each self-contained. You run
them and compare (run.py). The lesson comes from MEASUREMENT, not opinion:
  - the simplest strategy usually wins (few-shot beats the fancy multi-call ones);
  - but even the winner barely moves the OVERALL score — routing is only ~20% of the job,
    and the rest needs tools / RAG / memory (Sessions 3+). Prompt engineering has a ceiling.

EVAL HYGIENE — READ THIS: the few-shot examples below are hand-written and DELIBERATELY do NOT
reuse any ticket from data/train.json. Few-shotting with your test set leaks answers and turns
the eval into a memorisation test. Teach the *rules* with fresh scenarios instead.
"""

import json
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "data_gen"))

from sessions.s1_classifier.agent import RULES   # the shared playbook rules
from labeling import priority_rule                # the exact priority rule, in code

MODEL = os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o-mini")


def _call(system, user):
    from openai import OpenAI
    r = OpenAI().chat.completions.create(
        model=MODEL, temperature=0.0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return json.loads(r.choices[0].message.content)


def _finish(resp):
    """Fill the fields this session doesn't touch (no tools/RAG yet)."""
    resp.setdefault("citations", [])
    resp.setdefault("tool_calls", [])
    return resp


def _user(ticket, ctx):
    return f"Ticket:\n{ticket}\n\nCustomer context: {ctx or {}}"


_ANSWER_TAIL = """
Also write a brief one-line "answer" to the customer (do not invent policy details or approvals)."""

_RETURN = """
Return ONLY JSON: {"category","priority","requires_human","confidence","answer"}."""


# ─────────────────────────── Strategy 1: FEW-SHOT ───────────────────────────
# Fresh scenarios that teach the EDGES — none of these appear in data/train.json.
FEWSHOT = """
Worked examples (study the reasoning; these are NOT from the test set):

ticket: "Where do I change our workspace's default timezone?"  context: {"plan":"pro"}
-> {"category":"account","priority":"low","requires_human":false,"confidence":0.9,"answer":"You can change it under workspace settings — happy to point you there."}
(a settings how-to with no money = account; a plain question = inquiry = low)

ticket: "Every page loads a 503 error for our whole team right now."  context: {"plan":"pro"}
-> {"category":"technical","priority":"urgent","requires_human":false,"confidence":0.85,"answer":"That looks like an outage on our side — we're investigating."}
(something broken = technical; a total outage for many users = blocked + org = urgent)

ticket: "Could you add a way to bulk-archive old projects?"  context: {"plan":"pro"}
-> {"category":"feature_request","priority":"low","requires_human":false,"confidence":0.9,"answer":"That's not available today, but I'll pass the request along."}
(wants functionality that does not exist yet = feature_request)

ticket: "I think last month's invoice overcharged me by about $4."  context: {"plan":"pro"}
-> {"category":"billing","priority":"medium","requires_human":false,"confidence":0.85,"answer":"Let me look into that charge for you."}
(money = billing; any active money problem is at least medium, even a small one)

ticket: "Our reports page throws an error for one of our admins. We're on Enterprise."  context: {"plan":"enterprise"}
-> {"category":"technical","priority":"high","requires_human":false,"confidence":0.8,"answer":"Sorry about that — let's get your reports working."}
(broken feature = technical; degraded + single = medium, then Enterprise +1 = high)

ticket: "?????"  context: {"plan":"free"}
-> {"category":"other","priority":"low","requires_human":false,"confidence":0.6,"answer":"Happy to help — could you tell me a bit more about the issue?"}
(no product, error, or request named = too vague to route = other)
"""


def classify_fewshot(ticket, ctx=None):
    return _finish(_call(RULES + FEWSHOT + _ANSWER_TAIL + _RETURN, _user(ticket, ctx)))


# ─────────────────────── Strategy 2: REASONING-FIRST ───────────────────────
# Give the model a scratchpad so it derives priority step-by-step instead of guessing
# (and stops leaking intermediate values like "inquiry" into the priority field).
_REASONING = RULES + """

Think step by step. Return JSON where a "reasoning" object comes FIRST, then the final fields:
{"reasoning": {"impact": "...", "scope": "...", "plan_bump": "...", "category_reason": "...", "escalation_reason": "..."},
 "category": "...", "priority": "<low|medium|high|urgent>", "requires_human": <bool>, "confidence": <0..1>,
 "answer": "<one line>"}
The final "priority" must be exactly one of low|medium|high|urgent (never an impact word)."""


def classify_reasoning(ticket, ctx=None):
    return _finish(_call(_REASONING, _user(ticket, ctx)))


# ───────────────────── Strategy 3: ROUTER -> SPECIALIST ─────────────────────
# Two calls: a router picks the category + perceives impact/scope; a category-specialised
# prompt then decides priority/escalation. Tests whether decomposition beats one big prompt.
_ROUTER = """Route this support ticket. Return JSON:
{"category": one of billing|technical|account|feature_request|other,
 "impact": blocked|degraded|inquiry, "scope": org|single}
Rules: broken feature=technical, missing feature=feature_request, "how do I enable X?"=account,
too-vague=other. blocked=can't use product; a money problem is degraded (not blocked)."""

_SPECIALIST_HINT = {
    "billing": "Money issues are at least medium. A chargeback already filed -> requires_human.",
    "technical": "Outages (blocked+org) are urgent. A rate limit/partial issue is degraded.",
    "account": "Plan/settings how-tos are inquiries. Sole-admin lockout or legal request -> requires_human.",
    "feature_request": "Usually a low-priority inquiry; do not promise to build it.",
    "other": "Greetings/vague tickets are low priority and self-handled.",
}


def classify_router(ticket, ctx=None):
    route = _call(_ROUTER, _user(ticket, ctx))
    cat = route.get("category", "other")
    specialist = (f"You are the {cat} support specialist. {_SPECIALIST_HINT.get(cat, '')}\n\n"
                  + RULES + "\n\nGiven the router's read (impact/scope) and the customer plan, decide "
                  "priority + escalation." + _ANSWER_TAIL +
                  '\nReturn ONLY JSON with priority in {low|medium|high|urgent} and confidence a '
                  'number 0..1: {"priority":"...","requires_human":<bool>,"confidence":<0..1>,"answer":"..."}.')
    out = _call(specialist, _user(ticket, ctx) + f"\n\nRouter read: {route}")
    return _finish({"category": cat, "priority": out.get("priority"),
                    "requires_human": out.get("requires_human"),
                    "confidence": out.get("confidence", 0.7), "answer": out.get("answer", "")})


# ─────────────────── Strategy 4: PERCEPTION + CODE ───────────────────
# The LLM only PERCEIVES (category/impact/scope/is_financial); Python computes priority with
# the exact rule. Tests: don't make the LLM do arithmetic that code does perfectly.
_PERCEPTION = RULES + """

Do NOT output priority. Perceive the ticket and return JSON:
{"category": "...", "impact": "blocked|degraded|inquiry", "scope": "org|single",
 "is_financial": <bool>, "requires_human": <bool>, "confidence": <0..1>, "answer": "<one line>"}"""


def classify_perception(ticket, ctx=None):
    ctx = ctx or {}
    p = _call(_PERCEPTION, _user(ticket, ctx))
    impact = p.get("impact") if p.get("impact") in ("blocked", "degraded", "inquiry") else "inquiry"
    scope = p.get("scope") if p.get("scope") in ("org", "single") else "single"
    priority = priority_rule(impact, scope, ctx.get("plan", "pro"), bool(p.get("is_financial")))
    return _finish({"category": p.get("category"), "priority": priority,
                    "requires_human": bool(p.get("requires_human")),
                    "confidence": p.get("confidence", 0.7), "answer": p.get("answer", "")})


VARIANTS = {
    "few_shot": classify_fewshot,
    "reasoning": classify_reasoning,
    "router": classify_router,
    "perception": classify_perception,
}
