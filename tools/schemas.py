"""
schemas.py — tool definitions in OpenAI function-calling format.

Kept next to tools.py so a tool and its schema stay in sync. The agent passes TOOL_SCHEMAS to
the model; the model picks which to call.
"""

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_customer",
        "description": "Look up a customer's profile: name, plan, region, seats.",
        "parameters": {"type": "object",
                       "properties": {"customer_id": {"type": "string"}},
                       "required": ["customer_id"]}}},
    {"type": "function", "function": {
        "name": "get_subscription",
        "description": ("Get a customer's subscription: plan, status, renewal_date, seats, and plan_limits. "
                        "Field meanings — status: 'active', or 'past_due'/'canceled' means access may be "
                        "restricted until payment/renewal. plan_limits.retention_days: deleted data is "
                        "recoverable for this many days, after which it is permanently purged and CANNOT be "
                        "restored. plan_limits.sso (bool): whether SSO/SAML is available (false ⇒ needs "
                        "Business or higher). plan_limits.audit_logs (bool): whether audit logs are available "
                        "(false ⇒ needs Enterprise). plan_limits.api: API access level (none/read_only/full). "
                        "plan_limits.api_rate_limit: max API requests per minute. plan_limits.priority_sla "
                        "(bool): priority support."),
        "parameters": {"type": "object",
                       "properties": {"customer_id": {"type": "string"}},
                       "required": ["customer_id"]}}},
    {"type": "function", "function": {
        "name": "get_invoices",
        "description": "List a customer's invoices (id, date, amount, status, description), most recent first. Pass optional filters to narrow to what the customer mentioned. Read each description to tell duplicates from normal charges.",
        "parameters": {"type": "object",
                       "properties": {"customer_id": {"type": "string"},
                                      "invoice_id": {"type": "string", "description": "a specific invoice id, if the customer named one"},
                                      "since_days": {"type": "integer", "description": "only invoices from the last N days (e.g. 30 for 'last month')"},
                                      "amount": {"type": "number", "description": "only invoices for this amount (e.g. 300)"}},
                       "required": ["customer_id"]}}},
    {"type": "function", "function": {
        "name": "check_refund_eligibility",
        "description": "Return the refund POLICY for one invoice: 'always_eligible' for a duplicate charge, or 'eligible_within_days' (with window_days + invoice_date) for a normal charge. For a normal charge, then call check_days_since(invoice_date, window_days) to decide. Does not itself do date math.",
        "parameters": {"type": "object",
                       "properties": {"customer_id": {"type": "string"},
                                      "invoice_id": {"type": "string"}},
                       "required": ["customer_id", "invoice_id"]}}},
    {"type": "function", "function": {
        "name": "get_plan_catalog",
        "description": "Return every plan's limits (seats, price, API, SSO, audit logs, retention, SLA). Use to compare plans — e.g. a downgrade target's seat cap, or which plan unlocks a feature.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_incident_status",
        "description": "List active/recent platform incidents. Pass the customer's plan and region to see only incidents that could affect them (incidents are scoped to certain plan tiers and regions). Optionally filter by service (auth-service, api-gateway, export-service).",
        "parameters": {"type": "object",
                       "properties": {"service": {"type": "string"},
                                      "plan": {"type": "string"},
                                      "region": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "check_days_since",
        "description": "Compute how many days ago a date was (relative to today) and whether it's within a threshold. Use this for any date math (e.g. is an invoice within the 14-day refund window) instead of calculating dates yourself.",
        "parameters": {"type": "object",
                       "properties": {"date_str": {"type": "string", "description": "an ISO date, e.g. 2026-01-29"},
                                      "threshold_days": {"type": "integer"}},
                       "required": ["date_str", "threshold_days"]}}},
    {"type": "function", "function": {
        "name": "issue_refund",
        "description": "Issue a refund for a specific invoice. Only call once you've verified the charge is refundable (a duplicate, or within the 14-day window via check_days_since).",
        "parameters": {"type": "object",
                       "properties": {"customer_id": {"type": "string"},
                                      "invoice_id": {"type": "string"},
                                      "amount": {"type": "number"}},
                       "required": ["customer_id", "invoice_id", "amount"]}}},
    {"type": "function", "function": {
        "name": "create_escalation",
        "description": "Escalate to a human team (billing, privacy, platform, account-recovery) for cases beyond safe self-service.",
        "parameters": {"type": "object",
                       "properties": {"customer_id": {"type": "string"},
                                      "team": {"type": "string"},
                                      "summary": {"type": "string"},
                                      "priority": {"type": "string"}},
                       "required": ["customer_id", "team", "summary"]}}},
]
