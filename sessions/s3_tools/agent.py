"""
Session 3 — Tool-using agent (the agentic loop).

The classifier could only guess. Now the agent can LOOK THINGS UP: it runs a loop where the
model may call tools, read the results, call more tools (multi-hop), and only then answer.
The model can request several tools at once (parallel), which we execute and feed back together.

Every tool call is recorded in `tool_calls` on the final response, so the eval can score
tool-use correctness (and catch forbidden-tool safety violations).

    from sessions.s3_tools.agent import classify
    result = classify(ticket, customer_context)   # customer_context includes customer_id
"""

import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import sys
ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

sys.path.insert(0, os.path.join(ROOT, "data_gen"))
from sessions.s1_classifier.agent import RULES   # reuse the playbook rules
from tools.tools import REGISTRY
from tools.schemas import TOOL_SCHEMAS
from labeling import priority_rule                # priority is computed in code, not by the LLM
from eval.retry import call_with_retry            # backoff on transient 429s

MODEL = os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o")
MAX_STEPS = 5   # cap the loop (multi-hop budget); prevents runaway tool use

SYSTEM = RULES + """

CATEGORY — watch these edges (examples, NOT from the test set):
- "Email me a copy of last month's receipt" → billing (invoices/records are billing, not account).
- "Our integration gets 403/429 from the API" → technical (an error is technical, even when a plan limit is the cause).
- "Erase all the data you hold on us for compliance" → account (data/compliance admin, not other).
- "I deleted a doc yesterday — can I get it back?" → account (data management, not a feature request).
- "Nobody can edit anything since this morning" → check the account first; if it's past_due, it's billing.

PRIORITY — do NOT output a priority value. Instead perceive and report: impact (blocked/degraded/
inquiry), scope (org/single), and is_financial (true if there is active money harm). The system
computes the final priority from these plus the plan — you never apply the base table or plan bumps.

You have TOOLS. Use them to VERIFY before you answer — never guess a customer's plan, status,
invoices, or an active incident. Rules of thumb:
- Look up the subscription/profile when the answer depends on plan, status, or limits.
- NEVER do date arithmetic yourself — always use check_days_since.
- You may call several tools at once, and call more after seeing results. Don't repeat identical calls.

ACCESS / "NOT WORKING" FLOW — when a customer reports lost or restricted access, or that a
feature/page/service isn't working, establish the ACCOUNT context before blaming anything external:
  1. FIRST call get_subscription (status + plan limits); call get_customer if you need their region.
     Rule out account-level causes:
       - status "past_due" or "canceled" → THAT is the cause. Tell them to update their payment
         method / renew to restore access. Do NOT blame a platform incident.
       - the feature isn't on their plan, or they've hit a plan limit (e.g. API 429) → that's the cause.
  2. ONLY if the account is healthy (active + feature included) → call get_incident_status, passing
     the customer's plan and region. Treat an incident as the cause ONLY if it directly concerns the
     SAME feature the customer reported (match on the incident's service and summary). Do NOT link
     indirectly: an incident about the public API is NOT the cause of a broken admin page just
     because pages can call APIs. Different service ⇒ NOT a match. You are a support agent, not an
     incident investigator — never fabricate a cause.
  3. If neither an account cause nor a directly-matching incident explains the issue, you do NOT
     have a grounded answer. Do NOT offer generic or guessed fixes ("try refreshing", "clear your
     cache", "check your browser", etc.). Instead hand off: set requires_human = true and call
     create_escalation with a short summary.

REFUND FLOW — follow this order:
  1. Find the charge: call get_invoices with the filters you can infer from the ticket
     (invoice_id if named, amount like "$300", since_days for "last month"). Read the descriptions.
  2. Select the relevant invoice(s):
       none match  → tell the customer you can't find that charge;
       exactly one → proceed with it;
       several     → handle each; if their outcomes differ, list them and ask which (do not guess).
  3. For each selected invoice, call check_refund_eligibility:
       policy "always_eligible"      → it is refundable; do NOT check the window;
       policy "eligible_within_days" → call check_days_since(invoice_date, window_days):
                                        within → refundable; outside → not refundable.
  4. Only if refundable, call issue_refund. Never otherwise.
  5. Compose the reply from what you found (cover every selected invoice if there are several).

WHAT COUNTS AS A DUPLICATE: the ONLY reliable signal is that an invoice's description flags it as a
duplicate. The same amount — even on the same date — is NOT necessarily a duplicate (a customer may
have legitimately made two purchases). If a customer claims they were "charged twice" but no invoice
is flagged as a duplicate, tell them there is no duplicate and no refund is needed.
ALREADY REFUNDED: if the invoice status is already "refunded", do NOT refund it again — tell the
customer the refund is already underway and the amount should appear in their account within a few days.

HANDLE AMBIGUITY — do not guess. If the customer's description matches MORE THAN ONE charge
(e.g. they name only an amount like "$300" and several invoices have that amount, or they say
"a charge"/"last month" without an invoice id), the request is AMBIGUOUS — even if only one of
those charges happens to be refundable. Do NOT pick one yourself. Look up the candidates, then
ASK the customer which invoice they mean, briefly listing each matching charge with its date and
refund status (within the 14-day window or not). NEVER issue a refund on an ambiguous request —
refunding the wrong charge is an error.

When you have enough information, STOP calling tools and return the final JSON:
{"category","priority","requires_human","confidence","answer","citations","actions"}
- answer: the customer-facing reply, grounded in what the tools returned.
- citations: [] for now (knowledge-base search comes later).
- actions: any write actions you took (issue_refund / create_escalation) as
  [{"tool": "...", "args": {...}}]. Only include actions you actually performed via a tool call.
"""


def _run_tool(name, args):
    fn = REGISTRY.get(name)
    if not fn:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(**args)
    except Exception as e:
        return {"error": f"{name} failed: {e}"}


def classify(ticket: str, customer_context: dict | None = None, system: str | None = None) -> dict:
    from openai import OpenAI
    client = OpenAI()

    ctx = customer_context or {}
    messages = [
        {"role": "system", "content": system or SYSTEM},
        {"role": "user", "content": f"Ticket:\n{ticket}\n\nCustomer context: {ctx}"},
    ]
    tool_calls_log = []

    for step in range(MAX_STEPS):
        resp = call_with_retry(client.chat.completions.create,
            model=MODEL, temperature=0.0, tools=TOOL_SCHEMAS,
            messages=messages,
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            # Model is done reasoning — ask for the final structured JSON.
            break

        # Execute every requested tool (several in one turn = parallel; a new turn = a hop).
        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result = _run_tool(tc.function.name, args)
            tool_calls_log.append({"step": step, "tool": tc.function.name, "args": args})
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result, default=str)})

    # Final turn: force a crisply-typed JSON answer (the chatty tool dialogue tends to make the
    # model leak its reasoning into fields, so we restate the exact types here).
    messages.append({"role": "user", "content":
        'Now return ONLY this JSON, with final values as plain scalars (no reasoning, no extra keys):\n'
        '{"category":"<billing|technical|account|feature_request|other>",'
        '"impact":"<blocked|degraded|inquiry>","scope":"<org|single>","is_financial":<true|false>,'
        '"requires_human":<true|false>,"confidence":<number 0..1>,'
        '"answer":"<one line, grounded in the tool results>",'
        '"citations":[],"actions":[{"tool":"...","args":{...}}]}'})
    final = call_with_retry(client.chat.completions.create,
        model=MODEL, temperature=0.0,
        response_format={"type": "json_object"}, messages=messages,
    )
    out = json.loads(final.choices[0].message.content)
    # Priority is COMPUTED from the LLM's perception (impact/scope/is_financial) + the plan — the
    # LLM never does the base-table/plan-bump arithmetic itself.
    impact = out.get("impact") if out.get("impact") in ("blocked", "degraded", "inquiry") else "inquiry"
    scope = out.get("scope") if out.get("scope") in ("org", "single") else "single"
    out["priority"] = priority_rule(impact, scope, ctx.get("plan", "pro"), bool(out.get("is_financial")))
    out["confidence"] = _as_confidence(out.get("confidence"))
    out["tool_calls"] = tool_calls_log
    out.setdefault("citations", [])
    out.setdefault("actions", [])
    return out


def _as_confidence(v):
    """Coerce confidence to a 0..1 float — models return 'high', 95, 100.0, etc."""
    if isinstance(v, (int, float)):
        v = float(v)
        return v / 100.0 if v > 1.0 else max(0.0, v)
    return {"high": 0.9, "medium": 0.6, "low": 0.3}.get(str(v).lower(), 0.5)
