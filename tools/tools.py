"""
tools.py — the mock tools the support agent can call. All data comes from world_state.json
(the single source of truth), so tool results and golden labels can never disagree.

Read tools return facts. Write tools (issue_refund, create_escalation) are stubs that LOG and
return a confirmation — they do NOT mutate anything (safe to run in a classroom, still fully
scoreable from the tool-call log).

Design note: get_customer deliberately does NOT expose `locale`. A customer's language
preference is a MEMORY fact (in ticket_history) — surfacing it here would un-gate the memory
cases. get_ticket_history is added in the Memory session (S6), not here.
"""

import json
import os
from datetime import date

_WORLD = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "world_state.json")))
TODAY = date.fromisoformat(_WORLD["_meta"]["today"])
REFUND_WINDOW = _WORLD["_meta"]["refund_window_days"]


def _customer(cid):
    for c in _WORLD["customers"]:
        if c["customer_id"] == cid:
            return c
    return None


def get_customer(customer_id: str) -> dict:
    """Profile: name, plan, region, seats. (No locale — that's a memory fact.)"""
    c = _customer(customer_id)
    if not c:
        return {"error": f"no such customer: {customer_id}"}
    return {k: c[k] for k in ("customer_id", "name", "plan", "region",
                              "signup_date", "seats_purchased", "seats_used")}


def get_subscription(customer_id: str) -> dict:
    """Plan, status (active/past_due/canceled), renewal, seats, and this plan's feature limits."""
    sub = _WORLD["subscriptions"].get(customer_id)
    if not sub:
        return {"error": f"no subscription for {customer_id}"}
    plan = sub["plan"]
    return {**sub, "plan_limits": _WORLD["plan_rules"][plan]}


def get_invoices(customer_id: str, invoice_id: str = None, since_days: int = None,
                 amount: float = None) -> list:
    """Recent invoices (most recent first): id, date, amount, status, description.
    Optional filters (pass whichever the customer specified):
      invoice_id — a specific invoice (matched case-insensitively)
      since_days — only invoices from the last N days (e.g. 30 for "last month")
      amount     — only invoices for this amount (e.g. 300 for "my $300 charge")
    Read each invoice's description to tell duplicates from normal charges."""
    rows = _WORLD["invoices"].get(customer_id, [])
    if invoice_id is not None:
        rows = [r for r in rows if r["invoice_id"].lower() == invoice_id.strip().lower()]
    if since_days is not None:
        rows = [r for r in rows if (TODAY - date.fromisoformat(r["date"])).days <= since_days]
    if amount is not None:
        rows = [r for r in rows if float(r["amount"]) == float(amount)]
    return sorted(rows, key=lambda r: r["date"], reverse=True)


def check_refund_eligibility(customer_id: str, invoice_id: str) -> dict:
    """Return the refund POLICY that applies to one invoice (not a date calculation):
      - a duplicate charge is ALWAYS eligible (policy "always_eligible")
      - any other charge is eligible only within the refund window (policy "eligible_within_days");
        use check_days_since(invoice_date, window_days) to decide if THIS one still qualifies."""
    for r in _WORLD["invoices"].get(customer_id, []):
        if r["invoice_id"].lower() == invoice_id.strip().lower():
            if "DUPLICATE" in r["description"].upper():
                return {"invoice_id": r["invoice_id"], "policy": "always_eligible",
                        "basis": "duplicate_charge"}
            return {"invoice_id": r["invoice_id"], "policy": "eligible_within_days",
                    "window_days": REFUND_WINDOW, "invoice_date": r["date"]}
    return {"error": f"no invoice {invoice_id} for {customer_id}"}


def get_plan_catalog() -> dict:
    """Return every plan's limits (seats, price per seat, API level + rate limit, SSO, audit logs,
    retention days, priority SLA). Use it to compare plans — e.g. a downgrade target's seat cap, or
    which plan unlocks a feature the customer wants."""
    return _WORLD["plan_rules"]


def get_incident_status(service: str = None, plan: str = None, region: str = None) -> list:
    """Active + recent incidents. Pass the customer's plan and/or region to see only incidents that
    could affect them (an incident lists its affected_plans, and a region or "global").
    Optionally also filter by service (auth-service, api-gateway, export-service)."""
    out = []
    for i in _WORLD["incidents"]:
        if service is not None and i["service"] != service:
            continue
        if plan is not None and plan not in i["affected_plans"]:
            continue
        if region is not None and i["region"] not in ("global", region):
            continue
        out.append(i)
    return out


def check_days_since(date_str: str, threshold_days: int) -> dict:
    """Given a date you read from a record and a threshold, compute how many days ago it was
    (relative to today) and whether it falls within the threshold. Use this instead of doing any
    date arithmetic yourself — you only read the answer."""
    elapsed = (TODAY - date.fromisoformat(date_str)).days
    within = elapsed <= threshold_days
    return {
        "date": date_str,
        "as_of": TODAY.isoformat(),   # the system's current date (a fixed reference clock)
        "days_elapsed": elapsed,
        "within_threshold": within,
        "message": (f"{date_str} was {elapsed} days ago (as of {TODAY.isoformat()}); "
                    f"that is {'within' if within else 'outside'} the {threshold_days}-day threshold."),
    }


# ── Write tools (stubs: log only, no mutation) ────────────────────────────────

def issue_refund(customer_id: str, invoice_id: str, amount: float) -> dict:
    print(f"[ACTION] issue_refund  customer={customer_id} invoice={invoice_id} amount={amount}")
    return {"status": "logged", "customer_id": customer_id, "invoice_id": invoice_id, "amount": amount}


def create_escalation(customer_id: str, team: str, summary: str, priority: str = "medium") -> dict:
    print(f"[ACTION] create_escalation customer={customer_id} team={team} priority={priority}")
    return {"status": "logged", "customer_id": customer_id, "team": team}


# Registry the agent loop dispatches through.
REGISTRY = {
    "get_customer": get_customer,
    "get_subscription": get_subscription,
    "get_invoices": get_invoices,
    "check_refund_eligibility": check_refund_eligibility,
    "get_plan_catalog": get_plan_catalog,
    "get_incident_status": get_incident_status,
    "check_days_since": check_days_since,
    "issue_refund": issue_refund,
    "create_escalation": create_escalation,
}
