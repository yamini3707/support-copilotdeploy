---
doc_id: arch_saml_cert
title: Architecture — What the SAML signing certificate signs
doc_type: architecture
plan: all
---

# The SAML signing certificate and its dependents

CloudDesk uses a single shared signing certificate — the SAML signing certificate — for several
cryptographic signing operations across the platform. Because it is shared, its lifecycle affects
multiple, otherwise-unrelated product surfaces at once.

The signing certificate is used by three dependents:

1. **SSO login.** SAML authentication assertions issued during single sign-on are signed with it, so
   identity providers can verify the login is genuinely from CloudDesk.
2. **Audit-log export.** Exported audit-log bundles are signed with it so customers' compliance tools
   can verify the bundles are authentic and untampered.
3. **Signed API webhooks.** Outbound webhook payloads are signed with it so customer endpoints can
   verify the request really came from CloudDesk.

Any change to the signing certificate — rotation, expiry, or revocation — can simultaneously affect
SSO login, audit-log export, and signed webhooks. For that reason its rotation is treated as a
platform-wide change, not a component-local one.
