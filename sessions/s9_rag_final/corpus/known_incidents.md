---
doc_id: known_incidents
title: Status Page — Current & Recent Incidents
category: technical
---

# CloudDesk Status — Current & Recent Incidents

This page mirrors live incident status. When a ticket describes symptoms that match an active
incident, reference the incident and advise accordingly instead of treating it as a
customer-side misconfiguration. Always confirm against the live incident tool as well.

## Active incidents

### INC-2041 — SSO (SAML) login failures, EU tenants
- **Service:** auth-service · **Status:** ACTIVE · **Region:** EU
- Some EU tenants cannot complete SAML logins following an upstream certificate rotation.
  Symptoms include "signature invalid" errors. The platform team is deploying a fix.
- **Guidance:** confirm the customer is EU and on Business/Enterprise (SSO plans). If their
  metadata is current and they still fail, this incident is the likely cause — advise that a
  fix is in progress rather than asking them to reconfigure repeatedly. Admins may enable
  temporary password fallback.

### INC-2042 — Elevated API errors (5xx / 429)
- **Service:** api-gateway · **Status:** ACTIVE · **Region:** global
- Business/Enterprise API consumers may see intermittent 5xx responses and stricter throttling.
- **Guidance:** advise retry with exponential backoff. Do not tell customers to rewrite their
  integration; this is server-side and being mitigated.

## Recently resolved

### INC-2039 — Project export timeouts
- **Service:** export-service · **Status:** RESOLVED
- Export jobs were timing out under load; resolved after worker scale-up. New exports should
  succeed. If a customer still reports export failures, treat as a fresh issue (see export
  troubleshooting).
