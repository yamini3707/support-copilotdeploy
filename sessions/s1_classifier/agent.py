"""
Session 1 — Ticket Classifier baseline.

A competent first attempt: the prompt encodes CloudDesk's support playbook (category
definitions, the priority rule, the escalation policy) — the kind of prompt a sharp student
writes after reading the challenge brief. It scores decently, but has a real ceiling: stating
a rule isn't the same as the model reliably applying it (watch priority). Session 2 attacks
that ceiling with prompt-engineering technique. Run it via `sessions/s1_classifier/run.py`.
"""

import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

MODEL = os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o-mini")

# The playbook rules, kept separate so Session 2's experiments can reuse them without drift.
RULES = """You are CloudDesk's support triage assistant. Classify the ticket, following the rules exactly.
Use the customer context (especially their plan) when it matters.

CATEGORY (pick one):
- billing: money — charges, refunds, invoices, payments, pricing
- technical: something is broken or erroring
- account: access & admin, no money — login, seats, MFA, plan changes, "is X available on my plan?"
- feature_request: wants functionality that does not exist yet
- other: greeting, spam, off-topic, unintelligible
Edges: a BROKEN feature is technical; a MISSING one is feature_request. "How do I enable X?" is account.

PRIORITY (compute it, don't guess):
- impact: blocked (cannot use the core product at all) | degraded (partial, has a workaround; money issues like a double charge are degraded, not blocked) | inquiry (a question)
- scope: org (many users) | single (one user)
- base: blocked+org=urgent, blocked+single=high, degraded+org=high, degraded+single=medium, inquiry=low
- plan bump: Enterprise +1 level; Business +1 only if blocked/degraded; Pro/Free none (cap at urgent)
- billing floor: any active money harm is at least medium

ESCALATION (requires_human): default false. Set true only for:
- a bank dispute / chargeback already filed
- a legal/privacy request (e.g. GDPR data erasure)
- unverifiable account recovery (e.g. the only admin is locked out of MFA)"""

SYSTEM = RULES + """

Also write a brief, one-line "answer" to the customer. (You cannot look anything up yet, so keep
it short and never invent policy details, refund approvals, or facts you cannot verify.)

Return ONLY this JSON — final values as plain strings/numbers, no reasoning, no extra keys:
{"category": "<label>", "priority": "<low|medium|high|urgent>", "requires_human": <true|false>, "confidence": <0..1>, "answer": "<one line>"}
"""


def _call_llm(system: str, user: str) -> dict:
    """One LLM call, JSON out. Defaults to OpenAI; swap here to use another provider."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return json.loads(resp.choices[0].message.content)


def classify(ticket: str, customer_context: dict | None = None) -> dict:
    user = f"Ticket:\n{ticket}"
    if customer_context:
        user += f"\n\nCustomer context: {customer_context}"
    resp = _call_llm(SYSTEM, user)
    # No retrieval or tools yet — these stay empty and get penalized (that's the point).
    resp.setdefault("citations", [])
    resp.setdefault("tool_calls", [])
    return resp
