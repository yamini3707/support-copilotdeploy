---
doc_id: api_access_and_limits
title: API Access & Rate Limits
category: technical
---

# API Access & Rate Limits

## Availability by plan

- **Free:** no API access.
- **Pro:** **read-only** API. Write endpoints return `403 Forbidden`.
- **Business:** full read + write API.
- **Enterprise:** full read + write API.

## Rate limits

Rate limits are per organization, per minute:

| Plan | Limit |
|---|---|
| Pro | 60 requests/min |
| Business | 600 requests/min |
| Enterprise | 6000 requests/min |

When you exceed the limit, the API returns **HTTP 429 Too Many Requests** with a
`Retry-After` header (in seconds). This is expected behavior, not an outage.

## Handling 429s

- Respect the `Retry-After` header and back off exponentially.
- Batch requests where possible; use bulk endpoints instead of per-item calls.
- If you consistently hit the limit at normal volume, you likely need a higher tier.

## Authentication

Generate API keys under **Admin → Developer → API Keys**. Keys inherit the plan's access
level (a Pro key is read-only even on write endpoints). Rotate keys if they are exposed.

## Distinguishing rate limits from incidents

A steady stream of **429s** is a rate-limit issue tied to your plan. A burst of **5xx errors**
(500/502/503) is a server-side problem — check the CloudDesk status page for an **active API
incident** before assuming it's your integration. If there is an active api-gateway incident,
the correct guidance is to reference it and advise retry with backoff, not to change the
customer's code.
