---
doc_id: postmortem_inc2037
title: Postmortem INC-2037 — Audit-log export signature failures
doc_type: postmortem
plan: all
---

# Postmortem: INC-2037 — Audit-log export bundles failing signature verification

**Summary.** For roughly six hours, customers downloading audit-log export bundles received files that
failed integrity checks. Downstream verification tools rejected the bundles with a signature
mismatch, so automated compliance pipelines could not ingest them. There was no data loss; the
exports themselves were complete but could not be verified by the recipient.

**Impact.** Enterprise customers running automated audit-log ingestion were most affected. Manual
downloads still worked if the customer skipped verification, which most compliance teams do not.

**Root cause.** The export bundles are cryptographically signed. The signing operation used a
certificate that had been rotated on the signing service without the new public key being published
to the verification endpoint in time. As a result, bundles signed with the new key could not be
validated. The underlying object was the shared SAML signing certificate used across the platform's
signing operations; its rotation was not coordinated with dependents.

**Resolution.** We republished the certificate chain and re-signed the affected bundles. Follow-up
actions were tracked to prevent uncoordinated rotations of the signing certificate in future.
