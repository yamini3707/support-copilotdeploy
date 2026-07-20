---
doc_id: audit_logs_guide
title: Audit Logs (Enterprise)
category: technical
---

# Audit Logs

Audit logs are an **Enterprise-only** feature. Business, Pro, and Free plans do not include
audit logs; customers on those plans who need them must upgrade to Enterprise.

## Accessing audit logs

Enterprise admins can view audit logs under **Admin → Security → Audit Logs**. Logs capture
sign-ins, permission changes, data exports, API key events, and admin actions. Each entry
records actor, action, target, timestamp, and source IP.

## Exporting audit logs

- **UI export:** filter by date range and click **Export CSV** (up to 90 days per export).
- **API export:** the `GET /v1/audit-logs` endpoint (Enterprise, full API) supports pagination
  and streaming for larger ranges.

## Retention of audit-log data

Audit-log retention follows the Enterprise retention configuration (default 10 years, or your
custom contract term).

## Troubleshooting

- **Menu missing:** confirm the plan is Enterprise and the user has the **Admin** role. Non-admins
  cannot see audit logs.
- **Partial export:** UI exports are capped at 90 days; for longer ranges, use the API or split
  the export into multiple ranges.
- **Export returns an error:** check the status page for an active export-service incident before
  escalating.

If audit logs appear entirely unavailable on a confirmed Enterprise account with an admin user,
and there is no active incident, escalate to the platform team.
