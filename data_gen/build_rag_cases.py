"""
build_rag_cases.py — INSTRUCTOR-SIDE. Emits data/rag_cases.json: RAG test cases whose gold-evidence
is engineered to BREAK naive dense retrieval, each tagged with the technique it should force.

Each case: {id, slice, ticket, customer_context, gold_docs, must_mention, answerable}.
  gold_docs  = the doc(s) that truly answer it (for Recall@k — exact retrieval score)
  must_mention = facts the answer must convey (for the semantic/generation score, later)
  answerable = false for null queries (abstention slice)

Run: python3 data_gen/build_rag_cases.py
"""

import json
import os

HERE = os.path.dirname(__file__)
WORLD = json.load(open(os.path.normpath(os.path.join(HERE, "..", "data", "world_state.json"))))
OUT = os.path.normpath(os.path.join(HERE, "..", "data", "rag_cases.json"))
RET = {p: WORLD["plan_rules"][p]["retention_days"] for p in WORLD["plan_rules"]}

cases = []
# a clean, active customer per plan (avoid planted-scenario/memory customers) so the FULL agent can
# establish account context — the technical/billing specialists look the customer up first, and a
# missing/invalid customer_id derails them before they ever reach the KB (see s6 integration).
CUSTOMER_BY_PLAN = {"free": "cust_free_020", "pro": "cust_pro_012",
                    "business": "cust_business_006", "enterprise": "cust_enterprise_000"}

def add(slice_, ticket, plan, gold, must, answerable=True):
    cases.append({
        "id": f"rag_{len(cases):03d}_{slice_}",
        "slice": slice_,
        "ticket": ticket,
        "customer_context": {"customer_id": CUSTOMER_BY_PLAN[plan], "plan": plan},
        "gold_docs": gold,
        "must_mention": must,
        "answerable": answerable,
    })

# ── metadata-filter: plan-agnostic query, gold = the plan-specific variant ────
for plan in ("free", "pro", "business", "enterprise"):
    add("metadata",
        "How long do we have to get a deleted project back before it's gone for good?",
        plan, [f"policy_retention_{plan}"],
        [f"deleted data on the {plan} plan is recoverable for {RET[plan]} days"])

# ── hybrid: ticket quotes an obscure exact token; distractors lack it ─────────
add("hybrid", "Our API calls fail with ERR_SSL_VERSION_OR_CIPHER_MISMATCH. What's wrong?",
    "business", ["ts_ssl_cipher"], ["it is a TLS version/cipher issue; upgrade the client to TLS 1.2+"])
add("hybrid", "Webhooks stopped arriving — our logs show WEBHOOK_RETRY_EXHAUSTED.",
    "business", ["ts_webhook_retry"], ["retries are exhausted after repeated non-2xx responses; the endpoint must return 200"])
add("hybrid", "Every export dies with EXPORT_TIMEOUT. Help.",
    "pro", ["ts_export_timeout"], ["large exports can time out; split by project or date range, or stream via the API"])
add("hybrid", "Is INC-2041 fixed yet? Our EU logins were failing.",
    "enterprise", ["postmortem_inc2041"], ["INC-2041 concerned EU SSO login failures after a certificate rotation"])
add("hybrid", "Which plan gives exactly 6000 API requests per minute?",
    "business", ["policy_features_enterprise"], ["the Enterprise plan allows 6000 API requests per minute"])

# ── rerank: distractor-dense topic; gold present but out-ranked (score at k=3) ─
add("rerank", "What is your refund policy?", "pro", ["refund_policy"],
    ["refunds can be requested within 14 days of the charge"])
add("rerank", "How does getting money back for a charge work here?", "business", ["refund_policy"],
    ["refunds can be requested within 14 days of the charge"])
add("rerank", "Remind me of the rules for returning a payment.", "pro", ["refund_policy"],
    ["refunds can be requested within 14 days of the charge"])

# ── HyDE / query-rewrite: lay wording, answer only in a technical doc ─────────
add("hyde", "Can we make it so our old stuff automatically disappears after a set time?",
    "business", ["data_retention_policy"], ["data is retained per the plan's window, then permanently purged"])
add("hyde", "Is the information we keep with you safe and private?",
    "business", ["security_and_compliance"], ["data is encrypted in transit and at rest, and CloudDesk is SOC 2 compliant"])
add("hyde", "Can we see a record of who changed what in our workspace?",
    "enterprise", ["audit_logs_guide"], ["audit logs record who did what and are available on the Enterprise plan"])

# ── cross-plan: the question is about a DIFFERENT plan than the customer's, so blindly
#    filtering by the customer's plan would REMOVE the answer. The agent must choose NOT to filter
#    (or to filter to the plan actually asked about). ─────────────────────────
add("cross_plan", "Does the Business plan include audit logs?", "pro", ["policy_features_business"],
    ["audit logs are not included on Business; they are Enterprise-only"])
add("cross_plan", "How many API requests per minute does Enterprise allow?", "pro", ["policy_features_enterprise"],
    ["the Enterprise plan allows 6000 API requests per minute"])
add("cross_plan", "Is SSO available on the Business plan?", "free", ["policy_features_business"],
    ["SSO is available on the Business plan"])

# ── abstention: no doc answers this; the agent must NOT fabricate ─────────────
for q in ("Do you have a mobile app for iPhone?",
          "What are your phone support hours?",
          "Can I pay with cryptocurrency?",
          "Do you offer an on-premise / self-hosted version?"):
    add("abstention", q, "business", [], [], answerable=False)

json.dump(cases, open(OUT, "w"), indent=2)
from collections import Counter
print(f"Wrote {OUT}  ({len(cases)} cases)")
print("  by slice:", dict(Counter(c["slice"] for c in cases)))
