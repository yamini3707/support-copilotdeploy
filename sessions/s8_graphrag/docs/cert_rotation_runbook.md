---
doc_id: cert_rotation_runbook
title: Runbook — Safe rotation of the SAML signing certificate
doc_type: runbook
plan: all
---

# Runbook: Rotating the SAML signing certificate safely

This runbook prevents the class of outage where rotating the shared SAML signing certificate breaks
dependents that still trust the old key.

**Overlap window.** Never hard-swap the certificate. Publish the new certificate alongside the old
one and keep both valid for a 14-day overlap so every dependent can pick up the new public key before
the old one is retired.

**Coordinated publication.** Before retiring the old key, confirm the new public key is live on every
verification surface: the SSO metadata endpoint, the export verification endpoint, and the webhook
signature docs. Rotation is only complete once all three confirm the new key.

**Monitoring and alerts.** A scheduled check alerts on-call 30 days before the signing certificate
expires, and a synthetic probe validates a freshly signed test artifact every hour. If the probe
fails, page immediately — this is the earliest signal that a rotation has broken a dependent.

**Ownership.** The platform security team owns the signing certificate lifecycle. Any rotation must
be filed as a change request and cross-checked against the list of dependent services.
