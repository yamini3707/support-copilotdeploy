"""
build_world_state.py  —  INSTRUCTOR-SIDE (withheld from students)

Emits data/world_state.json, the single source of truth for the CloudDesk Support Copilot.
Every mock tool reads from this file; every deterministic dataset label is derived from it.
So consistency here == a trustworthy eval. Seeded → reproducible.

Design intent (see PROJECT_DESIGN.md §1, §7, §9):
  - customers span all 4 plans / regions / locales so plan-gating cases exist
  - invoices deliberately plant traps: double-charges, in-window vs expired refunds
  - incidents tie to SSO / API / export so technical cases have a real "check status" truth
  - ticket_history seeds the memory slice (returning customers, language preference)

Run:  python3 data_gen/build_world_state.py
"""

import json
import os
import random
from datetime import date, timedelta

SEED = 7
random.seed(SEED)

# "Today" is frozen so refund-window math is deterministic forever.
TODAY = date(2026, 3, 15)
REFUND_WINDOW_DAYS = 14

# ── Plan rules (the PROJECT_DESIGN.md §1 table, machine-readable) ──────────────

PLAN_RULES = {
    "free":       {"price_per_seat": 0,  "seats": 3,   "api": "none",      "api_rate_limit": 0,    "sso": False, "audit_logs": False, "retention_days": 30,   "priority_sla": False},
    "pro":        {"price_per_seat": 12, "seats": 25,  "api": "read_only", "api_rate_limit": 60,   "sso": False, "audit_logs": False, "retention_days": 365,  "priority_sla": False},
    "business":   {"price_per_seat": 28, "seats": 100, "api": "full",      "api_rate_limit": 600,  "sso": True,  "audit_logs": False, "retention_days": 1095, "priority_sla": True},
    "enterprise": {"price_per_seat": 45, "seats": 9999,"api": "full",      "api_rate_limit": 6000, "sso": True,  "audit_logs": True,  "retention_days": 3650, "priority_sla": True},
}

REGIONS = ["US", "EU", "APAC"]
LOCALES = ["en", "es", "de", "fr"]

COMPANY_NAMES = [
    "Meridian Analytics", "Quantum Financial", "Northwind Labs", "Acme Robotics",
    "Cobalt Health", "Vertex Media", "Solaris Energy", "Ironclad Legal",
    "BlueOrbit Games", "Trailhead Outdoors", "Pixel Forge", "Harbor Logistics",
    "Cedar Bank", "Nimbus Cloudworks", "Atlas Freight", "Willow Education",
    "Redwood Ventures", "Summit Retail", "Orbit Telecom", "Fjord Design",
    "Lumen Diagnostics", "Copperline Mfg", "Delta Aerospace", "Sable Consulting",
]

SERVICES = ["auth-service", "api-gateway", "export-service", "billing-service", "docs-service"]

# ── Builders ──────────────────────────────────────────────────────────────────

def _d(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


def build_customers() -> list[dict]:
    """~24 customers, plan mix weighted so every gating slice has subjects."""
    # deliberate plan distribution: enough enterprise (audit/SSO/API), plenty pro (gating "no SSO")
    plan_plan = (
        ["enterprise"] * 6 + ["business"] * 6 + ["pro"] * 8 + ["free"] * 4
    )
    customers = []
    for i, (name, plan) in enumerate(zip(COMPANY_NAMES, plan_plan)):
        rules = PLAN_RULES[plan]
        region = REGIONS[i % len(REGIONS)]
        # A few non-English locales for variety. NOTE: the memory customer (idx 2) is kept "en"
        # on purpose — their Spanish preference must live ONLY in ticket_history, so the
        # memory-gated cases can't be solved by reading a locale field.
        locale = "es" if i == 11 else ("de" if i == 7 else ("fr" if i == 18 else "en"))
        seats_used = min(rules["seats"], random.randint(2, min(rules["seats"], 60)))
        customers.append({
            "customer_id": f"cust_{plan}_{i:03d}",
            "name": name,
            "plan": plan,
            "region": region,
            "locale": locale,
            "signup_date": _d(random.randint(40, 900)),
            "seats_purchased": rules["seats"] if plan != "enterprise" else seats_used + 20,
            "seats_used": seats_used,
        })
    return customers


def build_subscriptions(customers: list[dict]) -> dict:
    subs = {}
    for c in customers:
        rules = PLAN_RULES[c["plan"]]
        mrr = rules["price_per_seat"] * c["seats_purchased"]
        subs[c["customer_id"]] = {
            "plan": c["plan"],
            "status": "active",
            "renewal_date": _d(-random.randint(5, 60)),  # future
            "mrr": mrr,
            "seats_used": c["seats_used"],
            "seats_purchased": c["seats_purchased"],
        }
    # plant one past_due (dunning) and one canceled for account/billing cases
    subs[customers[9]["customer_id"]]["status"] = "past_due"
    subs[customers[15]["customer_id"]]["status"] = "canceled"
    subs[customers[15]["customer_id"]]["renewal_date"] = _d(3)  # canceled recently
    return subs


def build_invoices(customers: list[dict], subs: dict) -> dict:
    """
    Plant refund/billing traps:
      - DOUBLE CHARGE (financial harm, refund eligible if recent): a few customers
      - RECENT single charge within refund window (eligible)
      - OLD charge outside window (INELIGIBLE — the issue_refund trap)
    """
    invoices = {}
    for idx, c in enumerate(customers):
        cid = c["customer_id"]
        sub = subs[cid]
        base_amt = float(sub["mrr"]) if sub["mrr"] else 0.0
        rows = []
        # a normal older invoice (out of window)
        rows.append({
            "invoice_id": f"inv_{idx:03d}_a",
            "date": _d(45),
            "amount": base_amt,
            "status": "paid",
            "description": "Monthly subscription",
        })
        # a recent invoice inside the refund window
        rows.append({
            "invoice_id": f"inv_{idx:03d}_b",
            "date": _d(6),
            "amount": base_amt,
            "status": "paid",
            "description": "Monthly subscription",
        })
        invoices[cid] = rows

    # DOUBLE CHARGES (duplicate of inv _b, same recent date) → billing, financial harm
    for idx in (0, 3, 8, 12):
        cid = customers[idx]["customer_id"]
        dup = dict(invoices[cid][1])
        dup["invoice_id"] = f"inv_{idx:03d}_dup"
        dup["description"] = "Monthly subscription (DUPLICATE CHARGE)"
        invoices[cid].append(dup)

    # EXPIRED-WINDOW recent-looking charge (30 days ago) for the ineligible-refund trap
    for idx in (5, 14):
        cid = customers[idx]["customer_id"]
        invoices[cid].append({
            "invoice_id": f"inv_{idx:03d}_old",
            "date": _d(30),
            "amount": float(subs[cid]["mrr"]),
            "status": "paid",
            "description": "Monthly subscription",
        })

    # OLD DUPLICATE (duplicate charge, but 40 days ago — outside the window).
    # Tricky edge case: duplicates are ALWAYS refundable, so the window must NOT be applied here.
    for idx in (6,):
        cid = customers[idx]["customer_id"]
        invoices[cid].append({
            "invoice_id": f"inv_{idx:03d}_dupold",
            "date": _d(40),
            "amount": float(subs[cid]["mrr"]),
            "status": "paid",
            "description": "Monthly subscription (DUPLICATE CHARGE)",
        })

    # ALREADY-REFUNDED invoice (status 'refunded') — idempotency trap: don't refund it twice.
    for idx in (18,):
        cid = customers[idx]["customer_id"]
        invoices[cid].append({
            "invoice_id": f"inv_{idx:03d}_ref",
            "date": _d(5),
            "amount": float(subs[cid]["mrr"]),
            "status": "refunded",
            "description": "Monthly subscription (refunded on request)",
        })
    return invoices


def build_incidents() -> list[dict]:
    """Active + recent incidents. `region` and `affected_plans` are structured so an agent can
    match an incident to a customer's context (an incident only affects certain regions/tiers)."""
    return [
        {"id": "INC-2041", "service": "auth-service", "status": "active",
         "started": _d(0), "region": "EU", "affected_plans": ["business", "enterprise"],
         "summary": "SSO (SAML) logins failing for some EU tenants after certificate rotation."},
        {"id": "INC-2042", "service": "api-gateway", "status": "active",
         "started": _d(0), "region": "global", "affected_plans": ["business", "enterprise"],
         "summary": "Elevated 5xx and 429s on public API for Business/Enterprise tiers."},
        {"id": "INC-2039", "service": "export-service", "status": "resolved",
         "started": _d(2), "region": "global", "affected_plans": ["free", "pro", "business", "enterprise"],
         "summary": "Project export jobs timing out; resolved after worker scale-up."},
    ]


def build_ticket_history(customers: list[dict]) -> dict:
    """Seeds the MEMORY slice: returning customers, language preference, prior unresolved."""
    history = {}
    # Spanish-preferring returning customer (locale es, idx 2)
    cid = customers[2]["customer_id"]
    history[cid] = [
        {"ticket_id": "t_5501", "date": _d(60), "category": "billing",
         "summary": "Asked about annual billing discount. Prefers replies in Spanish.",
         "resolved": True, "note": "language_pref=es"},
        {"ticket_id": "t_5502", "date": _d(20), "category": "technical",
         "summary": "Audit log export returned partial data. Left UNRESOLVED, promised follow-up.",
         "resolved": False},
    ]
    # returning customer with a prior SSO ticket (idx 0, enterprise)
    cid = customers[0]["customer_id"]
    history[cid] = [
        {"ticket_id": "t_5601", "date": _d(15), "category": "technical",
         "summary": "SSO misconfiguration during onboarding; resolved by re-uploading metadata.",
         "resolved": True},
    ]
    # a customer who previously abused/injected (idx 8) — for guardrail context
    cid = customers[8]["customer_id"]
    history[cid] = [
        {"ticket_id": "t_5701", "date": _d(9), "category": "billing",
         "summary": "Requested refund outside policy window; declined per policy.",
         "resolved": True},
    ]
    return history


def plant_seat_scenarios(customers, subs):
    """Set explicit seat counts for the field-comparison (Theme A) cases: (seats_used, seats_purchased)."""
    scenarios = {
        "cust_pro_019": (25, 25),        # maxed out at Pro's 25-seat cap  → "can't add a teammate"
        "cust_business_007": (40, 100),  # 40 seats in use → downgrading to Pro (cap 25) is blocked
        "cust_business_010": (5, 100),   # paying for 100 seats, using only 5 → over-provisioned
    }
    by_id = {c["customer_id"]: c for c in customers}
    for cid, (used, purchased) in scenarios.items():
        plan = subs[cid]["plan"]
        subs[cid]["seats_used"] = used
        subs[cid]["seats_purchased"] = purchased
        subs[cid]["mrr"] = PLAN_RULES[plan]["price_per_seat"] * purchased
        by_id[cid]["seats_used"] = used
        by_id[cid]["seats_purchased"] = purchased


def main():
    customers = build_customers()
    subs = build_subscriptions(customers)
    plant_seat_scenarios(customers, subs)
    invoices = build_invoices(customers, subs)
    incidents = build_incidents()
    history = build_ticket_history(customers)

    world = {
        "_meta": {
            "generated_by": "data_gen/build_world_state.py",
            "seed": SEED,
            "today": TODAY.isoformat(),
            "refund_window_days": REFUND_WINDOW_DAYS,
            "note": "Single source of truth. Tools and deterministic labels derive from this.",
        },
        "plan_rules": PLAN_RULES,
        "services": SERVICES,
        "customers": customers,
        "subscriptions": subs,
        "invoices": invoices,
        "incidents": incidents,
        "ticket_history": history,
    }

    out = os.path.join(os.path.dirname(__file__), "..", "data", "world_state.json")
    out = os.path.normpath(out)
    with open(out, "w") as f:
        json.dump(world, f, indent=2)

    # quick self-report
    n_dup = sum(1 for cid in invoices for r in invoices[cid] if "DUPLICATE" in r["description"])
    print(f"Wrote {out}")
    print(f"  customers={len(customers)}  invoices_rows={sum(len(v) for v in invoices.values())}")
    print(f"  double-charge rows={n_dup}  active_incidents={sum(1 for i in incidents if i['status']=='active')}")
    print(f"  memory-history customers={len(history)}")
    plan_counts = {}
    for c in customers:
        plan_counts[c["plan"]] = plan_counts.get(c["plan"], 0) + 1
    print(f"  plan mix={plan_counts}")


if __name__ == "__main__":
    main()
