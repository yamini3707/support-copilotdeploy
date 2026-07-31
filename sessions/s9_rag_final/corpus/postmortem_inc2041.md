---
doc_id: postmortem_inc2041
title: Postmortem INC-2041 — EU SSO login failures
doc_type: postmortem
plan: all
---

# Postmortem: INC-2041 — EU SSO login failures

**Impact.** For about two hours, ~15% of EU tenants could not log in via single sign-on. SAML
authentication assertions were rejected, blocking access to the product.

**Root cause.** SSO login assertions are signed with the shared SAML signing certificate. That
certificate was rotated on the signing service without publishing the new public key to the SSO
metadata endpoint in time, so identity providers rejected assertions signed with the new key. The
rotation was not coordinated with the certificate's dependents.

**Resolution.** We republished the certificate chain to the SSO metadata endpoint and normal login
was restored. Follow-up work was tracked to prevent uncoordinated rotations of the SAML signing
certificate in future.
