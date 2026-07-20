"""
build_corpus.py — INSTRUCTOR-SIDE. Grows the KB into a messy, retrieval-hard corpus.

Two producers (the "hybrid" generation we agreed on):
  - FACT docs: templated from world_state.json (per-tier policies) → deterministic, consistent.
  - PROSE docs: LLM-written (troubleshooting, FAQ, distractors, handbook) → realistic, varied.
    LLM outputs are cached on disk (data_gen/.corpus_cache/) keyed by a hash of the prompt, so
    re-runs are free/instant/reproducible and work offline once built.

Writes new .md files into kb/ (never touches the 12 hand-written canonical docs) and a manifest
kb/_manifest.json with metadata {doc_id, title, doc_type, plan, version, date} for EVERY doc.

    python3 data_gen/build_corpus.py            # generate the sample set (default)
    python3 data_gen/build_corpus.py --full     # generate the full ~80-doc corpus
"""

import glob
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(__file__)
KB = os.path.normpath(os.path.join(HERE, "..", "kb"))
WORLD = json.load(open(os.path.normpath(os.path.join(HERE, "..", "data", "world_state.json"))))
CACHE = os.path.join(HERE, ".corpus_cache")
os.makedirs(CACHE, exist_ok=True)
TODAY = WORLD["_meta"]["today"]
PLAN_RULES = WORLD["plan_rules"]

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.normpath(os.path.join(HERE, "..", ".env")))
except ImportError:
    pass


# ── LLM with disk cache ───────────────────────────────────────────────────────
def llm(prompt: str) -> str:
    key = hashlib.sha1(prompt.encode()).hexdigest()[:16]
    path = os.path.join(CACHE, key + ".txt")
    if os.path.exists(path):
        return open(path).read()
    from openai import OpenAI
    resp = OpenAI().chat.completions.create(
        model=os.getenv("SUPPORT_COPILOT_MODEL", "gpt-4o-mini"), temperature=0.4,
        messages=[{"role": "user", "content": prompt}])
    text = resp.choices[0].message.content.strip()
    open(path, "w").write(text)
    return text


def write_doc(doc_id, title, doc_type, plan, body, version="v1"):
    fm = (f"---\ndoc_id: {doc_id}\ntitle: {title}\ndoc_type: {doc_type}\n"
          f"plan: {plan}\nversion: {version}\ndate: {TODAY}\n---\n\n")
    open(os.path.join(KB, doc_id + ".md"), "w").write(fm + body.strip() + "\n")
    return {"doc_id": doc_id, "title": title, "doc_type": doc_type, "plan": plan,
            "version": version, "date": TODAY}


# ── FACT docs (templated from world_state) ────────────────────────────────────
def fact_docs():
    made = []
    # per-tier retention policy — the metadata-filter trap (same topic, right answer differs by plan)
    for plan, r in PLAN_RULES.items():
        days = r["retention_days"]
        body = (f"# Data Retention — {plan.title()} Plan\n\n"
                f"On the **{plan.title()}** plan, deleted projects, docs, and activity data are "
                f"recoverable for **{days} days** from deletion. After {days} days the data is "
                f"permanently purged and cannot be restored. To retain data longer, upgrade to a "
                f"plan with a longer retention window or export before deleting.")
        made.append(write_doc(f"policy_retention_{plan}", f"Data Retention — {plan.title()}",
                              "policy", plan, body))
    # refund window by billing cycle — near-duplicate variant trap
    for cycle, days in (("monthly", 14), ("annual", 30)):
        body = (f"# Refund Policy — {cycle.title()} Billing\n\n"
                f"Customers on **{cycle}** billing may request a refund within **{days} days** of a "
                f"charge. Requests after the {days}-day window are not eligible except where required "
                f"by law. Duplicate charges are always refundable once verified.")
        made.append(write_doc(f"policy_refund_{cycle}", f"Refund Policy — {cycle.title()}",
                              "policy", "all", body))
    # per-plan feature sheet — aggregation/GraphRAG surface + metadata
    for plan, r in PLAN_RULES.items():
        body = (f"# {plan.title()} Plan — Feature Sheet\n\n"
                f"- Seats: {r['seats']}\n- API access: {r['api']} ({r['api_rate_limit']}/min)\n"
                f"- SSO (SAML/OIDC): {'yes' if r['sso'] else 'no'}\n"
                f"- Audit logs: {'yes' if r['audit_logs'] else 'no'}\n"
                f"- Data retention: {r['retention_days']} days\n"
                f"- Priority support SLA: {'yes' if r['priority_sla'] else 'no'}")
        made.append(write_doc(f"policy_features_{plan}", f"{plan.title()} Feature Sheet",
                              "policy", plan, body))
    return made


# ── PROSE docs (LLM, cached) ──────────────────────────────────────────────────
# Each spec: doc_id, title, doc_type, plan, and a prompt that plants the intended trap.
SAMPLE_PROSE = [
    dict(doc_id="ts_api_429", title="Resolving HTTP 429 (Too Many Requests)", doc_type="troubleshooting", plan="all",
         prompt="Write a ~180-word CloudDesk support troubleshooting article titled 'Resolving HTTP 429 "
                "(Too Many Requests)'. It MUST use the exact strings '429' and 'Retry-After'. Explain that "
                "429 means the plan's API rate limit was exceeded, to respect the Retry-After header and back "
                "off exponentially, and that steady 429s mean you need a higher plan. Plain markdown, no preamble."),
    dict(doc_id="ts_sso_cert_rotation", title="SAML login fails after certificate rotation", doc_type="troubleshooting", plan="all",
         prompt="Write a ~180-word CloudDesk troubleshooting article titled 'SAML login fails after certificate "
                "rotation'. MUST include the exact phrase 'signature invalid'. Explain that after an IdP rotates "
                "its signing certificate, CloudDesk validates against the old cert until you re-upload the IdP "
                "metadata, then clear the SSO cache and re-test. Plain markdown, no preamble."),
    dict(doc_id="faq_login_google", title="Why can't I sign in with my company Google account?", doc_type="faq", plan="all",
         prompt="Write a ~120-word CloudDesk FAQ entry in PLAIN, non-technical customer language titled 'Why "
                "can't I sign in with my company Google account?'. Do NOT use the words SAML, SSO, OIDC, or IdP. "
                "Describe that company-wide single sign-in (logging in through your company's Google/Microsoft "
                "account) is available on higher plans and set up by an admin. Plain markdown, no preamble."),
    dict(doc_id="dist_refund_credits", title="Understanding account credits", doc_type="faq", plan="all",
         prompt="Write a ~150-word CloudDesk help article titled 'Understanding account credits'. It is a "
                "DISTRACTOR: it must be about proration, account credits, and downgrades — topically adjacent to "
                "refunds — but must NOT mention the refund window, the number of days, or refund eligibility "
                "rules. Plain markdown, no preamble."),
    dict(doc_id="dist_billing_taxes", title="Taxes and VAT on your invoices", doc_type="faq", plan="all",
         prompt="Write a ~150-word CloudDesk help article titled 'Taxes and VAT on your invoices'. DISTRACTOR: "
                "about tax, VAT, and invoice line items — near billing/refund topics — but must NOT mention "
                "refunds, the refund window, or eligibility. Plain markdown, no preamble."),
    dict(doc_id="handbook_billing", title="CloudDesk Billing Handbook", doc_type="handbook", plan="all",
         prompt="Write a ~600-word CloudDesk 'Billing Handbook' with multiple ## sections: Invoices, Payment "
                "methods, Proration, Dunning & past-due, Plan changes, and Refunds. In the Refunds section (and "
                "only there, buried mid-document) state that the standard refund window is 14 days from the "
                "charge date. Use section headers and refer back with phrases like 'as noted above' and 'on this "
                "plan'. Plain markdown, no preamble."),
]


# More exact-token troubleshooting articles (hybrid/BM25 traps) — each buries a literal string.
FULL_TROUBLESHOOTING = [
    dict(doc_id="ts_api_5xx", title="Intermittent 5xx errors on the API", doc_type="troubleshooting", plan="all",
         prompt="~170-word CloudDesk troubleshooting article 'Intermittent 5xx errors on the API'. MUST include "
                "the exact strings '500', '502', and '503'. Explain these are server-side, to retry with backoff, "
                "and to check the status page for an active api-gateway incident before changing your integration. "
                "Plain markdown, no preamble."),
    dict(doc_id="ts_export_timeout", title="Export job times out with EXPORT_TIMEOUT", doc_type="troubleshooting", plan="all",
         prompt="~170-word CloudDesk troubleshooting article 'Export job times out with EXPORT_TIMEOUT'. MUST include "
                "the exact string 'EXPORT_TIMEOUT'. Explain large exports can time out, split by project or date "
                "range, or use the API to stream. Plain markdown, no preamble."),
    dict(doc_id="ts_audit_empty", title="Audit Logs page is blank", doc_type="troubleshooting", plan="enterprise",
         prompt="~170-word CloudDesk troubleshooting article 'Audit Logs page is blank'. MUST include the exact "
                "phrase 'Admin → Security' and mention confirming the user has the Admin role. Note audit logs are "
                "Enterprise-only. Plain markdown, no preamble."),
    dict(doc_id="ts_login_locked", title="Account locked after failed sign-in attempts", doc_type="troubleshooting", plan="all",
         prompt="~160-word CloudDesk troubleshooting article 'Account locked after failed sign-in attempts'. MUST "
                "state accounts lock after 10 failed attempts and auto-unlock after 30 minutes; an admin can unlock "
                "sooner. Plain markdown, no preamble."),
    dict(doc_id="ts_api_403", title="API write requests return 403 Forbidden", doc_type="troubleshooting", plan="all",
         prompt="~160-word CloudDesk troubleshooting article 'API write requests return 403 Forbidden'. MUST include "
                "the exact string '403'. Explain that a read-only API plan (Pro) blocks writes; full read+write API "
                "requires Business or higher. Plain markdown, no preamble."),
    dict(doc_id="ts_ssl_cipher", title="ERR_SSL_VERSION_OR_CIPHER_MISMATCH when calling the API", doc_type="troubleshooting", plan="all",
         prompt="~150-word CloudDesk troubleshooting article titled 'ERR_SSL_VERSION_OR_CIPHER_MISMATCH when calling "
                "the API'. MUST include that exact error string. Explain it's a TLS version/cipher issue on the "
                "client; upgrade to TLS 1.2+. Plain markdown, no preamble."),
    dict(doc_id="ts_webhook_retry", title="Webhooks not delivered (WEBHOOK_RETRY_EXHAUSTED)", doc_type="troubleshooting", plan="all",
         prompt="~150-word CloudDesk troubleshooting article 'Webhooks not delivered (WEBHOOK_RETRY_EXHAUSTED)'. MUST "
                "include the exact string 'WEBHOOK_RETRY_EXHAUSTED'. Explain retries exhaust after repeated non-2xx "
                "responses; check your endpoint returns 200. Plain markdown, no preamble."),
    dict(doc_id="ts_mfa_lost", title="Lost MFA device — regaining access", doc_type="troubleshooting", plan="all",
         prompt="~160-word CloudDesk troubleshooting article 'Lost MFA device — regaining access'. Explain an admin "
                "resets a member's MFA under Admin → Members; if the only admin is locked out, identity must be "
                "verified and it is escalated to account recovery. Plain markdown, no preamble."),
]

# Lay-vocabulary FAQs (query-rewrite / HyDE traps) — customer words, not our jargon.
FULL_FAQ = [
    dict(doc_id="faq_cancel", title="How do I stop my subscription?", doc_type="faq", plan="all",
         prompt="~110-word CloudDesk FAQ 'How do I stop my subscription?' in plain customer language (avoid the word "
                "'cancellation'). Explain stopping future renewals, access until period end. Plain markdown, no preamble."),
    dict(doc_id="faq_receipt", title="Where do I get a receipt for accounting?", doc_type="faq", plan="all",
         prompt="~110-word CloudDesk FAQ 'Where do I get a receipt for accounting?' in plain language (avoid the word "
                "'invoice' in the title's spirit). Explain receipts/invoices are under Admin then Billing. Plain markdown, no preamble."),
    dict(doc_id="faq_get_data_back", title="Can I get back a project I deleted?", doc_type="faq", plan="all",
         prompt="~110-word CloudDesk FAQ 'Can I get back a project I deleted?' in plain language (avoid the word "
                "'retention'). Explain deleted items are recoverable for a limited window that depends on your plan, "
                "then permanently gone. Plain markdown, no preamble."),
    dict(doc_id="faq_double_billed", title="I think you billed me twice", doc_type="faq", plan="all",
         prompt="~110-word CloudDesk FAQ 'I think you billed me twice' in plain language (avoid the word 'duplicate'). "
                "Explain to check charges under billing and that support verifies before refunding. Plain markdown, no preamble."),
    dict(doc_id="faq_new_teammate", title="Adding someone to our team", doc_type="faq", plan="all",
         prompt="~100-word CloudDesk FAQ 'Adding someone to our team' in plain language (avoid the word 'seat'). "
                "Explain an admin invites members under Admin then Members. Plain markdown, no preamble."),
    dict(doc_id="faq_app_slow", title="The app is really slow today", doc_type="faq", plan="all",
         prompt="~100-word CloudDesk FAQ 'The app is really slow today'. General advice: check the status page for "
                "incidents, try a refresh. Plain markdown, no preamble."),
]

FULL_HANDBOOKS = [
    dict(doc_id="handbook_admin", title="CloudDesk Admin Guide", doc_type="handbook", plan="all",
         prompt="~600-word CloudDesk 'Admin Guide' with ## sections: Members & seats, Roles & permissions, "
                "Single sign-on, Multi-factor authentication, Audit logs, Plan changes. In the SSO section (buried) "
                "state SSO requires the Business plan or higher; in the Audit logs section state audit logs are "
                "Enterprise-only and found under Admin → Security. Use back-references like 'as covered above'. "
                "Plain markdown, no preamble."),
    dict(doc_id="handbook_api", title="CloudDesk API Guide", doc_type="handbook", plan="all",
         prompt="~550-word CloudDesk 'API Guide' with ## sections: Authentication, Rate limits, Pagination, "
                "Webhooks, Errors. In Rate limits (buried) state Pro=60/min, Business=600/min, Enterprise=6000/min "
                "and that exceeding returns 429 with Retry-After. Plain markdown, no preamble."),
]

FULL_INCIDENT_DOCS = [
    dict(doc_id="postmortem_inc2041", title="Postmortem: INC-2041 SSO login failures (EU)", doc_type="postmortem", plan="all",
         prompt="~200-word CloudDesk postmortem for 'INC-2041': SSO (SAML) login failures for some EU tenants after "
                "an upstream certificate rotation. MUST include 'INC-2041'. Sections: Impact, Root cause, Resolution, "
                "Prevention. Plain markdown, no preamble."),
    dict(doc_id="postmortem_inc2042", title="Postmortem: INC-2042 elevated API 5xx/429", doc_type="postmortem", plan="all",
         prompt="~200-word CloudDesk postmortem for 'INC-2042': elevated 5xx and 429s on the public API for "
                "Business/Enterprise tiers. MUST include 'INC-2042'. Sections: Impact, Root cause, Resolution, "
                "Prevention. Plain markdown, no preamble."),
    dict(doc_id="release_notes_2026_03", title="Release notes — March 2026", doc_type="release_note", plan="all",
         prompt="~180-word CloudDesk 'Release notes — March 2026': a few realistic feature/fix bullets (exports, "
                "API, admin). Plain markdown, no preamble."),
    dict(doc_id="release_notes_2026_02", title="Release notes — February 2026", doc_type="release_note", plan="all",
         prompt="~180-word CloudDesk 'Release notes — February 2026': a few realistic feature/fix bullets. Plain "
                "markdown, no preamble."),
]

# Distractor clusters — topically-adjacent siblings that must NOT contain policy specifics.
# These are the volume that makes naive top-k / rerank necessary.
DISTRACTOR_CLUSTERS = {
    "refunds": ["How proration works when you upgrade", "Understanding your billing cycle",
                "Updating your payment method", "Reading your invoice line items",
                "Switching between monthly and annual billing"],
    "login": ["Password best practices", "Clearing browser cookies for sign-in issues",
              "How session timeouts work", "Trusting a device for faster sign-in",
              "Signing in on mobile"],
    "billing": ["How seat-based pricing works", "Purchase orders and procurement",
                "Setting spending alerts", "How usage is metered", "Managing multiple workspaces' billing"],
    "api": ["Getting started with API keys", "Paginating large API responses",
            "Choosing an SDK or client library", "Sandbox vs production environments",
            "API changelog and versioning"],
    "exports": ["Supported export formats", "Scheduling recurring exports",
                "Importing data into CloudDesk", "Archiving old projects", "Data residency overview"],
    "account": ["Setting up your profile", "Notification preferences",
                "Renaming your workspace", "Inviting external guests", "Deactivating a member"],
}


# Same-topic distractors that LACK the exact error strings — these push the exact-code
# troubleshooting docs down in pure-dense results, so hybrid (BM25) becomes necessary.
HYBRID_DISTRACTORS = [
    dict(doc_id="dist_api_error_categories", title="Common API error categories", doc_type="faq", plan="all",
         prompt="~150-word CloudDesk help article 'Common API error categories'. Explain 4xx vs 5xx in GENERAL "
                "terms (client vs server), retries, and reading error responses. DISTRACTOR: do NOT include any "
                "specific error code, status number, or literal error string. Plain markdown, no preamble."),
    dict(doc_id="dist_tls_overview", title="How CloudDesk secures API connections", doc_type="faq", plan="all",
         prompt="~150-word CloudDesk help article 'How CloudDesk secures API connections'. General overview of "
                "TLS/encryption for API calls. DISTRACTOR: do NOT include any literal error string or error code. "
                "Plain markdown, no preamble."),
    dict(doc_id="dist_webhooks_overview", title="An overview of CloudDesk webhooks", doc_type="faq", plan="all",
         prompt="~150-word CloudDesk help article 'An overview of CloudDesk webhooks'. General intro to webhooks, "
                "events, endpoints. DISTRACTOR: do NOT include any literal error code or error string. Plain "
                "markdown, no preamble."),
    dict(doc_id="dist_export_basics", title="About exporting your data", doc_type="faq", plan="all",
         prompt="~150-word CloudDesk help article 'About exporting your data'. General overview of exporting "
                "projects/docs. DISTRACTOR: do NOT include any literal error code or error string. Plain markdown, "
                "no preamble."),
]


def distractor_specs():
    specs = []
    for topic, angles in DISTRACTOR_CLUSTERS.items():
        for i, angle in enumerate(angles):
            specs.append(dict(
                doc_id=f"dist_{topic}_{i}", title=angle, doc_type="faq", plan="all",
                prompt=f"Write a ~130-word CloudDesk help article titled '{angle}'. Write genuinely about this "
                       f"sub-topic, but it is a DISTRACTOR: do NOT state any specific policy numbers — no refund "
                       f"window or day-counts, no eligibility rules, no exact rate limits, no retention day-counts. "
                       f"Keep it general and adjacent. Plain markdown, no preamble."))
    return specs


def prose_docs(specs):
    return [write_doc(s["doc_id"], s["title"], s["doc_type"], s["plan"], llm(s["prompt"])) for s in specs]


# ── Manifest (metadata for ALL docs, incl. the 12 canonical) ──────────────────
def manifest_for_existing(new_ids):
    """The 12 hand-written docs: infer metadata (plan=all, doc_type=policy)."""
    rows = []
    for f in sorted(glob.glob(os.path.join(KB, "*.md"))):
        txt = open(f).read()
        did = re.search(r"doc_id:\s*(\S+)", txt)
        did = did.group(1) if did else os.path.splitext(os.path.basename(f))[0]
        if did in new_ids:
            continue
        title = re.search(r"title:\s*(.+)", txt)
        rows.append({"doc_id": did, "title": title.group(1).strip() if title else did,
                     "doc_type": "policy", "plan": "all", "version": "v1", "date": TODAY})
    return rows


def main():
    full = "--full" in sys.argv
    made = fact_docs()
    if full:
        specs = (SAMPLE_PROSE + FULL_TROUBLESHOOTING + FULL_FAQ + FULL_HANDBOOKS
                 + FULL_INCIDENT_DOCS + HYBRID_DISTRACTORS + distractor_specs())
    else:
        specs = SAMPLE_PROSE
    made += prose_docs(specs)
    new_ids = {m["doc_id"] for m in made}
    all_rows = made + manifest_for_existing(new_ids)
    json.dump(sorted(all_rows, key=lambda r: r["doc_id"]),
              open(os.path.join(KB, "_manifest.json"), "w"), indent=2)

    from collections import Counter
    print(f"Generated {len(made)} new docs ({'FULL' if full else 'SAMPLE'}). Corpus total: {len(all_rows)} docs.")
    print("  by doc_type:", dict(Counter(r["doc_type"] for r in all_rows)))
    print("  by plan    :", dict(Counter(r["plan"] for r in all_rows)))
    print("  new doc_ids:", sorted(new_ids))


if __name__ == "__main__":
    main()
